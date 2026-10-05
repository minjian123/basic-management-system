"""租户账号种子脚本（幂等）：建 / 重置**本地可登录账号**（需求 01-7；运维建号 / 联调入口）。

用法：

```bash
cd backend
uv run python -m ops.seed_user --tenant demo --username admin --dry-run         # 计划预演（不建连）
uv run python -m ops.seed_user --tenant demo --username admin                    # 建号（口令随机生成并一次性打印）
uv run python -m ops.seed_user --tenant demo --username admin --password "$DEV_PASSWORD"
uv run python -m ops.seed_user --tenant demo --username admin --reset-password   # 重置既有账号口令
```

- **库定位**：`--url` > 按「租户注册库对照表 `sys_tenant_database` 取库名基 → 库键
  `tenant_org_{db_basis}`」经 `url_template` 解析（与 `ops/init_tenant.py` 同源口径；
  注册库不可读时回落 `--tenant` 作库名基，离线 / 演练可用）；
- **幂等**：按 `username` + 未软删除判存——存在且未传 `--reset-password` → 跳过；存在且传 → 重置；
  不存在 → 新建；重复执行全为「跳过」；
- **口令**：经 `Pbkdf2PasswordHasher`（`[password_hasher]` 口径）生成**自描述哈希**；明文**不落库、不落日志**，
  仅在标准输出一次性打印（`--dry-run` 不生成口令）；
- **边界**：只写 `sys_user`（本地登录所需字段）——不写 SSO 映射（`sys_user_identity`）、不写用户↔租户归属
  关系（登录不依赖；归属维护归统一建号入口 / 域 11）、不改会话（`sys_session`）；重置**不改账号状态**
  （停用账号不会被本脚本启用）；生产首建账号的口令强度由操作者按《安全开发规范》把关。
"""

import argparse
import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasherFactory
from bms_org.models.user import SysUser
from ops.migrate_tenants import tenant_refs

DEFAULT_TENANT = "demo"
"""缺省租户编码（演示租户）。"""

DEFAULT_USERNAME = "admin"
"""缺省账号名。"""

DEFAULT_NAME = "管理员"
"""缺省显示名。"""

DEFAULT_SERVICE = "org"
"""账号主数据归属服务（`sys_user` 落 org 租户库）。"""

MIN_PASSWORD_LENGTH = 8
"""脚本侧口令最小长度防护（复杂度与强度口径归《安全开发规范》）。"""


@dataclass(frozen=True)
class SeedOutcome:
    """执行结果（新增 / 重置 / 跳过，及本次下发口令明文）。"""

    created: int
    """新增行数。"""

    reset: int
    """重置行数。"""

    skipped: int
    """跳过行数。"""

    password: str = ""
    """本次下发口令明文（仅标准输出一次性打印；未下发时为空串）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="租户账号种子（sys_user 建 / 重置，幂等；需求 01-7）")
    parser.add_argument("--url", default="", help="org 租户库连接串（缺省按租户注册库对照表解析）")
    parser.add_argument("--tenant", default=DEFAULT_TENANT, help=f"租户编码（缺省 {DEFAULT_TENANT}）")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help=f"账号名（缺省 {DEFAULT_USERNAME}）")
    parser.add_argument("--name", default=DEFAULT_NAME, help="显示名")
    parser.add_argument("--password", default="", help="口令明文（缺省随机生成并一次性打印）")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help=f"账号归属服务（缺省 {DEFAULT_SERVICE}）")
    parser.add_argument("--reset-password", action="store_true", help="重置既有账号口令（缺省跳过既有账号）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与计划（不建连、不生成口令）")
    return parser


def _generate_password() -> str:
    """生成满足复杂度（大写 / 小写 / 数字 / 符号）的随机口令。

    Returns:
        str: 随机口令（16 字符）。
    """
    return f"Bms1@{secrets.token_hex(6)}"


def _hash_password(password: str) -> str:
    """按 `[password_hasher]` 口径生成口令自描述哈希。

    Args:
        password: 口令明文。

    Returns:
        str: 自描述哈希串（`pbkdf2_sha256$...`）。
    """
    return Pbkdf2PasswordHasherFactory(get_settings()).create().hash(password)


async def _resolve_basis(code: str) -> str:
    """取租户库名基（对照表；注册库不可读 / 未注册回落当前编码，离线可用）。

    Args:
        code: 租户编码。

    Returns:
        str: 库名基。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    try:
        registry_url = factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
        refs = await tenant_refs(registry_url)
    except Exception as exc:
        print(f"[seed_user] 租户注册库不可读，按编码作库名基：{type(exc).__name__}: {exc}")
        return code
    for ref in refs:
        if ref.code == code:
            return ref.db_basis
    return code


def _resolve_url(basis: str, override: str, service: str) -> str:
    """取服务租户库连接串（显式覆盖优先，否则按库键经模板解析）。

    Args:
        basis: 库名基（对照表 `db_basis`）。
        override: 显式连接串（空串表示未指定）。
        service: 服务标识。

    Returns:
        str: 服务租户库连接串。
    """
    if override:
        return override
    settings = get_settings()
    key = build_tenant_db_key(basis, service=service or None)
    # 运维通道：允许跨服务库键（按指定服务建该租户的库）
    return EngineFactory(settings, allow_cross_service=True).resolved_url(key)


async def seed_user(
    *,
    url: str,
    username: str,
    name: str,
    password: str = "",
    reset_password: bool = False,
) -> SeedOutcome:
    """建表（缺则建）并幂等建 / 重置账号。

    Args:
        url: org 租户库连接串。
        username: 账号名。
        name: 显示名。
        password: 口令明文（空串表示随机生成）。
        reset_password: 是否重置既有账号口令（false 时既有账号跳过）。

    Returns:
        SeedOutcome: 执行结果。
    """
    plain = password or _generate_password()
    hashed = _hash_password(plain)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysUser.__table__).create, checkfirst=True)
        async with factory() as session:
            statement = select(SysUser).where(SysUser.username == username, SysUser.deleted_at.is_(None))
            existing = (await session.execute(statement)).scalars().first()
            now = datetime.now(UTC).replace(tzinfo=None)
            if existing is None:
                session.add(
                    SysUser(
                        username=username,
                        password_hash=hashed,
                        name=name,
                        status="enabled",
                        failed_count=0,
                        locked_until=None,
                        pwd_changed_at=now,
                        pwd_reset_required=False,
                    )
                )
                await session.commit()
                return SeedOutcome(created=1, reset=0, skipped=0, password=plain)
            if not reset_password:
                return SeedOutcome(created=0, reset=0, skipped=1)
            existing.password_hash = hashed
            existing.pwd_changed_at = now
            existing.pwd_reset_required = False
            existing.failed_count = 0
            existing.locked_until = None
            await session.commit()
            return SeedOutcome(created=0, reset=1, skipped=0, password=plain)
    finally:
        await engine.dispose()


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 命令行参数（缺省取进程参数）。

    Returns:
        int: 退出码（0 成功；2 参数非法）。
    """
    args = build_parser().parse_args(argv)
    code = args.tenant.strip() or DEFAULT_TENANT
    username = args.username.strip() or DEFAULT_USERNAME
    name = args.name.strip() or DEFAULT_NAME
    if args.password and len(args.password) < MIN_PASSWORD_LENGTH:
        print(f"[seed_user] 口令过短（< {MIN_PASSWORD_LENGTH} 字符），拒绝执行")
        return 2
    if args.url:
        basis, url = code, args.url
    else:
        basis = asyncio.run(_resolve_basis(code))
        url = _resolve_url(basis, "", args.service)
    if args.dry_run:
        print(f"[seed_user] 目标库：{make_url(url).render_as_string(hide_password=True)}")
        print(
            f"[seed_user] 计划：租户 {code}（库名基 {basis}）/ 账号 {username}"
            f"（{'重置既有口令' if args.reset_password else '建号，已存在则跳过'}）"
        )
        return 0
    outcome = asyncio.run(
        seed_user(
            url=url,
            username=username,
            name=name,
            password=args.password,
            reset_password=args.reset_password,
        )
    )
    print(
        f"[seed_user] 新增 {outcome.created} 行 / 重置 {outcome.reset} 行 / 跳过 {outcome.skipped} 行"
        "（幂等；重复执行新增与重置为 0）"
    )
    if outcome.password:
        print(f"[seed_user] 账号 {username} 口令（仅本次打印，请立即保存并在首登后修改）：{outcome.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
