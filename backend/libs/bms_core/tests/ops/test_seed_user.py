"""账号种子脚本测试（Kiwi 2243：`sys_user` 建 / 重置，幂等；需求 01-7）。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.seed_user as seed_user
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasherFactory
from bms_org.models.user import SysUser


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
    url = f"sqlite+aiosqlite:///{tmp_path / 'org.db'}"
    first = await seed_user.seed_user(url=url, username="admin", name="管理员")
    assert (first.created, first.reset, first.skipped) == (1, 0, 0)
    assert first.password.startswith("Bms1@")

    second = await seed_user.seed_user(url=url, username="admin", name="管理员")
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
    url = f"sqlite+aiosqlite:///{tmp_path / 'org.db'}"
    await seed_user.seed_user(url=url, username="admin", name="管理员")
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

    outcome = await seed_user.seed_user(
        url=url, username="admin", name="管理员", password="***REDACTED***78", reset_password=True
    )
    assert (outcome.created, outcome.reset, outcome.skipped) == (0, 1, 0)

    after = await _load(url, "admin")
    assert after.password_hash != before.password_hash
    assert _verify("***REDACTED***78", after.password_hash) is True
    assert after.failed_count == 0
    assert after.locked_until is None
    assert after.status == "disabled"


@pytest.mark.kiwi_id(2243)
def test_seed_user_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 只打印目标库与计划（不建库）；正式执行打印新增行数；过短口令拒绝（退出码 2）。"""
    db_path = tmp_path / "org.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    assert seed_user.main(ConcurrentStableList(["--url", url, "--username", "admin", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "目标库" in out and "admin" in out
    assert db_path.exists() is False

    assert seed_user.main(ConcurrentStableList(["--url", url, "--username", "admin"])) == 0
    assert "新增 1 行" in capsys.readouterr().out

    assert seed_user.main(ConcurrentStableList(["--url", url, "--username", "admin", "--password", "short"])) == 2
