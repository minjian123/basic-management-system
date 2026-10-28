#!/usr/bin/env python3
"""列流水线的 job 状态（id / 阶段 / 状态 / 时长）。

与 `watch_pipeline.py` 的分工：那边盯到终态、只展开失败 job；这边是**随时查**——看任意历史流水线
的全部 job，含 id（拿去做 `job_log.py`）、阶段、时长与 allow_failure。

用法::

    # 看一条流水线的全部 job
    python3 scripts/tools/ci/pipeline_jobs.py bms:1285

    # 多仓一起看
    python3 scripts/tools/ci/pipeline_jobs.py bms:1285,mdm:1286

    # 只看失败 / 只跑中的
    python3 scripts/tools/ci/pipeline_jobs.py bms:1285 --status failed

    # 机器可读
    python3 scripts/tools/ci/pipeline_jobs.py bms:1285 --json

凭据与地址：与 `trigger.py` 同源（`deploy/.env` 或同名环境变量）。
退出码：0 查询成功；1 请求失败；2 用法或凭据缺失。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error

from ci_common import (
    Api,
    ConcurrentStableDict,
    ConcurrentStableList,
    PipelineRef,
    downstream_id,
    get_bridges,
    get_json,
    load_api,
    missing_credentials_hint,
    parse_pipeline_specs,
    quoted,
    split,
)

PAGE_SIZE = 100
"""job 列表分页大小（GitLab 上限 100）。"""


def jobs_of(api: Api, ref: PipelineRef) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """分页取一条流水线的全部 job。

    Args:
        api: 访问上下文。
        ref: 目标流水线。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: job 列表（GitLab 返回顺序）。
    """
    jobs: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    page = 1
    while True:
        path = f"projects/{quoted(ref.path)}/pipelines/{ref.pipeline_id}/jobs?per_page={PAGE_SIZE}&page={page}"
        data = get_json(api, path)
        if not isinstance(data, ConcurrentStableList):
            raise ValueError(f"{ref.project}#{ref.pipeline_id} job 列表响应非法")
        jobs.extend(item for item in data if isinstance(item, ConcurrentStableDict))
        if len(data) < PAGE_SIZE:
            return jobs
        page += 1


def _jsonable(value: object) -> object:
    """把并发稳定容器还原成可序列化结构。

    Args:
        value: 待序列化的结构。

    Returns:
        object: 普通 dict / list 结构。
    """
    if isinstance(value, ConcurrentStableDict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, ConcurrentStableList):
        return [_jsonable(item) for item in value]
    return value


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 成功 / 1 请求失败 / 2 用法或凭据缺失）。
    """
    parser = argparse.ArgumentParser(description="列流水线的 job 状态")
    parser.add_argument("targets", nargs="+", help="目标，格式 <仓名>:<流水线ID>，可多个或逗号分隔")
    parser.add_argument("--status", default="", help="只显示指定状态的 job（如 failed / running / success）")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    try:
        refs = parse_pipeline_specs(split(ConcurrentStableList(args.targets)))
    except ValueError as exc:
        print(f"[jobs] {exc}", file=sys.stderr)
        return 2
    api = load_api()
    if api is None:
        print(f"[jobs] {missing_credentials_hint()}", file=sys.stderr)
        return 2

    wanted = str(args.status).strip()
    failed = False
    summary: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for ref in refs:
        try:
            jobs = jobs_of(api, ref)
        except urllib.error.HTTPError as exc:
            print(f"[jobs] {ref.project}#{ref.pipeline_id} 查询失败：HTTP {exc.code}", file=sys.stderr)
            failed = True
            continue
        except (urllib.error.URLError, ValueError) as exc:
            print(f"[jobs] {ref.project}#{ref.pipeline_id} 查询失败：{exc}", file=sys.stderr)
            failed = True
            continue
        if not args.json:
            print(f"== {ref.path} #{ref.pipeline_id}（job {len(jobs)} 个）==")
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for job in jobs:
            status = str(job.get("status", ""))
            if wanted and status != wanted:
                continue
            stage = str(job.get("stage", ""))
            name = str(job.get("name", ""))
            job_id = job.get("id", 0)
            duration = job.get("duration")
            allow_failure = bool(job.get("allow_failure", False))
            rows.append(
                ConcurrentStableDict(
                    {
                        "name": name,
                        "id": job_id,
                        "stage": stage,
                        "status": status,
                        "duration": duration,
                        "allow_failure": allow_failure,
                    },
                ),
            )
            if not args.json:
                flag = "（allow_failure）" if allow_failure else ""
                spent = f"{float(duration):.0f}s" if isinstance(duration, (int, float)) else "-"
                print(f"  {stage:<10} {status:<10} {name:<28} id={job_id:<8} {spent}{flag}")
        summary.append(ConcurrentStableDict({"pipeline": ref.path, "id": ref.pipeline_id, "jobs": rows}))
        if not args.json and not rows:
            print("  （无匹配 job）")

        bridges = get_bridges(api, ref)
        if bridges:
            if not args.json:
                print("  --- 子流水线（bridge，`/jobs` 不含）---")
            bridge_rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            for bridge in bridges:
                status = str(bridge.get("status", ""))
                if wanted and status != wanted:
                    continue
                name = str(bridge.get("name", ""))
                bridge_id = bridge.get("id", 0)
                child = downstream_id(bridge)
                bridge_rows.append(
                    ConcurrentStableDict({"name": name, "id": bridge_id, "status": status, "downstream_id": child}),
                )
                if not args.json:
                    print(f"  {'bridge':<10} {status:<10} {name:<28} id={bridge_id:<8} → 子流水线 #{child}")
            summary.append(ConcurrentStableDict({"pipeline": ref.path, "id": ref.pipeline_id, "bridges": bridge_rows}))

    if args.json:
        print(json.dumps(_jsonable(summary), ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
