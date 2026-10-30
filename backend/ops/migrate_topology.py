"""租户拓扑迁移运维入口（07C `04_02`）：五阶段（预检 → 建库建表 → 搬数 → 对账 → 切换与清理）。

```bash
cd backend
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity --dry-run  # P1 计划（不建连）
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity --step p1  # 只预检
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity           # 全程（p1..p5）
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity --resume  # 断点续跑 P3
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity --verify-only
uv run python -m ops.migrate_topology --tenant demo --domain role --to-unit identity \
    --step cleanup --backup-ref bkp-20261205   # 观察期后清理旧库（须有备份凭据）
```

> 目标单元须已在服务目录登记（租户库键 `tenant_{unit}_{db_basis}` 的服务段靠登记识别）；未登记的分组单元
> 先登记，或对演练 / 接入前验证改用 `--from-url` / `--to-url` 显式给连接串。

口径（详细设计 §3）：

- **只做域级搬迁**：搬迁表集严格按该域登记表清单（`series_tables`），基础设施表不搬（每库一份）；
- **P1 不产生变更**：只出结论；`--dry-run` 连库也不做（数据量与停机预估记「未连库」）；
- **P2 幂等**：目标库不存在则建；按目标域表集建表并把该域结构清单执行到 head；
- **P3 幂等 + 可续**：按主键分批 `DELETE + INSERT`；进度落 `--state-dir`（缺省 `.cache/topology_migration/`）；
- **P4 四类对账**：行数 / 主键覆盖 / 抽样内容 / 业务断言（`--assert 名称=SQL` 可重复），全绿才允许 P5；
- **P5 同一次动作**：拓扑整批替换（版本 +1）与 `04_01` 发布清单写入在同一事务——发布校验不过则整体回滚，
  拓扑不生效；未在本轮跑 P4 时须 `--confirm`（表示已在上一轮全绿）；
- **清理独立成步**：观察期结束、且有备份凭据（`--backup-ref`）才删旧库（设计 §3.5「禁止把删旧库放在切换同一步」）；
- `dual` 档：反复「回填 + 对账」直至连续 `--converge-rounds` 轮全绿（停机档一条即止）；
- 退出码：0 通过 / 1 失败（异常信息打到 stderr，不吞错）。
"""

import argparse
import asyncio
import getpass
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.admin import database_exists, drop_database, resolve_target
from bms_core.db.bootstrap import apply_domains_schema, default_schema_of, domains_metadata
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_DB_KEY, build_platform_db_key, build_tenant_db_key, parse_db_key
from bms_core.db.migration import (
    DATASOURCE_TENANT,
    build_series_name,
    head_revision,
    known_domains,
    resolve_series,
    upgrade_series,
)
from bms_core.db.session import session_scope
from bms_core.db.sync import is_sync_only_url
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.db.topology_migration import (
    SAMPLE_SIZE,
    TABLE_BATCH_SIZE,
    BusinessAssertion,
    CopyReport,
    MigrationProgress,
    VerifyReport,
    copy_tables,
    count_rows,
    verify_tables,
)
from bms_core.tenant.registry import TenantRef, tenant_refs
from bms_platform.domains.platform_registry.services.release import ReleaseService
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService, TopologyRow
from bms_platform.main import ApplicationFactory
from ops.release import DatabaseRevisions

__all__ = ["MigrationPlan", "StepResult", "build_parser", "main", "run"]

RUN_IMAGE = "platform"
"""本脚本依赖平台服务包（`bms_platform`）——P5 的拓扑替换与发布清单写入复用平台服务层。"""

_STEPS = ConcurrentStableFrozenList(("p1", "p2", "p3", "p4", "p5", "cleanup"))
"""步骤全集（与 `--step` 参数一一对应）。"""

_DEFAULT_STEPS = ConcurrentStableFrozenList(("p1", "p2", "p3", "p4", "p5"))
"""缺省步骤序列（清理不在缺省链里，须显式 `--step cleanup`）。"""

_STRATEGIES = ConcurrentStableFrozenList(("stop", "dual"))
"""搬迁策略：`stop` 停机窗口（本期主档）/ `dual` 不停写回填追平。"""

_UNIT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
"""部署单元命名（与 `TenantTopologyService` 同一形态）。"""

_DOWNTIME_ROWS_PER_SECOND = 500
"""停机预估口径：每秒搬迁行数（含索引与约束写放大的保守值）。"""

_DOWNTIME_FIXED_SECONDS = 60
"""停机预估固定开销（停写、校验、切换、恢复的流程耗时）。"""

_DEFAULT_STATE_DIR = Path(".cache/topology_migration")
"""断点与审计的缺省落点（工程缓存目录，不入库）。"""


@dataclass(frozen=True)
class MigrationPlan(BaseValueObject):
    """迁移计划（一次运行的目标与取址；不连业务库即可算出）。"""

    tenant_code: str
    """租户编码（`--tenant`）。"""

    tenant_id: int
    """租户主键（拓扑表 `tenant_id`；0 表示默认拓扑）。"""

    db_basis: str
    """租户库名基（库键 `tenant_{unit}_{db_basis}` 的 code 段）。"""

    domains: ConcurrentStableFrozenList[str]
    """搬迁的业务域（`--domain`，保序去重）。"""

    source_unit: str
    """源部署单元（当前拓扑该域的承载单元，或 `--from-unit`）。"""

    target_unit: str
    """目标部署单元（`--to-unit`）。"""

    strategy: str
    """搬迁策略（`stop` / `dual`）。"""

    source_url: str
    """源库连接串（含密码；禁止写入日志）。"""

    target_url: str
    """目标库连接串（含密码；禁止写入日志）。"""


@dataclass(frozen=True)
class StepResult(BaseValueObject):
    """单条检查 / 步骤结论。"""

    key: str
    """步骤或检查项标识。"""

    title: str
    """中文标题。"""

    passed: bool
    """是否通过。"""

    detail: str
    """结论明细（数据量、库、版本、原因等）。"""


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="租户拓扑迁移（五阶段：预检 / 建表 / 搬数 / 对账 / 切换）")
    parser.add_argument("--tenant", required=True, help="租户编码（库键按对照表 db_basis 派生）")
    parser.add_argument("--domain", action="append", required=True, help="搬迁的业务域（可重复）")
    parser.add_argument("--to-unit", required=True, help="目标部署单元标识")
    parser.add_argument("--from-unit", default="", help="源部署单元（缺省按当前拓扑取；演练可显式指定）")
    parser.add_argument("--strategy", default="stop", choices=list(_STRATEGIES), help="搬迁策略（缺省 stop）")
    parser.add_argument("--step", action="append", default=[], choices=list(_STEPS), help="只执行指定步骤（可重复）")
    parser.add_argument("--dry-run", action="store_true", help="只输出 P1 计划（不建连、不建库）")
    parser.add_argument("--verify-only", action="store_true", help="只跑 P4 对账")
    parser.add_argument("--resume", action="store_true", help="P3 从断点续跑")
    parser.add_argument("--confirm", action="store_true", help="确认切换（P4 未在本轮执行时必填）")
    parser.add_argument("--tenant-id", type=int, default=None, help="租户主键（缺省按编码查租户注册库）")
    parser.add_argument("--db-basis", default="", help="租户库名基（缺省按对照表取，读不到回落编码）")
    parser.add_argument("--from-url", default="", help="源库连接串（演练用；不给则按单元派生）")
    parser.add_argument("--to-url", default="", help="目标库连接串（演练用；不给则按单元派生）")
    parser.add_argument("--schema", default="", help="达梦目标模式（缺省取连接串 database 段）")
    parser.add_argument("--batch-size", type=int, default=TABLE_BATCH_SIZE, help="单批复制行数")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help="P4 单表抽样条数")
    parser.add_argument("--rate-limit", type=float, default=0.0, help="每批之间的休眠秒数（限速）")
    parser.add_argument("--max-rounds", type=int, default=3, help="dual 档回填追平的最大轮数")
    parser.add_argument("--converge-rounds", type=int, default=2, help="dual 档切换前要求连续全绿轮数")
    parser.add_argument(
        "--assert",
        dest="assertions",
        action="append",
        default=[],
        metavar="名称=SQL",
        help="P4 业务断言（可重复）",
    )
    parser.add_argument("--notice", default="", help="停机告知留痕（`stop` 档必填，记录渠道与提前量）")
    parser.add_argument("--state-dir", default=str(_DEFAULT_STATE_DIR), help="断点与审计落点（缺省 .cache）")
    parser.add_argument("--skip-release", action="store_true", help="P5 只写拓扑、不写发布清单（演练；生产禁用）")
    parser.add_argument("--backup-ref", default="", help="清理前的备份凭据（缺则拒绝删旧库）")
    return parser


def _steps(args: argparse.Namespace) -> ConcurrentStableList[str]:
    """归一本次要执行的步骤序列。

    Args:
        args: 命令行参数。

    Returns:
        ConcurrentStableList[str]: 步骤序列（保序去重）。

    Raises:
        ConfigError: `--dry-run` / `--verify-only` 与 `--step` 冲突。
    """
    requested = ConcurrentStableList(cast("list[str]", args.step))
    if requested and (args.dry_run or args.verify_only):
        raise ConfigError("`--step` 与 `--dry-run` / `--verify-only` 不能同时使用")
    if args.dry_run:
        return ConcurrentStableList(["p1"])
    if args.verify_only:
        return ConcurrentStableList(["p4"])
    return ConcurrentStableList(dict.fromkeys(requested or _DEFAULT_STEPS))


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _factory() -> EngineFactory:
    """运维通道引擎工厂（允许跨单元取库键）。

    Returns:
        EngineFactory: 引擎工厂。
    """
    return EngineFactory(get_settings(), allow_cross_service=True)


def _platform_url() -> str:
    """平台库连接串（租户注册库与拓扑库同在此库）。

    Returns:
        str: 连接串（含密码；禁止写入日志）。
    """
    return _factory().resolved_url(PLATFORM_DB_KEY)


def _tenant_url(unit: str, db_basis: str) -> str:
    """按「单元 × 租户库名基」派生服务租户库连接串。

    库键 `tenant_{unit}_{db_basis}` 的服务段只对**已登记服务目录**的单元可识别（`parse_db_key`
    的既有口径）——未登记的部署单元（如尚未接入的分组单元）必须先登记，或改用 `--from-url` / `--to-url`
    显式给连接串（演练与接入前验证）。

    Args:
        unit: 部署单元标识。
        db_basis: 租户库名基。

    Returns:
        str: 连接串（含密码；禁止写入日志）。

    Raises:
        ConfigError: 单元未登记（库键服务段不可识别）。
    """
    key = build_tenant_db_key(db_basis, service=unit)
    if parse_db_key(key).service != unit:
        raise ConfigError(
            f"部署单元 {unit} 未在服务目录登记：租户库键 {key} 的服务段无法识别"
            "（请先登记该单元，或显式给 --from-url / --to-url）"
        )
    return _factory().resolved_url(key)


async def _tenant_ref(code: str) -> TenantRef:
    """按编码取租户引用（注册库读不到时回落「编码即库名基、主键 0」）。

    Args:
        code: 租户编码。

    Returns:
        TenantRef: 租户引用。

    Raises:
        ConfigError: 租户未在注册库登记。
    """
    registry_url = _factory().resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
    try:
        refs = await tenant_refs(registry_url)
    except Exception as exc:  # 注册库不可读：演练 / 离线场景按编码作库名基
        print(f"[migrate_topology] 租户注册库不可读，按编码作库名基：{type(exc).__name__}: {exc}")
        return TenantRef(code=code, db_basis=code)
    for ref in refs:
        if ref.code == code:
            return ref
    raise ConfigError(f"租户 {code} 未在租户注册库登记（sys_tenant 无该编码）")


async def _query_platform(
    statement: str, params: ConcurrentStableDict[str, object]
) -> ConcurrentStableList[ConcurrentStableList[object]]:
    """读平台库（按方言选异步 / 同步连接；只读，一次一连接）。

    Args:
        statement: 查询语句（`:name` 绑定）。
        params: 绑定值。

    Returns:
        ConcurrentStableList[ConcurrentStableList[object]]: 逐行取值。
    """
    url = _platform_url()
    if is_sync_only_url(url):
        return await asyncio.to_thread(_query_platform_sync, url, statement, params)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(statement), dict(params))
            return ConcurrentStableList(ConcurrentStableList(row) for row in result.all())
    finally:
        await engine.dispose()


def _query_platform_sync(
    url: str, statement: str, params: ConcurrentStableDict[str, object]
) -> ConcurrentStableList[ConcurrentStableList[object]]:
    """读平台库（同步方言，如达梦；调用方已在线程池内）。

    Args:
        url: 连接串（含密码；禁止写入日志）。
        statement: 查询语句。
        params: 绑定值。

    Returns:
        ConcurrentStableList[ConcurrentStableList[object]]: 逐行取值。
    """
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return ConcurrentStableList(
                ConcurrentStableList(row) for row in connection.execute(text(statement), dict(params)).all()
            )
    finally:
        engine.dispose()


async def _topology_units(tenant_id: int) -> ConcurrentStableDict[str, str]:
    """读当前拓扑（某租户最大版本的行；该租户无自身行时回落默认拓扑）。

    Args:
        tenant_id: 租户主键。

    Returns:
        ConcurrentStableDict[str, str]: 业务域 → 部署单元。

    Raises:
        ConfigError: 平台库不可读或拓扑表不存在。
    """
    try:
        rows = await _topology_rows(tenant_id)
        if not rows and tenant_id != 0:
            rows = await _topology_rows(0)
    except Exception as exc:
        raise ConfigError(f"当前拓扑不可读（平台库 / sys_tenant_topology）：{type(exc).__name__}: {exc}") from exc
    return rows


async def _topology_rows(tenant_id: int) -> ConcurrentStableDict[str, str]:
    """读某租户当前版本拓扑行。

    Args:
        tenant_id: 租户主键。

    Returns:
        ConcurrentStableDict[str, str]: 业务域 → 部署单元（无行为空映射）。
    """
    rows = await _query_platform(
        "SELECT domain_key, unit_key FROM sys_tenant_topology "
        "WHERE tenant_id = :tenant_id AND deleted_at IS NULL "
        "AND topology_version = (SELECT MAX(topology_version) FROM sys_tenant_topology "
        "WHERE tenant_id = :tenant_id AND deleted_at IS NULL)",
        ConcurrentStableDict({"tenant_id": tenant_id}),
    )
    return ConcurrentStableDict((str(row[0]), str(row[1])) for row in rows)


async def _dependent_consumers(domains: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """读该批业务域的消费方（能力授权 `sys_capability_grant` 的消费方键）。

    Args:
        domains: 业务域标识集合。

    Returns:
        ConcurrentStableList[str]: 消费方键（授权表不可读时为空）。
    """
    consumers: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        for domain in domains:
            rows = await _query_platform(
                "SELECT DISTINCT consumer_key FROM sys_capability_grant "
                "WHERE deleted_at IS NULL AND status = 'enabled' AND capability_name LIKE :pattern",
                ConcurrentStableDict({"pattern": f"%.{domain}.%"}),
            )
            for row in rows:
                if str(row[0]) not in consumers:
                    consumers.add(str(row[0]))
    except Exception as exc:  # 授权表缺失 / 平台库不可读：不影响预检结论，仅记不可用
        print(f"[migrate_topology] 依赖方清单不可用：{type(exc).__name__}: {exc}")
        return ConcurrentStableList()
    return consumers


def _domain_tables(plan: MigrationPlan) -> MetaData:
    """取搬迁表集元数据（仅域表，不含基础设施表）。

    Args:
        plan: 迁移计划。

    Returns:
        MetaData: 表集元数据。
    """
    return domains_metadata(plan.domains, DATASOURCE_TENANT, include_infrastructure=False)


async def _build_plan(args: argparse.Namespace) -> MigrationPlan:
    """按参数与当前拓扑构造迁移计划（不连业务库）。

    Args:
        args: 命令行参数。

    Returns:
        MigrationPlan: 迁移计划。

    Raises:
        ConfigError: 租户 / 域 / 单元 / 库键任一项无法判定。
    """
    code = cast("str", args.tenant)
    ref = await _tenant_ref(code)
    explicit_id = cast("int | None", args.tenant_id)
    tenant_id = ref.tenant_id if explicit_id is None else explicit_id
    db_basis = cast("str", args.db_basis) or ref.db_basis
    domains = ConcurrentStableFrozenList(dict.fromkeys(cast("list[str]", args.domain)))
    target_unit = cast("str", args.to_unit)
    source_unit = cast("str", args.from_unit)
    if not source_unit:
        source_unit = await _source_unit(tenant_id, domains)
    return MigrationPlan(
        tenant_code=code,
        tenant_id=tenant_id,
        db_basis=db_basis,
        domains=domains,
        source_unit=source_unit,
        target_unit=target_unit,
        strategy=cast("str", args.strategy),
        source_url=cast("str", args.from_url) or _tenant_url(source_unit, db_basis),
        target_url=cast("str", args.to_url) or _tenant_url(target_unit, db_basis),
    )


async def _source_unit(tenant_id: int, domains: ConcurrentStableFrozenList[str]) -> str:
    """按当前拓扑判定源单元（多域须同源，否则要求显式 `--from-unit`）。

    Args:
        tenant_id: 租户主键。
        domains: 搬迁的业务域。

    Returns:
        str: 源部署单元。

    Raises:
        ConfigError: 拓扑缺该域，或多个域当前不同源。
    """
    units = await _topology_units(tenant_id)
    missing = ConcurrentStableList(domain for domain in domains if domain not in units)
    if missing:
        raise ConfigError(f"当前拓扑没有这些业务域的映射（请用 --from-unit 显式指定）：{', '.join(missing)}")
    distinct = ConcurrentStableList(dict.fromkeys(units[domain] for domain in domains))
    if len(distinct) > 1:
        raise ConfigError(f"多域当前分属不同单元（{'、'.join(distinct)}），请用 --from-unit 显式指定源单元")
    return distinct[0]


async def _precheck(plan: MigrationPlan, args: argparse.Namespace) -> ConcurrentStableList[StepResult]:
    """P1 预检（不产生任何变更；`--dry-run` 不建连）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        ConcurrentStableList[StepResult]: 逐项结论。
    """
    metadata = _domain_tables(plan)
    tables = ConcurrentStableList(sorted(metadata.tables))
    results: ConcurrentStableList[StepResult] = ConcurrentStableList(
        [
            StepResult(
                key="tenant",
                title="租户与库名基",
                passed=bool(plan.tenant_code and plan.db_basis),
                detail=f"租户 {plan.tenant_code}（主键 {plan.tenant_id}）/ 库名基 {plan.db_basis}",
            ),
            _domains_result(plan),
            StepResult(
                key="tables",
                title="搬迁表集",
                passed=bool(tables),
                detail=f"{len(tables)} 张：{', '.join(tables)}" if tables else "该域在租户库没有登记表（无可搬迁内容）",
            ),
            _target_unit_result(plan),
        ]
    )
    results.extend(await _target_db_result(plan, args))
    results.extend(await _volume_results(plan, args, tables))
    return results


def _domains_result(plan: MigrationPlan) -> StepResult:
    """域登记结论。

    Args:
        plan: 迁移计划。

    Returns:
        StepResult: 结论。
    """
    known = known_domains()
    unknown = ConcurrentStableList(domain for domain in plan.domains if domain not in known)
    return StepResult(
        key="domains",
        title="业务域已登记",
        passed=not unknown,
        detail="全部已登记" if not unknown else f"未登记：{', '.join(unknown)}",
    )


def _target_unit_result(plan: MigrationPlan) -> StepResult:
    """目标单元合法性结论（命名 + 与源不同）。

    Args:
        plan: 迁移计划。

    Returns:
        StepResult: 结论。
    """
    same = plan.source_unit == plan.target_unit
    passed = bool(_UNIT_PATTERN.match(plan.target_unit)) and not same
    if same:
        detail = f"源与目标同为 {plan.target_unit}（换库请显式 --from-unit 并改用 --to-url）"
    else:
        detail = f"{plan.source_unit} → {plan.target_unit}"
    return StepResult(key="target_unit", title="目标单元合法", passed=passed, detail=detail)


async def _target_db_result(plan: MigrationPlan, args: argparse.Namespace) -> ConcurrentStableList[StepResult]:
    """目标库可取结论（`--dry-run` 不建连）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        ConcurrentStableList[StepResult]: 结论。
    """
    if args.dry_run:
        return ConcurrentStableList(
            [
                StepResult(
                    key="target_db",
                    title="目标库可取",
                    passed=True,
                    detail=f"{_masked(plan.target_url)}（dry-run 未连库）",
                )
            ]
        )
    try:
        exists = await database_exists(resolve_target(plan.target_url))
    except Exception as exc:  # 连接失败 / 无权建库：目标不可取
        return ConcurrentStableList(
            [
                StepResult(
                    key="target_db",
                    title="目标库可取",
                    passed=False,
                    detail=f"{_masked(plan.target_url)} 不可用：{type(exc).__name__}: {exc}",
                )
            ]
        )
    return ConcurrentStableList(
        [
            StepResult(
                key="target_db",
                title="目标库可取",
                passed=True,
                detail=f"{_masked(plan.target_url)}（{'已存在' if exists else '不存在，P2 创建'}）",
            )
        ]
    )


async def _volume_results(
    plan: MigrationPlan, args: argparse.Namespace, tables: ConcurrentStableList[str]
) -> ConcurrentStableList[StepResult]:
    """数据量与停机预估、依赖方、告知留痕三条结论。

    Args:
        plan: 迁移计划。
        args: 命令行参数。
        tables: 搬迁表集。

    Returns:
        ConcurrentStableList[StepResult]: 结论。
    """
    return ConcurrentStableList(
        [
            await _volume_result(plan, args, tables),
            await _dependents_result(plan),
            _notice_result(plan, args),
        ]
    )


async def _volume_result(
    plan: MigrationPlan, args: argparse.Namespace, tables: ConcurrentStableList[str]
) -> StepResult:
    """数据量与停机预估。

    Args:
        plan: 迁移计划。
        args: 命令行参数。
        tables: 搬迁表集。

    Returns:
        StepResult: 结论。
    """
    if args.dry_run:
        return StepResult(key="volume", title="数据量与停机预估", passed=True, detail="dry-run 未连源库")
    try:
        counts = await count_rows(plan.source_url, _domain_tables(plan))
    except Exception as exc:
        return StepResult(
            key="volume",
            title="数据量与停机预估",
            passed=False,
            detail=f"源库不可读：{type(exc).__name__}: {exc}",
        )
    total = sum(counts.values())
    minutes = (total / _DOWNTIME_ROWS_PER_SECOND + _DOWNTIME_FIXED_SECONDS) / 60
    return StepResult(
        key="volume",
        title="数据量与停机预估",
        passed=True,
        detail=f"共 {total} 行（{len(tables)} 表），预计停机约 {minutes:.1f} 分钟",
    )


async def _dependents_result(plan: MigrationPlan) -> StepResult:
    """依赖方清单结论（只列已授权消费方，不阻断）。

    Args:
        plan: 迁移计划。

    Returns:
        StepResult: 结论。
    """
    consumers = await _dependent_consumers(plan.domains)
    return StepResult(
        key="dependents",
        title="依赖方清单",
        passed=True,
        detail="、".join(consumers) if consumers else "未查到已授权的消费方（或授权表不可用）",
    )


def _notice_result(plan: MigrationPlan, args: argparse.Namespace) -> StepResult:
    """停机告知留痕结论（`stop` 档必须有 `--notice`）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        StepResult: 结论。
    """
    notice = cast("str", args.notice)
    if plan.strategy == "dual":
        return StepResult(key="notice", title="停机告知留痕", passed=True, detail="dual 档不停写，无需告知")
    return StepResult(
        key="notice",
        title="停机告知留痕",
        passed=bool(notice),
        detail=notice or "缺 --notice（涉及停机须提前告知租户并留痕）",
    )


async def _build_schema(plan: MigrationPlan, args: argparse.Namespace) -> StepResult:
    """P2 建库建表 + 结构清单到 head（幂等）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        StepResult: 结论。
    """
    schema = cast("str", args.schema) or default_schema_of(plan.target_url)
    outcome = await apply_domains_schema(
        plan.domains, DATASOURCE_TENANT, plan.target_url, target=_masked(plan.target_url), schema=schema
    )
    upgraded: ConcurrentStableList[str] = ConcurrentStableList()
    for domain in plan.domains:
        series = resolve_series(build_series_name(domain, DATASOURCE_TENANT))
        if head_revision(series) is None:
            continue
        await asyncio.to_thread(upgrade_series, series, plan.target_url, schema=schema)
        upgraded.add(domain)
    return StepResult(
        key="p2",
        title="建库建表",
        passed=True,
        detail=(
            f"表集 {outcome.total} 张（新建 {outcome.created} / 已存在 {outcome.existing}）；"
            f"结构清单到 head：{'、'.join(upgraded) if upgraded else '无脚本（跳过）'}"
        ),
    )


async def _copy(plan: MigrationPlan, args: argparse.Namespace) -> CopyReport:
    """P3 搬数（幂等 + 断点）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        CopyReport: 复制报告。
    """
    return await copy_tables(
        plan.source_url,
        plan.target_url,
        _domain_tables(plan),
        batch_size=cast("int", args.batch_size),
        progress=_progress(plan, args),
        rate_limit_seconds=cast("float", args.rate_limit),
    )


async def _verify(plan: MigrationPlan, args: argparse.Namespace) -> VerifyReport:
    """P4 对账（四类）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        VerifyReport: 对账报告。
    """
    return await verify_tables(
        plan.source_url,
        plan.target_url,
        _domain_tables(plan),
        batch_size=cast("int", args.batch_size),
        sample_size=cast("int", args.sample_size),
        assertions=_assertions(ConcurrentStableList(cast("list[str]", args.assertions))),
    )


def _assertions(raw: ConcurrentStableList[str]) -> ConcurrentStableList[BusinessAssertion]:
    """解析业务断言参数（`名称=SQL`）。

    Args:
        raw: 命令行原始断言。

    Returns:
        ConcurrentStableList[BusinessAssertion]: 断言列表。

    Raises:
        ConfigError: 缺少 `=` 或名称为空。
    """
    items: ConcurrentStableList[BusinessAssertion] = ConcurrentStableList()
    for item in raw:
        name, separator, sql = item.partition("=")
        if not separator or not name.strip() or not sql.strip():
            raise ConfigError(f"--assert 需「名称=SQL」形态：{item}")
        items.add(BusinessAssertion(name=name.strip(), sql=sql.strip()))
    return items


def _progress(plan: MigrationPlan, args: argparse.Namespace) -> MigrationProgress:
    """取本次运行的进度文件（非 `--resume` 时清空重来）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        MigrationProgress: 进度对象。
    """
    directory = Path(cast("str", args.state_dir))
    path = directory / f"{plan.tenant_code}_{'-'.join(plan.domains)}_{plan.target_unit}.json"
    if not args.resume and path.is_file():
        path.unlink()
    return MigrationProgress.load(path)


async def _copy_and_verify(
    plan: MigrationPlan, args: argparse.Namespace, *, want_copy: bool, want_verify: bool
) -> tuple[ConcurrentStableList[StepResult], bool]:
    """P3 / P4（`dual` 档反复回填直至连续全绿）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。
        want_copy: 是否执行 P3。
        want_verify: 是否执行 P4。

    Returns:
        tuple[ConcurrentStableList[StepResult], bool]: 结论与是否通过。
    """
    results: ConcurrentStableList[StepResult] = ConcurrentStableList()
    converge = cast("int", args.converge_rounds) if plan.strategy == "dual" else 1
    rounds = cast("int", args.max_rounds) if plan.strategy == "dual" and want_copy and want_verify else 1
    greens = 0
    passed = False
    for index in range(1, rounds + 1):
        if want_copy:
            report = await _copy(plan, args)
            results.add(_copy_result(report, round_index=index))
            if not report.passed:
                return results, False
        if want_verify:
            verified = await _verify(plan, args)
            results.add(_verify_result(verified, round_index=index))
            passed = verified.passed
            greens = greens + 1 if verified.passed else 0
        else:
            passed = True
            greens = converge
        if greens >= converge:
            return results, passed
    return results, passed


def _copy_result(report: CopyReport, *, round_index: int) -> StepResult:
    """复制结论转步骤结果。

    Args:
        report: 复制报告。
        round_index: 轮次（dual 档多轮）。

    Returns:
        StepResult: 结论。
    """
    detail = (
        f"复制 {report.total_rows} 行（{len(report.tables)} 表）"
        if report.passed
        else "；".join(f"{item.table} 失败：{item.error}" for item in report.failed)
    )
    return StepResult(key="p3", title=f"搬数（第 {round_index} 轮）", passed=report.passed, detail=detail)


def _verify_result(report: VerifyReport, *, round_index: int) -> StepResult:
    """对账结论转步骤结果（失败时逐表列出差异）。

    Args:
        report: 对账报告。
        round_index: 轮次（dual 档多轮）。

    Returns:
        StepResult: 结论。
    """
    if report.passed:
        detail = f"{len(report.tables)} 表行数与主键覆盖一致；断言 {len(report.assertions)} 条全过"
    else:
        detail = "；".join(
            f"{item.table}：源 {item.source_rows} / 目标 {item.target_rows}、缺 {item.missing}、"
            f"多 {item.extra}、抽样差异 {len(item.mismatched)}"
            for item in report.failed_tables
        ) or "；".join(
            f"断言 {item.name} 不一致（{item.source} vs {item.target}）" for item in report.assertions if not item.ok
        )
    return StepResult(key="p4", title=f"对账（第 {round_index} 轮）", passed=report.passed, detail=detail)


async def _switch(plan: MigrationPlan, args: argparse.Namespace) -> StepResult:
    """P5 拓扑替换 + 发布清单（同一事务；发布校验不过则整体回滚）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        StepResult: 结论。
    """
    note = f"拓扑迁移：{'、'.join(plan.domains)} 从 {plan.source_unit} 迁至 {plan.target_unit}"
    urls: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        {"platform": _platform_url(), "tenant": plan.target_url}
    )
    app = ApplicationFactory().create(None)
    async with (
        app.router.lifespan_context(app),
        session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session,
    ):
        topology = TenantTopologyService(session)
        version, rows = await topology.export(plan.tenant_id)
        merged = ConcurrentStableList(
            TopologyRow(
                domain_key=row.domain_key,
                unit_key=plan.target_unit if row.domain_key in plan.domains else row.unit_key,
                status=row.status,
            )
            for row in rows
        )
        new_version, _ = await topology.replace(plan.tenant_id, rows=merged, note=note)
        manifest = "未写（--skip-release）"
        if not args.skip_release:
            service = ReleaseService(session, revisions=DatabaseRevisions(urls))
            recorded = await service.record(unit_key=plan.target_unit, topology_version=new_version, note=note)
            manifest = f"清单 #{recorded.manifest_version}（单元 {recorded.unit_key}）"
    return StepResult(
        key="p5",
        title="切换与发布",
        passed=True,
        detail=f"拓扑版本 {version} → {new_version}；发布{manifest}",
    )


async def _cleanup(plan: MigrationPlan, args: argparse.Namespace) -> StepResult:
    """观察期后的旧库清理（必须有备份凭据；删库是破坏性操作）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。

    Returns:
        StepResult: 结论。
    """
    backup = cast("str", args.backup_ref)
    if not backup:
        return StepResult(
            key="cleanup",
            title="清理旧库",
            passed=False,
            detail="缺 --backup-ref（删除前必须有备份；设计 §3.5「清理」）",
        )
    dropped = await drop_database(resolve_target(plan.source_url))
    return StepResult(
        key="cleanup",
        title="清理旧库",
        passed=True,
        detail=f"{_masked(plan.source_url)} {'已删除' if dropped else '本不存在（跳过）'}；备份凭据 {backup}",
    )


def _audit(plan: MigrationPlan, args: argparse.Namespace, results: ConcurrentStableList[StepResult]) -> Path:
    """迁移审计留痕（追加一行 JSON；谁 / 何时 / 哪些域 / 策略 / 结果）。

    Args:
        plan: 迁移计划。
        args: 命令行参数。
        results: 步骤结论。

    Returns:
        Path: 审计文件路径。
    """
    path = Path(cast("str", args.state_dir)) / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": datetime.now(UTC).isoformat(),
        "operator": getpass.getuser(),
        "tenant": plan.tenant_code,
        "tenant_id": plan.tenant_id,
        "db_basis": plan.db_basis,
        "domains": list(plan.domains),
        "strategy": plan.strategy,
        "source_unit": plan.source_unit,
        "target_unit": plan.target_unit,
        "source_db": _masked(plan.source_url),
        "target_db": _masked(plan.target_url),
        "notice": cast("str", args.notice),
        "passed": all(result.passed for result in results),
        "steps": [{"key": result.key, "passed": result.passed, "detail": result.detail} for result in results],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def _print(results: ConcurrentStableList[StepResult]) -> None:
    """逐项打印结论。

    Args:
        results: 步骤结论。
    """
    for result in results:
        mark = "通过" if result.passed else "不通过"
        print(f"[migrate_topology] {result.key:<10} {mark}｜{result.title}｜{result.detail}")


async def run(args: argparse.Namespace) -> int:
    """执行迁移步骤（P1 不过即停；P4 不全绿不切换）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    steps = _steps(args)
    plan = await _build_plan(args)
    print(
        f"[migrate_topology] 计划：租户 {plan.tenant_code}（库名基 {plan.db_basis}）"
        f"{'、'.join(plan.domains)}：{plan.source_unit} → {plan.target_unit}（{plan.strategy}）"
    )
    print(f"[migrate_topology] 库：{_masked(plan.source_url)} → {_masked(plan.target_url)}")
    results: ConcurrentStableList[StepResult] = ConcurrentStableList()
    if "p1" in steps:
        prechecked = await _precheck(plan, args)
        _print(prechecked)
        results.extend(prechecked)
        if not all(result.passed for result in prechecked):
            print("[migrate_topology] P1 未通过：不产生任何变更")
            _audit(plan, args, results)
            return 1
    if "p2" in steps:
        built = await _build_schema(plan, args)
        _print(ConcurrentStableList([built]))
        results.add(built)
    if "p3" in steps or "p4" in steps:
        if "p5" in steps and "p4" not in steps:
            raise ConfigError("P5 要求 P4 全绿：请把 p4 与 p5 一起执行，或单步执行 P5 时加 --confirm")
        paired, green = await _copy_and_verify(plan, args, want_copy="p3" in steps, want_verify="p4" in steps)
        _print(paired)
        results.extend(paired)
        if not green:
            print("[migrate_topology] P3/P4 未通过：不切换（目标库可重来，幂等）")
            _audit(plan, args, results)
            return 1
    if "p5" in steps:
        if "p4" not in steps and not args.confirm:
            raise ConfigError("P5 要求 P4 全绿：单步执行 P5 必须加 --confirm（确认 P4 已在上一轮全绿）")
        switched = await _switch(plan, args)
        _print(ConcurrentStableList([switched]))
        results.add(switched)
    if "cleanup" in steps:
        cleaned = await _cleanup(plan, args)
        _print(ConcurrentStableList([cleaned]))
        results.add(cleaned)
        if not cleaned.passed:
            _audit(plan, args, results)
            return 1
    audit_path = _audit(plan, args, results)
    print(f"[migrate_topology] 审计留痕：{audit_path}")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv`）。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except ConfigError as exc:
        print(f"[migrate_topology] 失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
