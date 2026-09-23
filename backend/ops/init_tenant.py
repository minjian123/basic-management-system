"""新租户初始化（真实）：建库 → 迁移 → 幂等种子。

用法：

```bash
cd backend
uv run python -m ops.init_tenant --code acme --dry-run                  # 计划预演
uv run python -m ops.init_tenant --code acme                            # 建库 + 迁移 + 种子
uv run python -m ops.init_tenant --code acme --skip-create-db           # 库已建（如 CI 建库后）
uv run python -m ops.init_tenant --code acme \
    --admin-url "mysql+aiomysql://root:pass@host:3306"                  # 建库用管理连接串
uv run python -m ops.init_tenant --code acme \
    --url "dm+dmPython://SYSDBA:pass@host:5236" --schema BMS_MIGRCHECK  # 达梦模式（库级隔离）
```

- **URL**：`--url` 优先；否则按库键 `tenant_{service}_{code}`（`--service` 缺省取 `[app].service`）
  经 `url_template` 解析（配置 `database.tenants.*`）；
- **单服务单租户**：只建/迁本任务指定的一个服务租户库；按「服务 × 租户」批量建库见 `ops/provision_tenant.py`；
- **建库**：`app/db/admin.py`（MySQL / PG 建库、SQLite 建文件、达梦建模式；**幂等**，已存在跳过）；
- **迁移**：Alembic 租户链 `upgrade head`（与 `ops/migrate_tenants.py` 同源；`alembic_version` 已最新则跳过）；
- **种子**：字典种子（`app/dict/seed.py` 幂等；输出新增行数）；
- `--dry-run` 仅打印计划（连接串脱敏），不建连、不建库；
- 平台侧租户注册（`sys_tenant` 行）由 `ops/seed_tenant.py` 或租户管理阶段开通流程负责（本脚本只管库侧三步）。
"""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.base import BaseObject
from bms_core.core.config import get_settings
from bms_core.db.admin import DatabaseTarget, create_database, resolve_target
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import current_revision, head_revision, resolve_chain, upgrade_chain
from bms_core.db.tenant import build_tenant_db_key
from bms_core.dict.seed import seed_dicts


@dataclass(frozen=True)
class InitResult(BaseObject):
    """初始化结果（建库 / 迁移 / 种子三段）。"""

    created: bool
    """建库是否新建（False 表示已存在跳过 / 显式跳过）。"""

    revision: str | None
    """迁移后 `alembic_version` 版本号（无则 None）。"""

    seeded: int
    """字典种子新增行数（重复执行为 0）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="新租户初始化（建库 → 迁移 → 幂等种子）")
    parser.add_argument("--code", required=True, help="租户编码（全小写；库键 tenant_{service}_{code}）")
    parser.add_argument("--service", default="", help="服务标识（缺省取 [app].service；服务化库键需之）")
    parser.add_argument("--url", default="", help="租户库连接串（缺省经 url_template 解析）")
    parser.add_argument("--admin-url", default="", help="建库管理连接串（缺省按方言推导）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效）")
    parser.add_argument("--skip-create-db", action="store_true", help="跳过建库步骤（库已存在）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划（不建连）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _resolve_url(code: str, override: str, service: str = "") -> str:
    """取服务租户库连接串（显式覆盖优先，否则按库键经模板解析）。

    Args:
        code: 租户编码。
        override: 显式连接串（空串表示未指定）。
        service: 服务标识（空串取 `[app].service`；仍为空则用相对键，模板需服务标识时快速失败）。

    Returns:
        str: 服务租户库连接串。
    """
    if override:
        return override
    settings = get_settings()
    effective = service or settings.app.service
    key = build_tenant_db_key(code, service=effective or None)
    # 运维通道：允许跨服务库键（按指定服务建该租户的库）
    return EngineFactory(settings, allow_cross_service=True).resolved_url(key)


async def _seed(url: str) -> int:
    """执行字典种子（幂等）。

    Args:
        url: 租户库连接串。

    Returns:
        int: 新增行数。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await seed_dicts(session)
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> InitResult:
    """执行初始化三步。

    Args:
        args: 命令行参数。

    Returns:
        InitResult: 初始化结果。
    """
    tenant_chain = resolve_chain("tenant")
    url = _resolve_url(args.code, args.url, args.service)
    target: DatabaseTarget = resolve_target(url, admin_url=args.admin_url)
    print(f"[init_tenant] 租户 {args.code} | 目标 {target.describe()} | {_masked(url)}")

    created = False
    if args.skip_create_db:
        print("[init_tenant] 建库 → 跳过（--skip-create-db）")
    else:
        created = await create_database(target)
        print(f"[init_tenant] 建库 → {'新建' if created else '已存在（跳过）'}")

    head = head_revision(tenant_chain)
    current = await current_revision(url, schema=args.schema)
    if head is not None and current == head:
        print(f"[init_tenant] 迁移 {tenant_chain.name} 链 → 已是最新（{current}）")
    else:
        await asyncio.to_thread(upgrade_chain, tenant_chain, url, schema=args.schema)
        revision = await current_revision(url, schema=args.schema)
        print(f"[init_tenant] 迁移 {tenant_chain.name} 链 → 完成（{current or '未迁移'} → {revision}）")
        current = revision

    seeded = await _seed(url)
    print(f"[init_tenant] 种子 → 新增 {seeded} 行（幂等；重复执行输出 0）")
    return InitResult(created=created, revision=current, seeded=seeded)


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.dry_run:
        url = _resolve_url(args.code, args.url, args.service)
        target = resolve_target(url, admin_url=args.admin_url)
        service = args.service or get_settings().app.service
        key = build_tenant_db_key(args.code, service=service or None)
        print(f"[init_tenant] 租户 {args.code} | 库键 {key} | 目标 {_masked(url)}")
        print(f"[init_tenant] 计划：建库（{target.describe()}）→ 迁移（tenant 链）→ 幂等种子（dry-run）")
        return 0
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
