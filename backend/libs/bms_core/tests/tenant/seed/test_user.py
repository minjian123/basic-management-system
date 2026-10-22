"""账号种子用例（14_04 自 `libs/bms_core/tests/ops/test_seed_user.py` 迁入基座；Kiwi 2243 / 2343）。

覆盖 `bms_core/tenant/seed/user.py`：建号幂等、重置口令、库名基解析与回落、CLI 分支与退出码。
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.platform.user import SysUser
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasherFactory
from bms_core.tenant.seed import user as user_seed


def _verify(password: str, hashed: str) -> bool:
    """按 `[password_hasher]` 口径校验口令。

    Args:
        password: 口令明文。
        hashed: 自描述哈希串。

    Returns:
        bool: 是否匹配。
    """
    return Pbkdf2PasswordHasherFactory(get_settings()).create().verify(password, hashed)


async def _load(url: str, username: str) -> SysUser:
    """读账号行（断言辅助）。

    Args:
        url: 库连接串。
        username: 账号名。

    Returns:
        SysUser: 账号行。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysUser).where(SysUser.username == username)
            return (await session.execute(statement)).scalars().one()
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2243)
async def test_seed_user_create_is_idempotent(tmp_path: Path) -> None:
    """首次建号（一次性口令可校验、账号为启用态）、重复执行跳过；哈希为 PBKDF2 自描述串。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    first = await user_seed.seed_user(url=url, username="admin", name="管理员")
    assert (first.created, first.reset, first.skipped) == (1, 0, 0)
    assert first.password.startswith("Bms1@")

    second = await user_seed.seed_user(url=url, username="admin", name="管理员")
    assert (second.created, second.reset, second.skipped) == (0, 0, 1)
    assert second.password == ""

    row = await _load(url, "admin")
    assert row.status == "enabled"
    assert row.pwd_changed_at is not None
    assert row.pwd_reset_required is False
    assert row.password_hash.startswith("pbkdf2_sha256$")
    assert _verify(first.password, row.password_hash) is True


@pytest.mark.kiwi_id(2243)
async def test_seed_user_reset_password(tmp_path: Path) -> None:
    """重置口令：哈希更新且新口令可校验、失败计数与锁定清零；**不改变账号状态**（停用账号不被启用）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await user_seed.seed_user(url=url, username="admin", name="管理员")
    before = await _load(url, "admin")

    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (await session.execute(select(SysUser).where(SysUser.username == "admin"))).scalars().one()
            row.status = "disabled"
            row.failed_count = 3
            row.locked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
            await session.commit()
    finally:
        await engine.dispose()

    outcome = await user_seed.seed_user(
        url=url, username="admin", name="管理员", password="Fixture-Only-Pa55w0rd", reset_password=True
    )
    assert (outcome.created, outcome.reset, outcome.skipped) == (0, 1, 0)

    after = await _load(url, "admin")
    assert after.password_hash != before.password_hash
    assert _verify("Fixture-Only-Pa55w0rd", after.password_hash) is True
    assert after.failed_count == 0
    assert after.locked_until is None
    assert after.status == "disabled"


@pytest.mark.kiwi_id(2243)
def test_seed_user_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 只打印目标库与计划（不建库）；正式执行打印新增行数；过短口令拒绝（退出码 2）。"""
    db_path = tmp_path / "platform.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "目标库" in out and "admin" in out
    assert db_path.exists() is False

    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin"])) == 0
    assert "新增 1 行" in capsys.readouterr().out

    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin", "--password", "short"])) == 2


@pytest.mark.kiwi_id(2343)
async def test_resolve_tenant_basis_returns_code_when_registry_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """租户注册库不可读：回落当前编码并打印提示（离线 / 演练可用）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()

    async def _boom(_url: str) -> ConcurrentStableList[object]:
        raise RuntimeError("registry down")

    monkeypatch.setattr("bms_core.tenant.seed.user.tenant_refs", _boom)
    assert await user_seed.resolve_tenant_basis("demo") == "demo"
    assert "租户注册库不可读" in capsys.readouterr().out
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
async def test_resolve_tenant_basis_reads_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """租户注册库可读：命中编码返回对照表库名基，未命中回落编码。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()
    from bms_core.tenant.registry import TenantRef

    async def _refs(_url: str) -> ConcurrentStableList[TenantRef]:
        return ConcurrentStableList([TenantRef(code="demo", db_basis="demo_frozen")])

    monkeypatch.setattr("bms_core.tenant.seed.user.tenant_refs", _refs)
    assert await user_seed.resolve_tenant_basis("demo") == "demo_frozen"
    assert await user_seed.resolve_tenant_basis("acme") == "acme"
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_resolve_tenant_url_override_and_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """租户库连接串：显式覆盖优先；否则按库键经模板解析。"""
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()
    assert user_seed.resolve_tenant_url("demo", "sqlite+aiosqlite:///override.db", "platform") == (
        "sqlite+aiosqlite:///override.db"
    )
    resolved = user_seed.resolve_tenant_url("demo", "", "platform")
    assert "bms_platform_demo.db" in resolved
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2343)
def test_main_defaults_and_empty_args(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI 缺省值：`--tenant` / `--username` / `--name` 空串时回落缺省常量（dry-run 打印计划）。"""
    args = user_seed.build_parser().parse_args(["--url", "sqlite+aiosqlite:///x.db", "--tenant", "  ", "--dry-run"])
    assert args.tenant.strip() == ""
    assert user_seed.main(ConcurrentStableList(["--url", "sqlite+aiosqlite:///x.db", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "计划：租户 demo" in out
    assert user_seed.DEFAULT_USERNAME in out


@pytest.mark.kiwi_id(2343)
def test_main_without_url_resolves_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI 未给 `--url`：经注册库对照表 + 模板解析出目标库（dry-run 不建连、不建库）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    get_settings.cache_clear()
    assert user_seed.main(ConcurrentStableList(["--tenant", "demo", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "bms_platform_demo.db" in out
    assert "库名基 demo" in out
    assert not (tmp_path / "bms_platform_demo.db").exists()
    get_settings.cache_clear()
