"""OIDC 测试客户端种子脚本（幂等）：写入 BMS 兼作 IdP 联调演示客户端（仅 dev / E2E 显式执行）。

用法：

```bash
cd backend
# identity 租户库（先迁移/建表）：
uv run python -m ops.seed_oidc_client
# 自定义回调地址 / 密钥：
OIDC_DEMO_CLIENT_SECRET=my-secret uv run python -m ops.seed_oidc_client --redirect-uri http://localhost:8080/callback
```

- URL 解析：租户库 `--url` > `BMS_MIGRATION_URL` > 配置租户库 URL；
- 幂等：按 `client_id` 判存——存在即更新（回调 / scope / 状态），不存在即创建；
- 生产不自种子（设计决策 15）；`client_secret` 落库只存 PBKDF2 哈希，明文在输出打印供联调。
"""

import argparse
import asyncio
import json
import os
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.security.pbkdf2 import PBKDF2_ITERATIONS, Pbkdf2PasswordHasher
from bms_identity.models.client import SysClient

DEFAULT_CLIENT_ID = "bms-demo-client"
DEFAULT_SECRET = "bms-demo-secret"
DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="OIDC 测试客户端种子（sys_client，幂等）")
    parser.add_argument("--url", default="", help="identity 租户库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID, help="客户端标识（缺省 bms-demo-client）")
    parser.add_argument("--name", default="BMS Demo Client", help="应用名称")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI, help="回调地址（可多次传入）", action="append")
    parser.add_argument("--scope", default="openid", help="scope（空格分隔；缺省 openid）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def _tenant_url(url: str) -> str:
    """解析租户库 URL（参数 > `BMS_MIGRATION_URL` > 配置租户库 URL）。

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


async def seed_client(
    url: str,
    *,
    client_id: str,
    name: str,
    redirect_uris: list[str],
    scopes: list[str],
    secret: str,
) -> tuple[int, int]:
    """建表并按 `client_id` 幂等写入演示客户端。

    Args:
        url: identity 租户库连接串。
        client_id: 客户端标识。
        name: 应用名称。
        redirect_uris: 回调地址白名单。
        scopes: scope 集合。
        secret: 客户端密钥明文（落库只存哈希）。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)；重复执行为 (0, 0)。
    """
    hasher = Pbkdf2PasswordHasher(iterations=PBKDF2_ITERATIONS)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysClient.__table__.create, checkfirst=True)
        async with factory() as session:
            statement = select(SysClient).where(SysClient.client_id == client_id, SysClient.deleted_at.is_(None))
            existing = (await session.execute(statement)).scalar_one_or_none()
            payload = {
                "name": name,
                "redirect_uris": json.dumps(redirect_uris, ensure_ascii=False),
                "grant_types": json.dumps(["authorization_code"], ensure_ascii=False),
                "scopes": json.dumps(scopes, ensure_ascii=False),
                "ip_whitelist": "[]",
                "status": "enabled",
            }
            if existing is None:
                session.add(SysClient(client_id=client_id, client_secret_hash=hasher.hash(secret), **payload))
                created = 1
            else:
                changed = False
                for field, value in payload.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if not hasher.verify(secret, existing.client_secret_hash or ""):
                    existing.client_secret_hash = hasher.hash(secret)
                    changed = True
                updated = 1 if changed else 0
            await session.commit()
    finally:
        await engine.dispose()
    return created, updated


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    url = _tenant_url(args.url)
    redirect_uris = list(args.redirect_uri)
    scopes = [item for item in args.scope.split() if item]
    secret = os.environ.get("OIDC_DEMO_CLIENT_SECRET", DEFAULT_SECRET)
    if args.dry_run:
        print(f"[seed_oidc_client] 租户库：{make_url(url).render_as_string(hide_password=True)}")
        print(f"[seed_oidc_client] 客户端：{args.client_id}（redirect_uris={redirect_uris} scopes={scopes}）")
        return 0
    created, updated = asyncio.run(
        seed_client(
            url,
            client_id=args.client_id,
            name=args.name,
            redirect_uris=redirect_uris,
            scopes=scopes,
            secret=secret,
        )
    )
    print(f"[seed_oidc_client] client_id={args.client_id} client_secret={secret}（新增 {created} / 更新 {updated}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
