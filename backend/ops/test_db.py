"""三库测试库流程（真实执行）：`plan` / `create` / `migrate` / `drop`（每方言两对象）。

用法：

```bash
cd backend
# 计划（无副作用；CI 常跑 job 与本地核对用）
uv run python -m ops.test_db plan --engine mysql
# 真实执行（本地首次：需管理凭据；CI：测试账号已存在，凭据由 CI 变量注入）
uv run python -m ops.test_db create  --engine mysql --execute
uv run python -m ops.test_db migrate --engine mysql --execute
uv run python -m ops.test_db drop    --engine mysql --execute
```

- **对象拓扑**：每方言两个对象——平台（`platform` 链）与租户（`tenant` 链）；MySQL / PostgreSQL
  为独立库，达梦为独立**模式**（库级隔离单位）。
- **清单为唯一事实源**：`TEST_DATABASES` 的库名 / 模式名须与 `.gitlab-ci.yml` 的
  `BMS_TEST_DB_URL` / `BMS_TEST_TENANT_DB_URL` 逐字一致（单测断言防两处漂移）。
- **账号**：`create` 幂等建测试账号与最小授权（MySQL 库级 `bms\\_test%` 的 `ALL`、
  PostgreSQL `CREATEDB`、达梦 `SYSDBA` 无独立测试账号）；管理连接经 `--admin-url` 显式指定，
  或按方言由管理员密码环境变量（`MYSQL_ROOT_PASSWORD` / `POSTGRES_PASSWORD` /
  `DM8_SYSDBA_PASSWORD`）推导；**无管理凭据即跳过建号并提示**（CI 路径账号已存在）。
- **幂等**：建库 / 建模式命中已存在即跳过；迁移 `alembic_version` 已为链 head 即「已是最新」；
  删库 / 删模式目标不存在即跳过。
- **凭据**：一律不写入日志（仅以脱敏连接串展示）；测试密码经 `--password` 或
  `MYSQL_TEST_PASSWORD` / `POSTGRES_TEST_PASSWORD` / `DM8_TEST_PASSWORD` 注入。
- 调用一律用**模块方式**（`uv run python -m ops.test_db`）：直接 `python ops/test_db.py` 时
  `sys.path[0]` 为脚本目录，脚本内引用 `app.*` 会 `ModuleNotFoundError`
  （与 `ops/check_modules.py` 同一坑，04_01 已实测）。
"""

import argparse
import asyncio
import os
from collections.abc import Sequence

from sqlalchemy.engine import make_url

from app.core.exceptions import ConfigError
from app.db.admin import (
    DatabaseTarget,
    create_database,
    drop_database,
    fetch_rows,
    resolve_target,
    run_statements,
)
from app.db.migration import current_revision, head_revision, resolve_chain, upgrade_chain

TEST_DATABASES: dict[str, dict[str, str]] = {
    "mysql": {"platform": "bms_test_mysql", "tenant": "bms_test_mysql_t1"},
    "postgres": {"platform": "bms_test_pg", "tenant": "bms_test_pg_t1"},
    "dm8": {"platform": "BMS_TEST_DM", "tenant": "BMS_TEST_DM_T1"},
}
"""测试对象清单（唯一事实源；与 `.gitlab-ci.yml` 的 `BMS_TEST_DB_URL` 系列变量逐字一致）。"""

TEST_URL_ENV: dict[str, str] = {
    "platform": "BMS_TEST_DB_URL",
    "tenant": "BMS_TEST_TENANT_DB_URL",
}
"""对象连接串环境变量名（平台 / 租户）。"""

TEST_ACCOUNT: dict[str, str] = {
    "mysql": "bms_test",
    "postgres": "bms_test",
    "dm8": "SYSDBA",
}
"""测试账号（达梦以 `SYSDBA` 承载，无独立测试账号）。"""

TEST_PASSWORD_ENV: dict[str, str] = {
    "mysql": "MYSQL_TEST_PASSWORD",
    "postgres": "POSTGRES_TEST_PASSWORD",
    "dm8": "DM8_TEST_PASSWORD",
}
"""测试账号密码环境变量名。"""

ADMIN_PASSWORD_ENV: dict[str, str] = {
    "mysql": "MYSQL_ROOT_PASSWORD",
    "postgres": "POSTGRES_PASSWORD",
    "dm8": "DM8_SYSDBA_PASSWORD",
}
"""管理员密码环境变量名（建号与授权用；达梦管理员即 `SYSDBA`）。"""

ADMIN_USER: dict[str, str] = {"mysql": "root", "postgres": "postgres", "dm8": "SYSDBA"}
"""管理员账号名。"""

ADMIN_DATABASE: dict[str, str | None] = {"mysql": None, "postgres": "postgres", "dm8": None}
"""管理连接默认库（MySQL 不带库名、PostgreSQL 用 `postgres` 库、达梦回落目标连接串）。"""

CHAIN_BY_SCOPE: dict[str, str] = {"platform": "platform", "tenant": "tenant"}
"""对象 → 迁移链（平台对象跑平台链、租户对象跑租户链，单库单链）。"""

FLOW_STEPS: tuple[str, ...] = ("建库", "迁移", "集成用例", "删库清理")
"""流程步骤（建库 → 迁移 → 集成用例 → 删库清理；job 内独立、互不污染）。"""

ENGINE_CHOICES: tuple[str, ...] = ("mysql", "postgres", "dm8")
SCOPE_CHOICES: tuple[str, ...] = ("all", "platform", "tenant")
"""`--scope` 取值（缺省 all = 平台 + 租户两对象）。"""


def resolve_test_database(engine: str, scope: str = "platform") -> str:
    """按方言与对象取测试库 / 模式名。

    Args:
        engine: 方言（`mysql` / `postgres` / `dm8`）。
        scope: 对象（`platform` / `tenant`）。

    Returns:
        str: 测试库名（达梦为模式名）。
    """
    return TEST_DATABASES[engine][scope]


def resolve_test_url(engine: str, scope: str = "platform", *, override: str = "") -> str:
    """取对象连接串（显式覆盖 > 环境变量）。

    Args:
        engine: 方言。
        scope: 对象。
        override: 显式连接串（空串表示未指定）。

    Returns:
        str: 连接串（可能为空串：既未覆盖也未配置环境变量）。
    """
    if override:
        return override
    return os.environ.get(TEST_URL_ENV[scope], "")


def resolve_admin_url(engine: str, url: str, *, override: str = "", password: str = "") -> str:
    """推导管理连接串（显式 > 管理员密码环境变量；达梦回落目标连接串）。

    Args:
        engine: 方言。
        url: 对象连接串。
        override: 显式管理连接串（空串表示未指定）。
        password: 显式管理员密码（空串表示取环境变量）。

    Returns:
        str: 管理连接串；无法推导时返回空串（调用方据此跳过建号）。
    """
    if override:
        return override
    if engine == "dm8":
        return _without_database(url)
    admin_password = password or os.environ.get(ADMIN_PASSWORD_ENV[engine], "")
    if not admin_password:
        return ""
    return _rebuild_url(url, user=ADMIN_USER[engine], password=admin_password, database=ADMIN_DATABASE[engine])


def build_target(engine: str, scope: str, *, url: str, admin_url: str = "", name: str | None = None) -> DatabaseTarget:
    """解析建删目标（达梦建 / 删模式用**去模式段**连接串 + 显式模式名）。

    Args:
        engine: 方言。
        scope: 对象。
        url: 对象连接串（含库名 / 模式名段）。
        admin_url: 显式管理连接串。
        name: 显式目标名（缺省取清单内对象名）。

    Returns:
        DatabaseTarget: 目标解析结果。

    Raises:
        ConfigError: 方言为达梦但无法从连接串派生去模式段连接串。
    """
    target_name = name or resolve_test_database(engine, scope)
    if make_url(url).get_backend_name() == "sqlite":
        return resolve_target(url, admin_url=admin_url)
    if engine == "dm8":
        schemeless = _without_database(url)
        resolved_admin = admin_url or schemeless
        return resolve_target(schemeless, name=target_name, admin_url=resolved_admin)
    return resolve_target(url, name=target_name, admin_url=admin_url)


def account_statements(engine: str, password: str) -> tuple[str, ...]:
    """测试账号建号 / 授权语句（MySQL；达梦无独立账号、PostgreSQL 走存在性分支）。

    Args:
        engine: 方言。
        password: 测试账号密码。

    Returns:
        tuple[str, ...]: 建号与授权语句（按序执行）。
    """
    if engine == "mysql":
        account = TEST_ACCOUNT["mysql"]
        literal = _quote(password)
        return (
            f"CREATE USER IF NOT EXISTS '{account}'@'%' IDENTIFIED BY '{literal}'",
            f"GRANT ALL PRIVILEGES ON `bms\\_test%`.* TO '{account}'@'%'",
        )
    return ()


async def ensure_test_account(engine: str, admin_url: str, *, password: str) -> bool:
    """幂等建测试账号与最小授权（无管理凭据 / 无密码即跳过）。

    Args:
        engine: 方言。
        admin_url: 管理连接串（空串表示未提供）。
        password: 测试账号密码（空串表示未提供）。

    Returns:
        bool: 新建账号 True；已存在或跳过 False。
    """
    if engine == "dm8":
        print(f"[test-db] 账号 → {TEST_ACCOUNT['dm8']}（达梦无独立测试账号，跳过建号）")
        return False
    if not admin_url or not password:
        print("[test-db] 账号 → 跳过（未提供管理连接串或测试密码；CI 路径账号已存在）")
        return False
    if engine == "postgres":
        return await _ensure_postgres_role(admin_url, password)
    for statement in account_statements(engine, password):
        await run_statements(admin_url, statement)
    print(f"[test-db] 账号 → {TEST_ACCOUNT[engine]}（已确保存在并授权）")
    return True


async def create(
    engine: str,
    scope: str,
    *,
    url: str,
    admin_url: str = "",
    admin_password: str = "",
    password: str = "",
) -> bool:
    """建库 / 建模式（幂等；含幂等建测试账号与授权）。

    Args:
        engine: 方言。
        scope: 对象。
        url: 对象连接串。
        admin_url: 显式管理连接串。
        admin_password: 显式管理员密码。
        password: 测试密码（建号用）。

    Returns:
        bool: 新建 True；已存在（跳过）False。
    """
    resolved_admin = resolve_admin_url(engine, url, override=admin_url, password=admin_password)
    await ensure_test_account(engine, resolved_admin, password=password)
    target = build_target(engine, scope, url=url, admin_url=resolved_admin)
    created = await create_database(target)
    if engine == "postgres":
        await _ensure_postgres_owner(resolved_admin, target.name)
    return created


async def _ensure_postgres_owner(admin_url: str, database: str) -> None:
    """把测试库属主改为测试账号（PostgreSQL 15+ 非属主在 `public` 模式无 CREATE 权限）。

    CI 路径下库由测试账号自身 `CREATE DATABASE`（属主即自身）→ 空操作；本地自带管理员时
    库由管理员建出（属主为管理员）→ 迁移前须转属主，否则建表报 `permission denied for schema public`。

    Args:
        admin_url: 管理连接串。
        database: 测试库名。
    """
    account = TEST_ACCOUNT["postgres"]
    if not admin_url or make_url(admin_url).username == account:
        return
    await run_statements(admin_url, f'ALTER DATABASE "{database}" OWNER TO {account}')


async def migrate(engine: str, scope: str, *, url: str, schema: str = "") -> bool:
    """按对象分链迁移到 head（幂等：已为 head 即跳过）。

    Args:
        engine: 方言。
        scope: 对象。
        url: 对象连接串。
        schema: 达梦目标模式名（空串表示不切换）。

    Returns:
        bool: 执行迁移 True；已是最新（跳过）False。
    """
    chain = resolve_chain(CHAIN_BY_SCOPE[scope])
    migration_url = _without_database(url) if engine == "dm8" else url
    head = head_revision(chain)
    current = await current_revision(migration_url, schema=schema)
    if head is not None and current == head:
        print(f"[test-db] {engine} {scope} → 已是最新（{current}）")
        return False
    await asyncio.to_thread(upgrade_chain, chain, migration_url, schema=schema)
    print(f"[test-db] {engine} {scope} → 迁移完成（{current or '未迁移'} → {head or '无脚本'}）")
    return True


async def drop(engine: str, scope: str, *, url: str, admin_url: str = "", admin_password: str = "") -> bool:
    """删库 / 删模式（幂等：不存在即跳过）。

    Args:
        engine: 方言。
        scope: 对象。
        url: 对象连接串。
        admin_url: 显式管理连接串。
        admin_password: 显式管理员密码。

    Returns:
        bool: 删除 True；不存在（跳过）False。
    """
    resolved_admin = resolve_admin_url(engine, url, override=admin_url, password=admin_password)
    target = build_target(engine, scope, url=url, admin_url=resolved_admin)
    return await drop_database(target)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="三库测试库流程（建库 / 迁移 / 删除；幂等）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="输出固定对象清单与执行步骤（无副作用）")
    plan.add_argument("--engine", required=True, choices=ENGINE_CHOICES)

    for name, help_text in (
        ("create", "建库 / 建模式 + 幂等建测试账号与授权"),
        ("migrate", "按对象分链 Alembic 迁移到 head（幂等）"),
        ("drop", "删库 / 删模式清理（幂等）"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--engine", required=True, choices=ENGINE_CHOICES)
        sub.add_argument("--scope", default="all", choices=SCOPE_CHOICES, help="对象（缺省 all）")
        sub.add_argument("--execute", action="store_true", help="真实执行（缺省为计划模式，不建连）")
        sub.add_argument("--url", default="", help="平台对象连接串（缺省取 BMS_TEST_DB_URL）")
        sub.add_argument("--tenant-url", default="", help="租户对象连接串（缺省取 BMS_TEST_TENANT_DB_URL）")
        sub.add_argument("--admin-url", default="", help="管理连接串（缺省按方言推导；含密码，禁止写入日志）")
        sub.add_argument("--password", default="", help="测试账号密码（缺省取该方言测试密码变量）")
        sub.add_argument("--admin-password", default="", help="管理员密码（缺省取该方言管理员变量）")
    return parser


def _scopes(scope: str) -> tuple[str, ...]:
    """`--scope` → 对象元组。"""
    return ("platform", "tenant") if scope == "all" else (scope,)


def _url_of(args: argparse.Namespace, scope: str) -> str:
    """取该对象连接串（覆盖参数 > 环境变量）。"""
    override = args.url if scope == "platform" else args.tenant_url
    return resolve_test_url(args.engine, scope, override=override)


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。"""
    return make_url(url).render_as_string(hide_password=True)


def _without_database(url: str) -> str:
    """去掉连接串的库名 / 模式段（达梦建删模式与迁移用）。"""
    return make_url(url)._replace(database=None).render_as_string(hide_password=False)  # pyright: ignore[reportPrivateUsage]


def _rebuild_url(url: str, *, user: str, password: str, database: str | None) -> str:
    """按管理员账号重建连接串（库名按方言口径；均不写入日志）。"""
    parsed = make_url(url)
    updated = parsed.set(username=user, password=password)
    updated = updated._replace(database=None) if database is None else updated.set(database=database)  # pyright: ignore[reportPrivateUsage]
    return updated.render_as_string(hide_password=False)


def _quote(value: str) -> str:
    """SQL 单引号字面量转义（防注入；值来自受控环境变量 / 参数）。"""
    return value.replace("\\", "\\\\").replace("'", "''")


async def _ensure_postgres_role(admin_url: str, password: str) -> bool:
    """幂等建 / 改 PostgreSQL 测试角色（`LOGIN` + `CREATEDB`）。

    Args:
        admin_url: 管理连接串。
        password: 测试账号密码。

    Returns:
        bool: 新建 True；已存在（改密）False。
    """
    account = TEST_ACCOUNT["postgres"]
    literal = _quote(password)
    rows = await fetch_rows(admin_url, "SELECT 1 FROM pg_roles WHERE rolname = :name", name=account)
    if rows:
        await run_statements(admin_url, f"ALTER ROLE {account} WITH LOGIN CREATEDB PASSWORD '{literal}'")
        print(f"[test-db] 账号 → {account}（已存在，已更新密码与权限）")
        return False
    await run_statements(admin_url, f"CREATE ROLE {account} WITH LOGIN CREATEDB PASSWORD '{literal}'")
    print(f"[test-db] 账号 → {account}（新建并授予 CREATEDB）")
    return True


async def _run(args: argparse.Namespace) -> int:
    """执行子命令。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（失败 1）。
    """
    engine: str = args.engine
    failures: list[str] = []

    if args.command == "plan":
        for scope in ("platform", "tenant"):
            print(f"[test-db] {engine} {scope} → {resolve_test_database(engine, scope)}")
        for step in FLOW_STEPS:
            print(f"[test-db] {step}（plan）")
        return 0

    scopes = _scopes(args.scope)
    password = args.password or os.environ.get(TEST_PASSWORD_ENV[engine], "")
    for scope in scopes:
        url = _url_of(args, scope)
        if not url:
            print(f"[test-db] {engine} {scope} → 跳过（未配置 {TEST_URL_ENV[scope]}，可用 --url / --tenant-url 指定）")
            failures.append(f"{scope}:未配置连接串")
            continue
        print(f"[test-db] {engine} {scope} {resolve_test_database(engine, scope)} | {_masked(url)}")
        if not args.execute:
            for step in FLOW_STEPS:
                print(f"[test-db] {step}（plan）")
            continue
        try:
            if args.command == "create":
                created = await create(
                    engine,
                    scope,
                    url=url,
                    admin_url=args.admin_url,
                    admin_password=args.admin_password,
                    password=password,
                )
                print(f"[test-db] {engine} {scope} → 建库：{'新建' if created else '已存在（跳过）'}")
            elif args.command == "migrate":
                schema = resolve_test_database(engine, scope) if engine == "dm8" else ""
                await migrate(engine, scope, url=url, schema=schema)
            else:
                dropped = await drop(
                    engine,
                    scope,
                    url=url,
                    admin_url=args.admin_url,
                    admin_password=args.admin_password,
                )
                print(f"[test-db] {engine} {scope} → 删库：{'已删除' if dropped else '不存在（跳过）'}")
        except ConfigError as exc:
            print(f"[test-db] {engine} {scope} → 失败：{exc}")
            failures.append(f"{scope}:{exc}")
        except Exception as exc:  # 连接 / 权限 / 驱动异常：显式失败并提示，不静默跳过
            print(f"[test-db] {engine} {scope} → 失败：{type(exc).__name__}: {exc}")
            failures.append(f"{scope}:{type(exc).__name__}")

    if failures:
        print(f"[test-db] 汇总：失败 {len(failures)} 项（{', '.join(failures)}）")
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（成功 0；执行失败 1；参数非法由 argparse 以 2 退出）。
    """
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
