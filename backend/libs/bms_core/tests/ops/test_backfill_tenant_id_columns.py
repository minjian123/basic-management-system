"""存量租户列回填测试（Kiwi 2219）：code → 雪花 id 与 idp_key 前缀重写 / 失败分支。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from ops.backfill_tenant_id_columns import (
    BackfillError,
    backfill_outbox,
    backfill_user_identity,
    main,
    process_database,
)

_ID_MAP = {"demo": 1001, "acme": 2002}


def _engine(path: Path):
    """建目标库引擎（同步 SQLite）并建最小表结构。"""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE sys_user_identity ("
                "id INTEGER PRIMARY KEY, idp_key VARCHAR(160), tenant_id VARCHAR(64), deleted_at DATETIME)"
            )
        )
        connection.execute(text("CREATE TABLE sys_outbox (id INTEGER PRIMARY KEY, tenant_id VARCHAR(64))"))
        connection.execute(text("CREATE TABLE sys_event_dead_letter (id INTEGER PRIMARY KEY, tenant_id VARCHAR(64))"))
    return engine


@pytest.mark.kiwi_id(2219)
def test_backfill_user_identity_rewrites_id_and_key_prefix(tmp_path: Path) -> None:
    """映射表：code 行改 id、idp_key 前缀改 id；已是 id 的行跳过（幂等）。"""
    engine = _engine(tmp_path / "identity.db")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_user_identity (id, idp_key, tenant_id, deleted_at) VALUES "
                    "(1, 'demo:keycloak', 'demo', NULL),"
                    "(2, '1001:oidc', '1001', NULL),"
                    "(3, 'gone:cas', 'gone', '2026-01-01')"
                )
            )
            stats = backfill_user_identity(connection, _ID_MAP)
        assert (stats.scanned, stats.updated, stats.unresolved) == (2, 1, ())
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id, idp_key, tenant_id FROM sys_user_identity ORDER BY id")).all()
        assert [(row.id, row.idp_key, row.tenant_id) for row in rows] == [
            (1, "1001:keycloak", "1001"),  # 回填后仍为 VARCHAR（类型迁移随 Alembic）
            (2, "1001:oidc", "1001"),
            (3, "gone:cas", "gone"),
        ]
        with engine.begin() as connection:  # 幂等：重复执行零变更
            assert backfill_user_identity(connection, _ID_MAP).updated == 0
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(2219)
def test_backfill_user_identity_unresolved_aborts(tmp_path: Path) -> None:
    """映射表不可解析行：报错中止并列明细（列非空不可置 NULL）。"""
    engine = _engine(tmp_path / "identity.db")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_user_identity (id, idp_key, tenant_id, deleted_at) "
                    "VALUES (1, 'ghost:cas', 'ghost', NULL)"
                )
            )
            with pytest.raises(BackfillError) as exc:
                backfill_user_identity(connection, _ID_MAP)
        assert "sys_user_identity(id=1).tenant_id" in str(exc.value)
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(2219)
def test_backfill_outbox_strict_and_lenient(tmp_path: Path) -> None:
    """发件箱 / 死信：精确解析改 id；严格模式不可解析中止、非严格置 NULL。"""
    engine = _engine(tmp_path / "outbox.db")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO sys_outbox (id, tenant_id) VALUES (1, 'demo'), (2, '1001'), (3, NULL), (4, 'ghost')")
            )
            connection.execute(
                text("INSERT INTO sys_event_dead_letter (id, tenant_id) VALUES (1, 'acme'), (2, 'ghost')")
            )
            stats = backfill_outbox(connection, _ID_MAP, strict=False)
        assert stats.updated == 4  # demo→1001、acme→2002、两处 ghost→NULL
        assert stats.unresolved == (
            "sys_outbox(id=4).tenant_id = 'ghost'",
            "sys_event_dead_letter(id=2).tenant_id = 'ghost'",
        )
        with engine.connect() as connection:
            outbox = {row[0]: row[1] for row in connection.execute(text("SELECT id, tenant_id FROM sys_outbox"))}
            dead = {
                row[0]: row[1] for row in connection.execute(text("SELECT id, tenant_id FROM sys_event_dead_letter"))
            }
        assert outbox == {1: "1001", 2: "1001", 3: None, 4: None}  # 回填后仍为 VARCHAR（类型迁移随 Alembic）
        assert dead == {1: "2002", 2: None}

        with engine.begin() as connection:
            connection.execute(text("INSERT INTO sys_outbox (id, tenant_id) VALUES (5, 'ghost')"))
            with pytest.raises(BackfillError) as exc:
                backfill_outbox(connection, _ID_MAP, strict=True)
        assert "sys_outbox(id=5).tenant_id" in str(exc.value)
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(2219)
def test_process_database_covers_identity_and_outbox(tmp_path: Path) -> None:
    """identity 平台库：映射表与发件箱同时回填；无表库为空操作。"""
    engine = _engine(tmp_path / "both.db")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_user_identity (id, idp_key, tenant_id, deleted_at) "
                    "VALUES (1, 'demo:cas', 'demo', NULL)"
                )
            )
            connection.execute(text("INSERT INTO sys_outbox (id, tenant_id) VALUES (1, 'demo')"))
            stats = process_database(connection, _ID_MAP, with_identity=True, strict=False)
        assert stats.updated == 2
    finally:
        engine.dispose()

    empty = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    try:
        with empty.begin() as connection:
            assert process_database(connection, _ID_MAP, with_identity=True, strict=True).scanned == 0
    finally:
        empty.dispose()


@pytest.mark.kiwi_id(2219)
def test_backfill_dry_run_requires_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--dry-run` 不写数据：注册库不可读 → 明确失败（退出码 1）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    from bms_core.core.config import get_settings

    get_settings.cache_clear()
    assert main(["--dry-run", "--service", "platform"]) == 1
    get_settings.cache_clear()
