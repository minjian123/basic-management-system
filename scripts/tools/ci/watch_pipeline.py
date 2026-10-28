#!/usr/bin/env python3
"""盯守 CI 流水线到终态（手工触发之后的配套入口）。

背景：推送不触发流水线（2026-10-26 用户拍板），CI 按需手工触发、手工触发即全量；
本脚本补上「触发之后盯到哪里」的一环——轮询到终态，失败时直接给出失败 job 与日志尾部，
免得在 GitLab 页面反复刷新、逐个点开日志。

用法::

    # 盯 bms 最新一条流水线
    python3 scripts/tools/ci/watch_pipeline.py

    # 盯指定一条
    python3 scripts/tools/ci/watch_pipeline.py --pipeline 1276

    # 多仓一起盯（未给 --pipeline 时各仓取最新一条）
    python3 scripts/tools/ci/watch_pipeline.py --project bms,mdm,engkit --interval 30

    # 多仓多 id：带仓名前缀，避免配对歧义
    python3 scripts/tools/ci/watch_pipeline.py --pipeline bms:1276,mdm:1274,engkit:1275

    # 只查一次现状（不阻塞）
    python3 scripts/tools/ci/watch_pipeline.py --project bms --once

    # 机器可读汇总（脚本串联用）
    python3 scripts/tools/ci/watch_pipeline.py --project engkit --json

凭据与地址：与 `trigger.py` 同源——读仓根 `deploy/.env`（已 gitignore）的 `GITLAB_API_URL` /
`GITLAB_API_TOKEN`，也可用同名环境变量覆盖；`--project` 按项目路径名查流水线（需 token 有 api 权限）。
退出码：0 全部 success；1 存在非 success（failed / canceled / skipped）或超时未到终态；
2 用法或凭据缺失（`--once` 下 0 仅表示查询成功，不判定终态）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/ci/`）。"""

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_SRC_ROOT = ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from ci_common import clean_trace_lines  # noqa: E402
from ci_common import tail as tail_lines  # noqa: E402
from trigger import ENV_FILE, REPO_NAMES, TERMINAL_STATUSES, load_env, resolve  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402

API_TIMEOUT_SECONDS = 30
"""单次 GitLab API 调用超时（秒）。"""

FAILED_JOB_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(("failed", "canceled"))
"""判为「失败 job」的状态（其余终态 success / skipped 只计入统计）。"""

PAGE_SIZE = 100
"""job 列表分页大小（GitLab 上限 100）。"""

DEFAULT_INTERVAL_SECONDS = 20
"""轮询间隔缺省值（秒；下限 5）。"""

DEFAULT_TIMEOUT_SECONDS = 7200
"""总预算缺省值（秒；0 表示不限）。"""

DEFAULT_LOG_TAIL_LINES = 50
"""失败 job 日志尾部行数缺省值（0 表示不打日志）。"""


@dataclass(frozen=True)
class Target:
    """一条要盯的流水线。"""

    project: str
    path: str
    pipeline_id: int


def _quoted(path: str) -> str:
    """URL 编码项目路径（`bms/bms` → `bms%2Fbms`）。

    Args:
        path: GitLab 项目路径。

    Returns:
        str: 编码后的路径。
    """
    return urllib.parse.quote(path, safe="")


def _wrap(value: object) -> object:
    """把 JSON 解析结果整体换成并发稳定容器（护栏要求集合声明走 ConcurrentStable*）。

    Args:
        value: `json.loads` 的原始结果。

    Returns:
        object: 递归替换后的结构（映射 → ConcurrentStableDict、数组 → ConcurrentStableList）。
    """
    if isinstance(value, dict):
        return ConcurrentStableDict((str(key), _wrap(item)) for key, item in value.items())
    if isinstance(value, list):
        return ConcurrentStableList(_wrap(item) for item in value)
    return value


def _jsonable(value: object) -> object:
    """把并发稳定容器还原成 `json` 可序列化的结构。

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


def _get_text(api: str, token: str, path: str) -> str:
    """GET 原始响应文本（JSON 与 job 日志共用）。

    Args:
        api: API 基址。
        token: 访问令牌。
        path: 相对 API 基址的路径。

    Returns:
        str: 响应体文本（空响应为空串）。
    """
    url = f"{api.rstrip('/')}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token}, method="GET")
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", "replace")


def _get_json(api: str, token: str, path: str) -> object:
    """GET 并解析 JSON（流水线与 job 列表既可能是对象也可能是数组）。

    Args:
        api: API 基址。
        token: 访问令牌。
        path: 相对 API 基址的路径。

    Returns:
        object: 解析后的响应（空响应为空映射）。
    """
    raw = _get_text(api, token, path)
    return _wrap(json.loads(raw)) if raw.strip() else ConcurrentStableDict()


def _split(values: ConcurrentStableList[str] | None) -> ConcurrentStableList[str]:
    """把可重复 / 逗号分隔的参数拍平（保序去重）。

    Args:
        values: 原始参数（可为 None）。

    Returns:
        ConcurrentStableList[str]: 拍平后的取值。
    """
    flattened: ConcurrentStableList[str] = ConcurrentStableList()
    for value in values or ():
        for item in value.split(","):
            name = item.strip()
            if name and name not in flattened:
                flattened.append(name)
    return flattened


def _parse_pipeline_arg(raw: str, projects: ConcurrentStableList[str]) -> tuple[str, int]:
    """解析单个 `--pipeline` 取值（`<ID>` 或 `<仓名>:<ID>`）。

    Args:
        raw: 原始取值。
        projects: `--project` 解析结果（决定无前缀 ID 的归属仓）。

    Returns:
        tuple[str, int]: 仓短名与流水线 ID（异质二元组，非集合声明）。
    """
    name, sep, digits = raw.partition(":")
    if not sep:
        name, digits = "", raw
    name = name.strip()
    digits = digits.strip()
    if not digits.isdigit():
        raise ValueError(f"--pipeline 取值非法：{raw}（应写成 <ID> 或 <仓名>:<ID>）")
    if not name:
        if len(projects) != 1:
            raise ValueError(
                f"--pipeline {raw} 未带仓名前缀：--project 需恰好一个仓（当前 {len(projects)} 个），或写成 仓名:ID",
            )
        name = projects[0]
    return name, int(digits)


def _latest_pipeline_id(api: str, token: str, path: str) -> int:
    """取项目最近一条流水线 ID。

    Args:
        api: API 基址。
        token: 访问令牌。
        path: GitLab 项目路径。

    Returns:
        int: 流水线 ID。
    """
    data = _get_json(api, token, f"projects/{_quoted(path)}/pipelines?per_page=1&order_by=id")
    if not isinstance(data, ConcurrentStableList) or not data:
        raise ValueError(f"{path} 没有流水线记录（先手动触发一次）")
    first: object = data[0]
    if not isinstance(first, ConcurrentStableDict):
        raise ValueError(f"{path} 最新流水线响应非法")
    raw_id = first.get("id")
    if not isinstance(raw_id, int):
        raise ValueError(f"{path} 最新流水线未返回 id")
    return raw_id


def resolve_targets(
    api: str,
    token: str,
    projects: ConcurrentStableList[str],
    pipelines: ConcurrentStableList[str],
) -> ConcurrentStableList[Target]:
    """解析要盯的流水线集合。

    Args:
        api: API 基址。
        token: 访问令牌。
        projects: `--project` 解析结果。
        pipelines: `--pipeline` 解析结果（为空表示各仓取最新一条）。

    Returns:
        ConcurrentStableList[Target]: 目标列表（保序去重）。
    """
    targets: ConcurrentStableList[Target] = ConcurrentStableList()
    if pipelines:
        for raw in pipelines:
            name, pipeline_id = _parse_pipeline_arg(raw, projects)
            target = Target(project=name, path=REPO_NAMES.get(name, name), pipeline_id=pipeline_id)
            if target not in targets:
                targets.append(target)
        return targets
    for name in projects or ("bms",):
        path = REPO_NAMES.get(name, name)
        target = Target(project=name, path=path, pipeline_id=_latest_pipeline_id(api, token, path))
        if target not in targets:
            targets.append(target)
    return targets


def pipeline_status(api: str, token: str, target: Target) -> str:
    """查询流水线当前状态。

    Args:
        api: API 基址。
        token: 访问令牌。
        target: 目标流水线。

    Returns:
        str: GitLab 状态值（`created` / `running` / `failed` / `success` …）。
    """
    data = _get_json(api, token, f"projects/{_quoted(target.path)}/pipelines/{target.pipeline_id}")
    if not isinstance(data, ConcurrentStableDict):
        raise ValueError(f"{target.project}#{target.pipeline_id} 流水线响应非法")
    raw = data.get("status")
    return raw if isinstance(raw, str) else "unknown"


def pipeline_jobs(
    api: str,
    token: str,
    target: Target,
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """分页取流水线的全部 job。

    Args:
        api: API 基址。
        token: 访问令牌。
        target: 目标流水线。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: job 对象序列（按 GitLab 返回顺序）。
    """
    jobs: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    page = 1
    while True:
        path = f"projects/{_quoted(target.path)}/pipelines/{target.pipeline_id}/jobs?per_page={PAGE_SIZE}&page={page}"
        data = _get_json(api, token, path)
        if not isinstance(data, ConcurrentStableList):
            raise ValueError(f"{target.project}#{target.pipeline_id} job 列表响应非法")
        items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            item for item in data if isinstance(item, ConcurrentStableDict)
        )
        jobs.extend(items)
        if len(data) < PAGE_SIZE:
            return jobs
        page += 1


def _job_field(job: ConcurrentStableDict[str, object], key: str, default: object) -> object:
    """取 job 字段（缺失回落缺省值）。

    Args:
        job: job 对象。
        key: 字段名。
        default: 缺省值。

    Returns:
        object: 字段值。
    """
    return job.get(key, default)


def job_trace_tail(api: str, token: str, target: Target, job_id: int, tail: int) -> ConcurrentStableList[str]:
    """取 job 日志尾部若干有效行（日志已过期时返回提示行）。

    Args:
        api: API 基址。
        token: 访问令牌。
        target: 目标流水线。
        job_id: job ID。
        tail: 有效行数（<= 0 返回空）。

    Returns:
        ConcurrentStableList[str]: 清理后的日志尾部行（已去 ANSI 码、时间戳与折叠段标记）。
    """
    if tail <= 0:
        return ConcurrentStableList()
    try:
        text = _get_text(api, token, f"projects/{_quoted(target.path)}/jobs/{job_id}/trace")
    except urllib.error.HTTPError as exc:
        return ConcurrentStableList((f"（日志不可取：HTTP {exc.code}）",))
    return tail_lines(clean_trace_lines(text), tail)


def _counts(jobs: ConcurrentStableList[ConcurrentStableDict[str, object]]) -> str:
    """汇总 job 状态计数（`success 9 / failed 1` 形式）。

    Args:
        jobs: job 对象序列。

    Returns:
        str: 计数摘要。
    """
    counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for job in jobs:
        status = _job_field(job, "status", "unknown")
        key = status if isinstance(status, str) else "unknown"
        counts.set(key, counts.get(key, 0) + 1)
    return " / ".join(f"{name} {count}" for name, count in counts.items())


def report(
    api: str,
    token: str,
    target: Target,
    status: str,
    jobs: ConcurrentStableList[ConcurrentStableDict[str, object]],
    log_tail: int,
) -> bool:
    """打印单条流水线的终态、job 计数与失败 job 日志尾部。

    Args:
        api: API 基址。
        token: 访问令牌。
        target: 目标流水线。
        status: 终态。
        jobs: job 对象序列。
        log_tail: 失败 job 日志尾部行数（0 不打日志）。

    Returns:
        bool: 是否 success。
    """
    print(f"[watch] {target.project}#{target.pipeline_id} 终态 {status}（job {len(jobs)} 个：{_counts(jobs)}）")
    for job in jobs:
        job_status = _job_field(job, "status", "")
        if job_status not in FAILED_JOB_STATUSES:
            continue
        name = str(_job_field(job, "name", "?"))
        job_id = _job_field(job, "id", 0)
        allow_failure = bool(_job_field(job, "allow_failure", False))
        web_url = str(_job_field(job, "web_url", ""))
        flag = "（allow_failure，不阻断）" if allow_failure else ""
        print(f"[watch]   失败 job：{name} [{job_status}]{flag} {web_url}".rstrip())
        if log_tail > 0 and isinstance(job_id, int) and job_id > 0:
            print(f"[watch]   ---- {name} 日志尾部（最后 {log_tail} 行）----")
            for line in job_trace_tail(api, token, target, job_id, log_tail):
                print(f"[watch]   {line}")
    return status == "success"


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 全 success / 1 存在非 success 或超时 / 2 用法或凭据缺失）。
    """
    parser = argparse.ArgumentParser(description="盯守 CI 流水线到终态（手工触发后的配套入口）")
    parser.add_argument(
        "--project",
        action="append",
        default=None,
        help="仓短名（bms / mdm / engkit / biz / test）或 GitLab 项目路径；可重复或逗号分隔，缺省 bms",
    )
    parser.add_argument(
        "--pipeline",
        action="append",
        default=None,
        help="流水线 ID；可重复或逗号分隔，多仓并用时写成 仓名:ID",
    )
    parser.add_argument("--latest", action="store_true", help="显式声明盯各仓最新一条（与不给 --pipeline 等价）")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"轮询间隔秒数（缺省 {DEFAULT_INTERVAL_SECONDS}，下限 5）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"总预算秒数（缺省 {DEFAULT_TIMEOUT_SECONDS}，0 表示不限）",
    )
    parser.add_argument(
        "--log-tail",
        type=int,
        default=DEFAULT_LOG_TAIL_LINES,
        help=f"失败 job 日志尾部行数（缺省 {DEFAULT_LOG_TAIL_LINES}，0 不打日志）",
    )
    parser.add_argument("--once", action="store_true", help="只查一次现状即返回（秒查，不阻塞）")
    parser.add_argument("--json", action="store_true", help="终态时额外输出机器可读汇总")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    env = load_env(ENV_FILE)
    api = resolve("GITLAB_API_URL", env)
    token = resolve("GITLAB_API_TOKEN", env)
    if not api or not token:
        print(f"[watch] 缺少 GITLAB_API_URL / GITLAB_API_TOKEN（读 {ENV_FILE} 或同名环境变量）", file=sys.stderr)
        return 2

    projects = _split(ConcurrentStableList(args.project or ()))
    pipelines = _split(ConcurrentStableList(args.pipeline or ()))
    if args.latest and pipelines:
        print("[watch] --latest 与 --pipeline 不能同时使用", file=sys.stderr)
        return 2

    try:
        targets = resolve_targets(api, token, projects, pipelines)
    except (urllib.error.URLError, ValueError) as exc:
        print(f"[watch] 解析流水线失败：{exc}", file=sys.stderr)
        return 1

    interval = max(5, int(args.interval))
    deadline = time.monotonic() + args.timeout if args.timeout > 0 else None
    states: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    while True:
        line_parts: ConcurrentStableList[str] = ConcurrentStableList()
        for target in targets:
            try:
                status = pipeline_status(api, token, target)
            except (urllib.error.URLError, ValueError) as exc:
                status = f"error:{exc}"
            states.set(target.pipeline_id, status)
            line_parts.append(f"{target.project}#{target.pipeline_id}={status}")
        print(f"[watch] {time.strftime('%H:%M:%S')} " + " | ".join(line_parts), flush=True)

        if args.once:
            return 0
        if all(states.get(target.pipeline_id) in TERMINAL_STATUSES for target in targets):
            break
        if deadline is not None and time.monotonic() >= deadline:
            print(f"[watch] 超时：{args.timeout}s 内未到终态（用 --timeout 0 取消预算，或继续等待）", file=sys.stderr)
            return 1
        time.sleep(interval)

    ok = True
    summary: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for target in targets:
        status = states.get(target.pipeline_id) or "unknown"
        try:
            jobs = pipeline_jobs(api, token, target)
        except (urllib.error.URLError, ValueError) as exc:
            print(f"[watch] {target.project}#{target.pipeline_id} job 列表查询失败：{exc}", file=sys.stderr)
            jobs = ConcurrentStableList()
        if not report(api, token, target, status, jobs, int(args.log_tail)):
            ok = False
        summary.append(
            ConcurrentStableDict(
                {
                    "project": target.project,
                    "pipeline_id": target.pipeline_id,
                    "status": status,
                    "jobs": ConcurrentStableList(
                        ConcurrentStableDict(
                            {
                                "name": _job_field(job, "name", ""),
                                "status": _job_field(job, "status", ""),
                                "allow_failure": _job_field(job, "allow_failure", False),
                                "web_url": _job_field(job, "web_url", ""),
                            },
                        )
                        for job in jobs
                    ),
                },
            ),
        )

    if ok:
        print(f"[watch] 结论：{len(targets)} 条全部 success")
    else:
        failed = ", ".join(
            f"{target.project}#{target.pipeline_id} {states.get(target.pipeline_id)}"
            for target in targets
            if states.get(target.pipeline_id) != "success"
        )
        print(f"[watch] 结论：存在非 success（{failed}）")
    if args.json:
        print(json.dumps(_jsonable(ConcurrentStableDict({"pipelines": summary})), ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
