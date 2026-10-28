#!/usr/bin/env python3
"""重试流水线里失败的 job（不改代码只重跑）。

常见场景：网络抖动、runner 抽风、拉取超时导致个别 job 失败，整条重触发浪费几分钟，重试失败 job 即可。
属会占用 runner 的动作：**不加 `--yes` 只打印计划**。

用法::

    # 先看会重试哪些
    python3 scripts/tools/ci/pipeline_retry.py bms:1285

    # 确认后执行
    python3 scripts/tools/ci/pipeline_retry.py bms:1285 --yes

凭据与地址：与 `trigger.py` 同源（`deploy/.env` 或同名环境变量）。
退出码：0 已受理 / 1 请求失败 / 2 用法错误或未经 `--yes` 确认。
"""

from __future__ import annotations

import argparse
import sys
import urllib.error

from ci_common import (
    Api,
    ConcurrentStableDict,
    ConcurrentStableList,
    PipelineRef,
    get_json,
    load_api,
    missing_credentials_hint,
    parse_pipeline_specs,
    post_json,
    quoted,
    split,
)

PAGE_SIZE = 100
"""job 列表分页大小（GitLab 上限 100）。"""

RETRYABLE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(("failed", "canceled"))
"""可重试的 job 状态。"""


def jobs_of(api: Api, ref: PipelineRef) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """分页取一条流水线的全部 job。

    Args:
        api: 访问上下文。
        ref: 目标流水线。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: job 列表。
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


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 已受理 / 1 请求失败 / 2 用法错误或未确认）。
    """
    parser = argparse.ArgumentParser(description="重试流水线里失败的 job（需 --yes）")
    parser.add_argument("targets", nargs="+", help="目标，格式 <仓名>:<流水线ID>，可多个或逗号分隔")
    parser.add_argument("--yes", action="store_true", help="确认执行（不加只打印计划）")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    try:
        refs = parse_pipeline_specs(split(ConcurrentStableList(args.targets)))
    except ValueError as exc:
        print(f"[retry] {exc}", file=sys.stderr)
        return 2
    api = load_api()
    if api is None:
        print(f"[retry] {missing_credentials_hint()}", file=sys.stderr)
        return 2

    plan: ConcurrentStableList[tuple[PipelineRef, int, str]] = ConcurrentStableList()
    for ref in refs:
        try:
            jobs = jobs_of(api, ref)
        except (urllib.error.URLError, ValueError) as exc:
            print(f"[retry] {ref.project}#{ref.pipeline_id} 查询失败：{exc}", file=sys.stderr)
            return 1
        for job in jobs:
            status = job.get("status")
            raw_id = job.get("id")
            allow_failure = bool(job.get("allow_failure", False))
            name = str(job.get("name", "?"))
            if (
                isinstance(status, str)
                and status in RETRYABLE_STATUSES
                and isinstance(raw_id, int)
                and not allow_failure
            ):
                plan.append((ref, raw_id, name))

    if not plan:
        print("[retry] 没有可重试的 job（失败 job 为空，或都标了 allow_failure）")
        return 0
    print("[retry] 计划重试：")
    for ref, job_id, name in plan:
        print(f"[retry]   {ref.project}#{ref.pipeline_id}  {name}  job={job_id}")
    if not args.yes:
        print("[retry] 未执行：确认后加 --yes", file=sys.stderr)
        return 2

    failed = False
    for ref, job_id, name in plan:
        try:
            result = post_json(api, f"projects/{quoted(ref.path)}/jobs/{job_id}/retry")
            new_id = result.get("id") if isinstance(result, ConcurrentStableDict) else "?"
            print(f"[retry]   {ref.project}#{ref.pipeline_id}  {name}  → 新 job {new_id}")
        except urllib.error.HTTPError as exc:
            print(f"[retry]   {ref.project}#{ref.pipeline_id}  {name}  重试失败：HTTP {exc.code}", file=sys.stderr)
            failed = True
        except urllib.error.URLError as exc:
            print(f"[retry]   {ref.project}#{ref.pipeline_id}  {name}  重试失败：{exc.reason}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
