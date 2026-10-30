"""发布清单运维入口（07C `04_01`）：前置校验、清单写入、批次回滚与查询。

```bash
cd backend
uv run python -m ops.release precheck --unit platform                       # 只看六条校验结论（不写库）
uv run python -m ops.release record   --unit platform --note "首次发布"      # 校验通过后写清单
uv run python -m ops.release fail     --unit platform --note "结构清单执行失败"  # 执行阶段失败留痕
uv run python -m ops.release plan     --unit platform                       # 生成回滚计划（不写库）
uv run python -m ops.release rollback --unit platform --confirm             # 按计划回滚（新增 rolled_back 行）
uv run python -m ops.release list     --unit platform --limit 5             # 最近几次发布与逐域版本
```

口径：

- **不写第二套逻辑**：经平台应用工厂进入生命周期，校验 / 写入 / 回滚都复用 `ReleaseService`，
  故命令行与进程内行为一致；
- **结构 revision 跨库读**：每域一张 `alembic_version_{domain}`，落在该域清单所属库；平台链连接串按配置解析，
  租户链需显式 `--tenant-url`（租户库键由调用方派生，运维入口不猜）；
- **失败即失败**：校验未过退出码 1 且不写任何行；执行阶段失败用 `fail` 子命令留痕（`status=failed`）；
- 退出码：0 成功 / 1 失败（异常信息打到 stderr，不吞错）。
"""

import argparse
import asyncio
import json
import sys
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.migration import DATASOURCE_PLATFORM, DATASOURCE_TENANT, current_revision, domain_series
from bms_core.db.session import session_scope
from bms_platform.domains.platform_registry.dto import (
    ReleaseDomainEntry,
    ReleaseManifestSnapshot,
    ReleasePrecheckResult,
    RollbackPlan,
)
from bms_platform.domains.platform_registry.ports import ReleaseRevisionPort
from bms_platform.domains.platform_registry.services.release import ReleaseService
from bms_platform.main import ApplicationFactory

__all__ = ["DatabaseRevisions", "build_parser", "main", "run"]

RUN_IMAGE = "platform"
"""本脚本依赖平台服务包（`bms_platform`），仅平台镜像可运行。"""

_COMMANDS = ("precheck", "record", "fail", "plan", "rollback", "list")
"""子命令全集（与 `build_parser` 的注册保持一一对应）。"""


class DatabaseRevisions(ReleaseRevisionPort):
    """结构 revision 读面实现：按域清单所属数据源连库读版本记录表。

    一域可能跨两条链（平台库 / 服务租户库各有一份清单，记录表同名）——按 `platform` → `tenant` 顺序
    取**首个已初始化**的 revision，作为该域本次发布的结构版本快照。
    """

    def __init__(self, urls: ConcurrentStableDict[str, str]) -> None:
        """初始化。

        Args:
            urls: 数据源段 → 连接串（`platform` / `tenant`）。
        """
        self._urls = ConcurrentStableDict(urls)

    async def current(self, domain_key: str) -> str | None:
        """读取某域的结构 revision。

        Args:
            domain_key: 业务域标识。

        Returns:
            str | None: 当前 revision；连接串缺失或该域尚未初始化时返回 None。
        """
        for series in domain_series(domain_key):
            url = self._urls.get(series.datasource)
            if not url:
                continue
            revision = await current_revision(url, version_table=series.version_table)
            if revision:
                return revision
        return None


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器（六个子命令）。
    """
    parser = argparse.ArgumentParser(description="发布清单运维入口（校验 / 写入 / 回滚 / 查询）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        """给子命令补公共参数。

        Args:
            target: 子命令解析器。
        """
        target.add_argument("--unit", required=True, help="部署单元标识（拓扑中的 unit_key）")
        target.add_argument("--tenant-scope", type=int, default=0, help="作用范围（0 = 全局）")
        target.add_argument("--platform-url", default="", help="平台库连接串（缺省按配置解析）")
        target.add_argument("--tenant-url", default="", help="服务租户库连接串（租户链结构 revision 用）")

    for name, help_text in (
        ("precheck", "只做六条前置校验，输出结论（不写库）"),
        ("record", "校验通过后写入发布清单（主表 + 明细）"),
        ("fail", "记录一次执行阶段失败（只写主表行）"),
        ("plan", "生成批次回滚计划（不写库）"),
        ("rollback", "按计划回滚：新增一行 rolled_back，不修改原行"),
        ("list", "查最近若干次发布与逐域版本"),
    ):
        command = sub.add_parser(name, help=help_text)
        add_common(command)
        if name in ("precheck", "record"):
            command.add_argument("--manifest-version", type=int, default=None, help="批次号（缺省当前最大值 + 1）")
            command.add_argument("--topology-version", type=int, default=None, help="绑定的拓扑版本（缺省取当前）")
            command.add_argument(
                "--declare",
                action="append",
                default=[],
                metavar="域,服务版本,契约版本,结构revision",
                help="流水线声明的期望版本（可重复；缺省按登记值与记录表落盘）",
            )
            command.add_argument("--allow-breaking", action="store_true", help="放行契约破坏性变更（主版本升级流程）")
        if name in ("record", "fail", "rollback"):
            command.add_argument("--note", default="", help="发布摘要 / 失败原因 / 回滚原因")
        if name in ("plan", "rollback"):
            command.add_argument("--to-version", type=int, default=None, help="回退目标批次号（缺省上一成功发布）")
        if name == "rollback":
            command.add_argument("--confirm", action="store_true", help="确认结构回退（涉及删列类回退必须显式确认）")
        if name == "list":
            command.add_argument("--limit", type=int, default=10, help="返回条数上限")
    return parser


def _resolve_urls(args: argparse.Namespace) -> ConcurrentStableDict[str, str]:
    """解析各数据源的连接串（平台链缺省按配置，租户链只能显式给）。

    Args:
        args: 命令行参数。

    Returns:
        ConcurrentStableDict[str, str]: 数据源段 → 连接串。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    platform_url = cast("str", args.platform_url) or factory.resolved_url(PLATFORM_DB_KEY)
    urls: ConcurrentStableDict[str, str] = ConcurrentStableDict({DATASOURCE_PLATFORM: platform_url})
    tenant_url = cast("str", args.tenant_url)
    if tenant_url:
        urls.set(DATASOURCE_TENANT, tenant_url)
    return urls


def _declared(raw: ConcurrentStableList[str]) -> ConcurrentStableList[ReleaseDomainEntry]:
    """把 `--declare` 参数解析为声明条目。

    Args:
        raw: 形如 `域,服务版本,契约版本,结构revision` 的字符串（后三段可空）。

    Returns:
        ConcurrentStableList[ReleaseDomainEntry]: 声明条目。

    Raises:
        ValueError: 段数不足或域标识为空。
    """
    entries: ConcurrentStableList[ReleaseDomainEntry] = ConcurrentStableList()
    for item in raw:
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 4 or not parts[0]:
            raise ValueError(f"--declare 需 4 段（域,服务版本,契约版本,结构revision）：{item}")
        entries.add(
            ReleaseDomainEntry(
                domain_key=parts[0],
                service_key="",
                service_version=parts[1],
                contract_version=parts[2],
                schema_revision=parts[3] or None,
            )
        )
    return entries


def _entry_payload(entry: ReleaseDomainEntry) -> ConcurrentStableDict[str, object]:
    """域明细转可序列化结构。

    Args:
        entry: 域明细。

    Returns:
        ConcurrentStableDict[str, object]: 输出结构。
    """
    return ConcurrentStableDict(
        {
            "domain_key": entry.domain_key,
            "service_key": entry.service_key,
            "service_version": entry.service_version,
            "contract_version": entry.contract_version,
            "schema_revision": entry.schema_revision,
        }
    )


def _manifest_payload(row: ReleaseManifestSnapshot) -> ConcurrentStableDict[str, object]:
    """发布快照转可序列化结构。

    Args:
        row: 发布快照。

    Returns:
        ConcurrentStableDict[str, object]: 输出结构。
    """
    return ConcurrentStableDict(
        {
            "manifest_id": row.id,
            "unit_key": row.unit_key,
            "tenant_scope": row.tenant_scope,
            "manifest_version": row.manifest_version,
            "topology_version": row.topology_version,
            "status": row.status,
            "released_at": row.released_at.isoformat(),
            "rolled_back_from": row.rolled_back_from,
            "note": row.note,
            "domains": ConcurrentStableList(_entry_payload(entry) for entry in row.domains),
        }
    )


def _precheck_payload(result: ReleasePrecheckResult) -> ConcurrentStableDict[str, object]:
    """预检结论转可序列化结构。

    Args:
        result: 预检结论。

    Returns:
        ConcurrentStableDict[str, object]: 输出结构。
    """
    return ConcurrentStableDict(
        {
            "unit_key": result.unit_key,
            "tenant_scope": result.tenant_scope,
            "manifest_version": result.manifest_version,
            "topology_version": result.topology_version,
            "passed": result.passed,
            "items": ConcurrentStableList(
                ConcurrentStableDict(
                    {"key": item.key, "title": item.title, "passed": item.passed, "detail": item.detail}
                )
                for item in result.items
            ),
            "entries": ConcurrentStableList(_entry_payload(entry) for entry in result.entries),
        }
    )


def _plan_payload(plan: RollbackPlan) -> ConcurrentStableDict[str, object]:
    """回滚计划转可序列化结构。

    Args:
        plan: 回滚计划。

    Returns:
        ConcurrentStableDict[str, object]: 输出结构。
    """
    return ConcurrentStableDict(
        {
            "unit_key": plan.unit_key,
            "tenant_scope": plan.tenant_scope,
            "from_version": plan.source.manifest_version,
            "to_version": plan.target.manifest_version,
            "requires_confirmation": plan.requires_confirmation,
            "executable": plan.executable,
            "blocked_reasons": plan.blocked_reasons,
            "steps": ConcurrentStableList(
                ConcurrentStableDict(
                    {
                        "domain_key": step.domain_key,
                        "from_revision": step.from_revision,
                        "to_revision": step.to_revision,
                    }
                )
                for step in plan.steps
            ),
        }
    )


async def run(args: argparse.Namespace) -> object:
    """在平台应用生命周期内执行命令。

    Args:
        args: 命令行参数。

    Returns:
        object: 可 JSON 序列化的结果。

    Raises:
        ValueError: 未知子命令。
    """
    command = cast("str", args.command)
    if command not in _COMMANDS:
        raise ValueError(f"未知命令：{command}")
    revisions = DatabaseRevisions(_resolve_urls(args))
    app = ApplicationFactory().create(None)
    async with (
        app.router.lifespan_context(app),
        session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session,
    ):
        service = ReleaseService(session, revisions=revisions)
        unit_key = cast("str", args.unit)
        tenant_scope = cast("int", args.tenant_scope)
        if command == "precheck":
            return _precheck_payload(
                await service.precheck(
                    unit_key=unit_key,
                    tenant_scope=tenant_scope,
                    manifest_version=cast("int | None", args.manifest_version),
                    topology_version=cast("int | None", args.topology_version),
                    declared=_declared(ConcurrentStableList(cast("list[str]", args.declare))),
                    allow_breaking=bool(args.allow_breaking),
                )
            )
        if command == "record":
            return _manifest_payload(
                await service.record(
                    unit_key=unit_key,
                    tenant_scope=tenant_scope,
                    manifest_version=cast("int | None", args.manifest_version),
                    topology_version=cast("int | None", args.topology_version),
                    declared=_declared(ConcurrentStableList(cast("list[str]", args.declare))),
                    allow_breaking=bool(args.allow_breaking),
                    note=cast("str", args.note),
                )
            )
        if command == "fail":
            return _manifest_payload(
                await service.record_failure(
                    unit_key=unit_key,
                    tenant_scope=tenant_scope,
                    note=cast("str", args.note),
                )
            )
        if command == "plan":
            return _plan_payload(
                await service.plan_rollback(
                    unit_key=unit_key,
                    tenant_scope=tenant_scope,
                    target_version=cast("int | None", args.to_version),
                )
            )
        if command == "rollback":
            return _manifest_payload(
                await service.rollback(
                    unit_key=unit_key,
                    tenant_scope=tenant_scope,
                    target_version=cast("int | None", args.to_version),
                    confirmed=bool(args.confirm),
                    note=cast("str", args.note),
                )
            )
        return ConcurrentStableList(
            _manifest_payload(row)
            for row in await service.recent(unit_key, tenant_scope, limit=cast("int", args.limit))
        )


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv`）。

    Returns:
        int: 退出码（0 成功 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        print(f"[release] 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
