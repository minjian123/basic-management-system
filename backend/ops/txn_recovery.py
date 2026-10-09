"""跨服务事务恢复命令行：悬挂 / 启发式对账与协议驱动（运维入口，不启 lifespan）。

用法::

    uv run python -m ops.txn_recovery list --state hung [--limit N]
    uv run python -m ops.txn_recovery drive-commit --global-txn-id ID
    uv run python -m ops.txn_recovery drive-rollback --global-txn-id ID

- `list`：**直读 TM 账本**（平台侧独立基础设施库 `bms_txn`）——列出非终态（`hung`）或
  启发式完成（`heuristic`）事务及其分支，供人工对账；
- `drive-commit` / `drive-rollback`：**只驱动协议**——调 TM 端点完成协议推进
  （决定点之后 `rollback` 由 TM **幂等吸收**，不会回滚已提交事务）；
- **禁止手工修改业务数据**（详设 05_07 §6 硬口径）：人的动作＝幂等重放 / 驱动协议，
  全程由 TM 落 `global_txn_recovery` 台账留痕。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from fastapi import FastAPI

from bms_core.core.assembly import register_platform_plugins
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.resources import ResourceManager
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_core.transaction.base import TM_SERVICE_NAME
from bms_txn.repositories.ledger import GlobalTxnBranchRepository, GlobalTxnRepository

_STATE_HUNG = "hung"
"""悬挂：非终态（在途）事务。"""

_STATE_HEURISTIC = "heuristic"
"""启发式：参与方单方面提交 / 回滚形成的异常终态。"""


async def _list(args: argparse.Namespace) -> int:
    """列出待对账事务与分支并打印。

    Args:
        args: 命令行参数（`state` / `limit` / `db_key`）。

    Returns:
        int: 退出码（0 成功）。
    """
    settings = get_settings()
    registry = EngineRegistry(EngineFactory(settings))
    try:
        async with session_scope(registry, db_key=args.db_key, factory=SessionFactory()) as session:
            txns = GlobalTxnRepository(session)
            branches = GlobalTxnBranchRepository(session)
            if args.state == _STATE_HEURISTIC:
                rows = await txns.list_heuristic(limit=args.limit)
            else:
                rows = await txns.list_unsettled(limit=args.limit)
            if not rows:
                print(f"待对账事务（{args.state}）：无")
                return 0
            for row in rows:
                decided = row.decided_at.isoformat() if row.decided_at else "-"
                print(
                    f"[{row.state}] {row.global_txn_id}  caller={row.caller_service}  "
                    f"deadline={row.deadline_at.isoformat()}  decided={decided}"
                )
                for branch in await branches.list_by_txn(row.global_txn_id):
                    error = branch.last_error or "-"
                    print(
                        f"    - {branch.branch_id}  service={branch.service}  db_key={branch.db_key}  "
                        f"state={branch.state}  retry={branch.retry_count}  err={error}"
                    )
            print(f"合计 {len(rows)} 项（{args.state}）")
    finally:
        await registry.aclose()
    return 0


def _service_client() -> BaseServiceClient:
    """构造服务间调用客户端（CLI 无应用上下文，按配置自行装配）。

    Returns:
        BaseServiceClient: 服务间调用客户端。
    """
    settings = get_settings()
    app = FastAPI()
    register_platform_plugins(settings, app, ResourceManager())
    build_plugin_registry()
    return cast(
        "BaseServiceClient",
        resolve_plugin(
            "service_client",
            settings.service_client.provider or "http",
            expected_version=BaseServiceClient.contract_version,
        ),
    )


async def _drive(args: argparse.Namespace, *, commit: bool) -> int:
    """驱动协议到终态（提交 / 回滚；只调 TM，不写业务数据）。

    Args:
        args: 命令行参数（`global_txn_id`）。
        commit: True 驱动提交 / False 驱动回滚。

    Returns:
        int: 退出码（0 成功；1 失败）。
    """
    client = _service_client()
    path = f"/api/v1/txn/global/{args.global_txn_id}"
    request = (
        ServiceRequest(service=TM_SERVICE_NAME, method="POST", path=f"{path}/commit")
        if commit
        else ServiceRequest(service=TM_SERVICE_NAME, method="DELETE", path=path)
    )
    response = await client.call(request)
    payload = response.payload()
    print(f"驱动{'提交' if commit else '回滚'} {args.global_txn_id}：HTTP {response.status_code} {payload}")
    return 0 if response.status_code // 100 == 2 else 1


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(prog="ops.txn_recovery", description="跨服务事务对账与协议驱动")
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="列出待对账事务（hung 在途 / heuristic 启发式终态）")
    listing.add_argument("--state", choices=[_STATE_HUNG, _STATE_HEURISTIC], default=_STATE_HUNG, help="筛选口径")
    listing.add_argument("--limit", type=int, default=200, help="单轮上限")
    listing.add_argument("--db-key", default=PLATFORM_DB_KEY, help="数据源键（缺省平台库 = 账本库）")

    drive_commit = subparsers.add_parser("drive-commit", help="驱动提交（只驱动协议）")
    drive_commit.add_argument("--global-txn-id", required=True, help="全局事务标识")

    drive_rollback = subparsers.add_parser("drive-rollback", help="驱动回滚（决定点后由 TM 幂等吸收）")
    drive_rollback.add_argument("--global-txn-id", required=True, help="全局事务标识")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：解析参数并执行子命令。

    Args:
        argv: 参数列表（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return asyncio.run(_list(args))
        return asyncio.run(_drive(args, commit=args.command == "drive-commit"))
    except Exception as exc:
        print(f"跨服务事务恢复命令失败：{exc!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
