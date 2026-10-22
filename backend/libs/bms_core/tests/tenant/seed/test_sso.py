"""SSO 演示种子用例（Kiwi 2343）：`bms_core/tenant/seed/sso.py`。

覆盖：IdP 行新建 / 配置变化更新 / 无变化不更新、用户映射新建 / `user_id` 变化更新 / 无变化跳过、
URL 解析优先级、CLI 分支（`--dry-run` / `--map-user-id` 校验 / 正常路径）。
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.identity.identity_provider import SysIdentityProvider
from bms_core.models.identity.user_identity import SysUserIdentity
from bms_core.tenant.seed import sso as sso_seed


@pytest.mark.kiwi_id(2343)
async def test_seed_identity_provider_creates_then_updates(tmp_path: Path) -> None:
    """首次写演示 IdP 行；配置变化（`KEYCLOAK_PUBLIC_URL`）触发更新；无变化不更新。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    assert await sso_seed.seed_identity_provider(url) == (1, 0)
    assert await sso_seed.seed_identity_provider(url) == (0, 0)

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (await session.execute(select(SysIdentityProvider))).scalars().all()
            assert len(rows) == 1
            assert rows[0].idp_key == sso_seed.DEFAULT_IDP_KEY
            assert rows[0].status == "enabled"
            assert "client_secret_ref" in rows[0].config
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2343)
async def test_seed_identity_provider_updates_on_config_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`KEYCLOAK_PUBLIC_URL` 变化 → issuer 变化 → 行被更新（返回 (0, 1)）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    monkeypatch.setenv("KEYCLOAK_PUBLIC_URL", "http://idp-a:8090")
    assert await sso_seed.seed_identity_provider(url) == (1, 0)
    monkeypatch.setenv("KEYCLOAK_PUBLIC_URL", "http://idp-b:8090")
    assert await sso_seed.seed_identity_provider(url) == (0, 1)
    # status 变化同样触发更新
    assert await sso_seed.seed_identity_provider(url, status="disabled") == (0, 1)


@pytest.mark.kiwi_id(2343)
async def test_seed_user_mapping_creates_updates_and_skips(tmp_path: Path) -> None:
    """映射按 `(idp_key, external_id)` 幂等：新建 → 跳过 → `user_id` 变化更新。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    assert await sso_seed.seed_user_mapping(url, tenant="demo", user_id=1, external_id="ext-1") == (1, 0)
    assert await sso_seed.seed_user_mapping(url, tenant="demo", user_id=1, external_id="ext-1") == (0, 0)
    assert await sso_seed.seed_user_mapping(url, tenant="demo", user_id=2, external_id="ext-1") == (0, 1)

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (await session.execute(select(SysUserIdentity))).scalars().all()
            assert len(rows) == 1
            assert rows[0].idp_key == f"demo:{sso_seed.DEFAULT_IDP_KEY}"
            assert rows[0].user_id == 2
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2343)
def test_url_resolution_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 解析：显式参数 > 环境变量 > 配置 / 库键解析。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env-tenant.db")
    monkeypatch.setenv("BMS_PLATFORM_MIGRATION_URL", "sqlite+aiosqlite:///env-platform.db")
    assert sso_seed._tenant_url("sqlite+aiosqlite:///arg.db") == "sqlite+aiosqlite:///arg.db"  # pyright: ignore[reportPrivateUsage]
    assert sso_seed._tenant_url("") == "sqlite+aiosqlite:///env-tenant.db"  # pyright: ignore[reportPrivateUsage]
    assert sso_seed._platform_url("") == "sqlite+aiosqlite:///env-platform.db"  # pyright: ignore[reportPrivateUsage]
    monkeypatch.delenv("BMS_MIGRATION_URL")
    monkeypatch.delenv("BMS_PLATFORM_MIGRATION_URL")
    get_settings.cache_clear()
    assert "sqlite" in sso_seed._tenant_url("")  # pyright: ignore[reportPrivateUsage]
    assert "sqlite" in sso_seed._platform_url("")  # pyright: ignore[reportPrivateUsage]
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_main_rejects_map_user_id_without_external_id(capsys: pytest.CaptureFixture[str]) -> None:
    """`--map-user-id` 缺 `--map-external-id`：拒绝执行（退出码 2）。"""
    assert sso_seed.main(ConcurrentStableList(["--map-user-id", "5"])) == 2
    assert "--map-user-id 需与 --map-external-id 同时提供" in capsys.readouterr().out


@pytest.mark.kiwi_id(2343)
def test_main_dry_run_prints_targets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 打印租户库与种子清单；带映射时另打印平台库与映射目标。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    assert sso_seed.main(ConcurrentStableList(["--url", tenant_url, "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[seed_sso] 租户库：" in out
    assert "sys_identity_provider" in out
    assert "sys_user_identity" not in out

    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert (
        sso_seed.main(
            ConcurrentStableList(
                [
                    "--url",
                    tenant_url,
                    "--platform-url",
                    platform_url,
                    "--map-user-id",
                    "7",
                    "--map-external-id",
                    "ext-7",
                    "--dry-run",
                ]
            )
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "[seed_sso] 平台库：" in out
    assert "sys_user_identity" in out


@pytest.mark.kiwi_id(2343)
def test_main_writes_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """正常路径：写 IdP 行与用户映射并打印新增 / 更新计数。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert (
        sso_seed.main(
            ConcurrentStableList(
                [
                    "--url",
                    tenant_url,
                    "--platform-url",
                    platform_url,
                    "--map-user-id",
                    "9",
                    "--map-external-id",
                    "ext-9",
                ]
            )
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "IdP 行新增 1 行 / 更新 0 行" in out
    assert "用户映射新增 1 行 / 更新 0 行" in out
