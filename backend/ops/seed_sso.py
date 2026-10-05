"""SSO 演示种子脚本（幂等）：写入演示 IdP 行与可选用户映射（阶段二 02_01，仅 dev / E2E 显式执行）。

用法：

```bash
cd backend
# IdP 行（identity 租户库；先迁移/建表，读配置解析）：
uv run python -m ops.seed_sso
# 追加用户映射（identity 平台库；02_02 起由管理面写入，本期仅联调用）：
uv run python -m ops.seed_sso --map-user-id 1 --map-external-id <Keycloak 用户 UUID>
```

- URL 解析：租户库 `--url` > `BMS_MIGRATION_URL` > 配置租户库模板；平台库 `--platform-url` >
  `BMS_PLATFORM_MIGRATION_URL` > 按库键 `platform_identity` 解析；
- 幂等：按 `idp_key` / `(idp_key, external_id)` 判存——存在即跳过（映射 `user_id` 变化则更新）；
- 生产不自种子（设计决策 22）；`config.client_secret_ref=env:KEYCLOAK_CLIENT_SECRET`（零明文入行）。
"""

import argparse
import asyncio
import json
import os

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.serialization import normalize_collections
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key
from bms_identity.models.identity_provider import SysIdentityProvider
from bms_identity.models.user_identity import SysUserIdentity

DEFAULT_IDP_KEY = "keycloak"
DEFAULT_CLIENT_ID = "bms-backend"


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="SSO 演示种子（sys_identity_provider + 可选 sys_user_identity，幂等）")
    parser.add_argument("--url", default="", help="identity 租户库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument(
        "--platform-url", default="", help="identity 平台库连接串（缺省读 BMS_PLATFORM_MIGRATION_URL / 配置）"
    )
    parser.add_argument("--tenant", default="demo", help="映射归属租户码（缺省 demo）")
    parser.add_argument("--map-user-id", type=int, default=0, help="映射的 BMS 用户 ID（>0 时写平台库映射）")
    parser.add_argument("--map-external-id", default="", help="外部 IdP 用户标识（如 Keycloak subject）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def _tenant_url(url: str) -> str:
    """解析租户库 URL（参数 > `BMS_MIGRATION_URL` > 配置租户库模板）。

    Args:
        url: 命令行传入的 URL（空串表示未指定）。

    Returns:
        str: 租户库连接串。
    """
    if url:
        return url
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    return get_settings().database.tenants.url


def _platform_url(url: str) -> str:
    """解析平台库 URL（参数 > `BMS_PLATFORM_MIGRATION_URL` > 按库键 `platform_identity`）。

    Args:
        url: 命令行传入的 URL（空串表示未指定）。

    Returns:
        str: 平台库连接串。
    """
    if url:
        return url
    env_url = os.environ.get("BMS_PLATFORM_MIGRATION_URL", "")
    if env_url:
        return env_url
    settings = get_settings()
    return EngineFactory(settings, allow_cross_service=True).resolved_url(build_platform_db_key("identity"))


def _idp_config() -> ConcurrentStableDict[str, object]:
    """取演示 IdP 行配置（issuer 取 `KEYCLOAK_PUBLIC_URL`，密钥仅存引用）。

    Returns:
        ConcurrentStableDict[str, object]: OIDC 行配置 JSON。
    """
    issuer_base = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8090").rstrip("/")
    return ConcurrentStableDict(
        {
            "issuer": f"{issuer_base}/realms/bms",
            "client_id": DEFAULT_CLIENT_ID,
            "client_secret_ref": "env:KEYCLOAK_CLIENT_SECRET",
            "scopes": ConcurrentStableList(["openid", "profile", "email"]),
        }
    )


async def seed_identity_provider(url: str) -> tuple[int, int]:
    """建表并按 `idp_key` 幂等写入演示 IdP 行。

    Args:
        url: identity 租户库连接串。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)；重复执行为 (0, 0)。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysIdentityProvider.__table__.create, checkfirst=True)
        async with factory() as session:
            statement = select(SysIdentityProvider).where(
                SysIdentityProvider.idp_key == DEFAULT_IDP_KEY, SysIdentityProvider.deleted_at.is_(None)
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is None:
                session.add(
                    SysIdentityProvider(
                        name="Keycloak",
                        idp_key=DEFAULT_IDP_KEY,
                        type="oidc",
                        icon="",
                        config=json.dumps(normalize_collections(_idp_config()), ensure_ascii=False),
                        status="enabled",
                        sort=10,
                    )
                )
                created = 1
            else:
                payload = {
                    "name": "Keycloak",
                    "type": "oidc",
                    "config": json.dumps(normalize_collections(_idp_config()), ensure_ascii=False),
                    "status": "enabled",
                    "sort": 10,
                }
                for field, value in payload.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        updated = 1
            await session.commit()
    finally:
        await engine.dispose()
    return created, updated


async def seed_user_mapping(url: str, *, tenant: str, user_id: int, external_id: str) -> tuple[int, int]:
    """建表并按 `(idp_key, external_id)` 幂等写入用户映射（`user_id` 变化则更新）。

    Args:
        url: identity 平台库连接串。
        tenant: 映射归属租户码。
        user_id: BMS 用户 ID。
        external_id: 外部 IdP 用户标识。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)；重复执行为 (0, 0)。
    """
    idp_key = f"{tenant}:{DEFAULT_IDP_KEY}"
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysUserIdentity.__table__.create, checkfirst=True)
        async with factory() as session:
            statement = select(SysUserIdentity).where(
                SysUserIdentity.idp_key == idp_key,
                SysUserIdentity.external_id == external_id,
                SysUserIdentity.deleted_at.is_(None),
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is None:
                session.add(
                    SysUserIdentity(idp_key=idp_key, external_id=external_id, tenant_id=tenant, user_id=user_id)
                )
                created = 1
            elif existing.user_id != user_id:
                existing.user_id = user_id
                updated = 1
            await session.commit()
    finally:
        await engine.dispose()
    return created, updated


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.map_user_id > 0 and not args.map_external_id:
        print("[seed_sso] --map-user-id 需与 --map-external-id 同时提供")
        return 2
    tenant_url = _tenant_url(args.url)
    if args.dry_run:
        print(f"[seed_sso] 租户库：{make_url(tenant_url).render_as_string(hide_password=True)}")
        print(f"[seed_sso] 种子：sys_identity_provider[{DEFAULT_IDP_KEY}]（dry-run）")
        if args.map_user_id > 0:
            platform_url = _platform_url(args.platform_url)
            print(f"[seed_sso] 平台库：{make_url(platform_url).render_as_string(hide_password=True)}")
            print(
                "[seed_sso] 种子：sys_user_identity"
                f"[{args.tenant}:{DEFAULT_IDP_KEY} / {args.map_external_id}]（dry-run）"
            )
        return 0
    created, updated = asyncio.run(seed_identity_provider(tenant_url))
    print(f"[seed_sso] IdP 行新增 {created} 行 / 更新 {updated} 行（幂等；重复执行输出 0 / 0）")
    if args.map_user_id > 0:
        platform_url = _platform_url(args.platform_url)
        map_created, map_updated = asyncio.run(
            seed_user_mapping(
                platform_url, tenant=args.tenant, user_id=args.map_user_id, external_id=args.map_external_id
            )
        )
        print(f"[seed_sso] 用户映射新增 {map_created} 行 / 更新 {map_updated} 行（幂等；重复执行输出 0 / 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
