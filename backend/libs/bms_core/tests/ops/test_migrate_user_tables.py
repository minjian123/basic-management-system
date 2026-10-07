"""跨库数据搬迁脚本测试（Kiwi 2247）：幂等 upsert / dry-run 不建连 / 失败汇总 / 参数成对校验。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_platform.models.user import SysAccountLock, SysUser
from ops import migrate_user_tables
from ops.migrate_tenants import TenantRef
from ops.migrate_user_tables import main, move_tenant

_NOW = datetime(2026, 10, 7, 0, 0, 0, tzinfo=UTC).replace(tzinfo=None)

_USER_TABLE: Table = cast("Table", SysUser.__table__)
_LOCK_TABLE: Table = cast("Table", SysAccountLock.__table__)


def _always_sync(_url: str) -> bool:
    """测试替身：恒定判定为同步方言（走达梦等同步驱动路径）。

    Args:
        _url: 连接串（忽略）。

    Returns:
        bool: 恒定 True。
    """
    return True


def _async_url(path: Path) -> str:
    """异步连接串（SQLite 文件）。

    Args:
        path: 库文件路径。

    Returns:
        str: `sqlite+aiosqlite` 连接串。
    """
    return f"sqlite+aiosqlite:///{path}"


def _sync_url(path: Path) -> str:
    """同步连接串（测试侧准备数据与断言）。

    Args:
        path: 库文件路径。

    Returns:
        str: `sqlite` 连接串。
    """
    return f"sqlite:///{path}"


def _create_tables(path: Path) -> None:
    """建两表（缺则建）。

    Args:
        path: 库文件路径。
    """
    engine = create_engine(_sync_url(path))
    try:
        with engine.begin() as connection:
            _USER_TABLE.create(bind=connection, checkfirst=True)
            _LOCK_TABLE.create(bind=connection, checkfirst=True)
    finally:
        engine.dispose()


def _seed_user(path: Path, user_id: int, username: str) -> None:
    """写入一条用户与一条锁定记录（模拟 org 租户库存量数据）。

    Args:
        path: 库文件路径。
        user_id: 用户主键。
        username: 登录账号。
    """
    engine = create_engine(_sync_url(path))
    try:
        with engine.begin() as connection:
            connection.execute(
                _USER_TABLE.insert(),
                [
                    {
                        "id": user_id,
                        "created_at": _NOW,
                        "updated_at": _NOW,
                        "version": 1,
                        "username": username,
                        "password_hash": "pbkdf2_sha256$stub",
                        "name": "管理员",
                        "status": "enabled",
                        "failed_count": 0,
                        "pwd_reset_required": False,
                    }
                ],
            )
            connection.execute(
                _LOCK_TABLE.insert(),
                [
                    {
                        "id": user_id + 1,
                        "created_at": _NOW,
                        "updated_at": _NOW,
                        "version": 1,
                        "user_id": user_id,
                        "lock_type": "manual",
                        "reason": "管理员手动锁定",
                        "locked_at": _NOW,
                    }
                ],
            )
    finally:
        engine.dispose()


def _count_rows(path: Path, table_name: str) -> int:
    """统计目标表行数。

    Args:
        path: 库文件路径。
        table_name: 表名（`sys_user` / `sys_account_lock`）。

    Returns:
        int: 行数。
    """
    table = _USER_TABLE if table_name == "sys_user" else _LOCK_TABLE
    engine = create_engine(_sync_url(path))
    try:
        with engine.connect() as connection:
            return len(connection.execute(select(table.c.id)).all())
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(2247)
def test_move_tenant_is_idempotent(tmp_path: Path) -> None:
    """两表按主键搬迁：首跑新增、重跑更新且不重复插入（幂等）。"""
    source = tmp_path / "bms_org_demo.db"
    target = tmp_path / "bms_platform_demo.db"
    _create_tables(source)
    _create_tables(target)
    _seed_user(source, 1001, "admin")

    first = asyncio.run(move_tenant(_async_url(source), _async_url(target)))
    assert first.created == 2
    assert _count_rows(target, "sys_user") == 1
    assert _count_rows(target, "sys_account_lock") == 1

    second = asyncio.run(move_tenant(_async_url(source), _async_url(target)))
    assert (second.created, second.updated) == (0, 2)
    assert _count_rows(target, "sys_user") == 1


@pytest.mark.kiwi_id(2247)
def test_move_tenant_skips_missing_source_table(tmp_path: Path) -> None:
    """源表不存在（已删 / 未建）按跳过处理，不抛异常。"""
    source = tmp_path / "bms_org_empty.db"
    target = tmp_path / "bms_platform_empty.db"
    _create_tables(target)

    outcome = asyncio.run(move_tenant(_async_url(source), _async_url(target)))
    assert outcome.created == 0
    assert outcome.updated == 0
    assert _count_rows(target, "sys_user") == 0


@pytest.mark.kiwi_id(2247)
def test_main_dry_run_and_drill_pair_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只打印清单不建连；单库演练参数须成对给出。"""
    target = tmp_path / "bms_platform_drill.db"
    source = tmp_path / "bms_org_drill.db"
    assert (
        main(ConcurrentStableList(["--dry-run", "--url", _async_url(source), "--target-url", _async_url(target)])) == 0
    )
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert not target.exists()

    assert main(ConcurrentStableList(["--url", _async_url(source)])) == 1
    assert "同时给出" in capsys.readouterr().out


@pytest.mark.kiwi_id(2247)
def test_main_collects_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """单库失败记失败并汇总（退出码 1，可幂等重跑；不中断整批）。"""
    target = tmp_path / "bms_platform_broken.db"
    _create_tables(target)
    broken = "sqlite+aiosqlite:////nonexistent_dir_for_drill/bms_org_broken.db"
    assert main(ConcurrentStableList(["--url", broken, "--target-url", _async_url(target)])) == 1
    assert "汇总：成功 0、失败 1" in capsys.readouterr().out


@pytest.mark.kiwi_id(2247)
def test_move_tenant_sync_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同步方言路径（达梦等）：经 `is_sync_only_url` 判定走 `_move_sync`，搬迁结果一致。"""
    source = tmp_path / "bms_org_sync.db"
    target = tmp_path / "bms_platform_sync.db"
    _create_tables(source)
    _create_tables(target)
    _seed_user(source, 3001, "sync-admin")
    monkeypatch.setattr(migrate_user_tables, "is_sync_only_url", _always_sync)

    outcome = asyncio.run(move_tenant(_sync_url(source), _sync_url(target)))
    assert outcome.created == 2
    assert _count_rows(target, "sys_user") == 1

    again = asyncio.run(move_tenant(_sync_url(source), _sync_url(target)))
    assert (again.created, again.updated) == (0, 2)

    empty = tmp_path / "bms_org_sync_empty.db"
    outcome_empty = asyncio.run(move_tenant(_sync_url(empty), _sync_url(target)))
    assert outcome_empty.created == 0


@pytest.mark.kiwi_id(2247)
def test_main_drill_moves_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """单库演练真搬：成功汇总写入新增行数。"""
    source = tmp_path / "bms_org_drill2.db"
    target = tmp_path / "bms_platform_drill2.db"
    _create_tables(source)
    _create_tables(target)
    _seed_user(source, 4001, "drill-admin")

    assert main(ConcurrentStableList(["--url", _async_url(source), "--target-url", _async_url(target)])) == 0
    out = capsys.readouterr().out
    assert "汇总：成功 1、失败 0" in out
    assert _count_rows(target, "sys_user") == 1


@pytest.mark.kiwi_id(2247)
async def test_resolve_refs_by_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--code` 显式租户：库名基经对照表补全后构造源 / 目标连接串。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _fake_enrich(
        refs: ConcurrentStableList[TenantRef], _registry_url: str
    ) -> ConcurrentStableList[TenantRef]:
        """测试替身：原样返回租户引用（不读注册库）。"""
        calls.add("enrich")
        return refs

    monkeypatch.setattr(migrate_user_tables, "enrich_refs", _fake_enrich)
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    args = migrate_user_tables.build_parser().parse_args(["--code", "demo"])
    refs = await migrate_user_tables._resolve_refs(args, factory)  # pyright: ignore[reportPrivateUsage]
    assert [ref.code for ref in refs] == ["demo"]
    pairs = migrate_user_tables._pairs(args, factory, refs)  # pyright: ignore[reportPrivateUsage]
    assert len(pairs) == 1
    assert calls == ["enrich"]


@pytest.mark.kiwi_id(2247)
def test_main_all_tenants_registry_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--all-tenants` 但租户注册库不可读 → 明确报错（退出码 1）。"""

    async def _boom(_registry_url: str) -> object:
        """测试替身：模拟注册库不可读。"""
        raise RuntimeError("db down")

    monkeypatch.setattr(migrate_user_tables, "tenant_refs", _boom)
    assert main(ConcurrentStableList(["--all-tenants", "--dry-run"])) == 1
    assert "租户注册库不可读" in capsys.readouterr().out


@pytest.mark.kiwi_id(2247)
def test_main_requires_tenant_dimension(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """既无 `--code` 也无 `--all-tenants` → 明确报错（退出码 1）。"""
    assert main(ConcurrentStableList(["--dry-run"])) == 1
    assert "需 --code" in capsys.readouterr().out

    async def _empty(_registry_url: str) -> ConcurrentStableList[TenantRef]:
        """测试替身：注册库可读但无租户。"""
        return ConcurrentStableList()

    monkeypatch.setattr(migrate_user_tables, "tenant_refs", _empty)
    assert main(ConcurrentStableList(["--all-tenants", "--dry-run"])) == 1
    assert "未注册租户" in capsys.readouterr().out
