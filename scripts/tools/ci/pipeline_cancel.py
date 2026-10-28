#!/usr/bin/env python3
"""取消流水线（可多仓多流水线，或一次取消某仓所有运行中的流水线）。

取消会中断正在跑的验证（含 `.post` 的锁释放 job），属不可逆动作：**不加 `--yes` 只打印计划**。

用法::

    # 先看会取消什么
    python3 scripts/tools/ci/pipeline_cancel.py bms:1285 mdm:1286

    # 确认后执行
    python3 scripts/tools/ci/pipeline_cancel.py bms:1285 mdm:1286 --yes

    # 某仓所有还没结束的流水线（running / pending / created）
    python3 scripts/tools/ci/pipeline_cancel.py --running bms --yes

凭据与地址：与 `trigger.py` 同源（`deploy/.env` 或同名环境变量）。
退出码：0 已受理；1 请求失败；2 用法错误 / 未经 `--yes` 确认。
"""

from __future__ import annotations

import argparse
import sys
import urllib.error

from ci_common import (
    REPO_NAMES,
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

ACTIVE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    ("created", "waiting_for_resource", "preparing", "pending", "running")
)
"""尚未结束、可被取消的状态。"""

SCAN_PAGE_SIZE = 20
"""`--running` 扫描最近多少条流水线。"""


def status_of(api: Api, ref: PipelineRef) -> str:
    """查流水线当前状态。

    Args:
        api: 访问上下文。
        ref: 目标流水线。

    Returns:
        str: 状态值（查询失败返回 `unknown`）。
    """
    try:
        data = get_json(api, f"projects/{quoted(ref.path)}/pipelines/{ref.pipeline_id}")
    except urllib.error.URLError, ValueError:
        return "unknown"
    if not isinstance(data, ConcurrentStableDict):
        return "unknown"
    raw = data.get("status")
    return raw if isinstance(raw, str) else "unknown"


def running_refs(api: Api, project: str) -> ConcurrentStableList[PipelineRef]:
    """取某仓最近若干条未结束的流水线。

    Args:
        api: 访问上下文。
        project: 仓短名或项目路径。

    Returns:
        ConcurrentStableList[PipelineRef]: 未结束的流水线。
    """
    refs: ConcurrentStableList[PipelineRef] = ConcurrentStableList()
    path = REPO_NAMES.get(project, project)
    data = get_json(api, f"projects/{quoted(path)}/pipelines?per_page={SCAN_PAGE_SIZE}&order_by=id")
    if not isinstance(data, ConcurrentStableList):
        return refs
    for item in data:
        if not isinstance(item, ConcurrentStableDict):
            continue
        status = item.get("status")
        raw_id = item.get("id")
        if isinstance(status, str) and status in ACTIVE_STATUSES and isinstance(raw_id, int):
            refs.append(PipelineRef(project=project, path=path, pipeline_id=raw_id))
    return refs


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 已受理 / 1 请求失败 / 2 用法错误或未确认）。
    """
    parser = argparse.ArgumentParser(description="取消流水线（不可逆，需 --yes）")
    parser.add_argument("targets", nargs="*", help="目标，格式 <仓名>:<流水线ID>，可多个或逗号分隔")
    parser.add_argument("--running", default="", help="取消该仓所有未结束的流水线（仓短名或项目路径）")
    parser.add_argument("--yes", action="store_true", help="确认执行（不加只打印计划）")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    try:
        refs = parse_pipeline_specs(split(ConcurrentStableList(args.targets)))
    except ValueError as exc:
        print(f"[cancel] {exc}", file=sys.stderr)
        return 2
    if not refs and not args.running:
        print("[cancel] 缺少目标：给 <仓名>:<流水线ID> 或 --running <仓名>", file=sys.stderr)
        return 2
    api = load_api()
    if api is None:
        print(f"[cancel] {missing_credentials_hint()}", file=sys.stderr)
        return 2

    if args.running:
        refs.extend(running_refs(api, str(args.running)))
    if not refs:
        print("[cancel] 没有可取消的流水线", file=sys.stderr)
        return 0

    plan: ConcurrentStableList[tuple[PipelineRef, str]] = ConcurrentStableList()
    for ref in refs:
        plan.append((ref, status_of(api, ref)))
    print("[cancel] 计划取消：")
    for ref, status in plan:
        print(f"[cancel]   {ref.project}#{ref.pipeline_id}  status={status}")
    if not args.yes:
        print("[cancel] 未执行：确认后加 --yes", file=sys.stderr)
        return 2

    failed = False
    for ref, _status in plan:
        try:
            result = post_json(api, f"projects/{quoted(ref.path)}/pipelines/{ref.pipeline_id}/cancel")
            state = result.get("status") if isinstance(result, ConcurrentStableDict) else "?"
            print(f"[cancel] {ref.project}#{ref.pipeline_id} → {state}")
        except urllib.error.HTTPError as exc:
            print(f"[cancel] {ref.project}#{ref.pipeline_id} 取消失败：HTTP {exc.code}", file=sys.stderr)
            failed = True
        except urllib.error.URLError as exc:
            print(f"[cancel] {ref.project}#{ref.pipeline_id} 取消失败：{exc.reason}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
