"""i18n 附表读写助手（Kiwi 2405）：两级回退 / 大小写不敏感 / 多文案列 / 连带清理。

被测对象是**域无关**的通用助手（`bms_core/repositories/i18n.py`）：本文件自造两张最小表
（主表 + 多列附表），锁死「读按语言优先级回退、写整体替换、删连带软删」三条口径。
"""

from collections.abc import AsyncIterator
from functools import partial
from typing import cast

import pytest
from sqlalchemy import Connection, String, Table, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import BaseModel, SnowflakeId
from bms_core.repositories.i18n import (
    load_i18n,
    load_i18n_all,
    load_i18n_all_texts,
    load_i18n_texts,
    replace_i18n,
    replace_i18n_texts,
    soft_delete_i18n,
)
from bms_core.testing.transaction import rollback_session


class I18nProbe(BaseModel):
    """测试主表（`test_i18n_probe`）：默认文案列 `name`。"""

    __tablename__ = "test_i18n_probe"
    __table_args__ = (UniqueConstraint("code", "deleted_at", name="uq_test_i18n_probe_code"),)

    code: Mapped[str] = mapped_column(String(32), comment="编码")
    name: Mapped[str] = mapped_column(String(64), comment="默认文案（派生快照）")


class I18nProbeText(BaseModel):
    """测试附表（`test_i18n_probe_i18n`）：单列 `name` + 双列 `subject` / `content`。"""

    __tablename__ = "test_i18n_probe_i18n"
    __table_args__ = (
        UniqueConstraint("probe_id", "locale", "deleted_at", name="uq_test_i18n_probe_i18n_probe_locale"),
    )

    probe_id: Mapped[int] = mapped_column(SnowflakeId, comment="主表 ID")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识")
    name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="单列文案")
    subject: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="主题")
    content: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="正文")


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享库上只补本文件需要的表）。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎（幂等建本文件两表）。

    Args:
        shared_platform_engine: 共享库引擎。

    Returns:
        AsyncEngine: 已建表的引擎。
    """
    async with shared_platform_engine.begin() as connection:
        for table in (cast("Table", I18nProbe.__table__), cast("Table", I18nProbeText.__table__)):
            await connection.run_sync(partial(_create_table, table))
    return shared_platform_engine


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """回滚会话（用例结束整体回滚）。

    Args:
        engine: 共享库引擎。

    Yields:
        AsyncSession: 会话。
    """
    async with rollback_session(engine) as session:
        yield session


async def _seed_probe(session: AsyncSession, *, name: str = "菜单一", code: str = "probe") -> int:
    """写一条主表行并返回主键。

    Args:
        session: 会话。
        name: 主表默认文案。
        code: 编码（唯一）。

    Returns:
        int: 主表主键。
    """
    row = I18nProbe(code=code, name=name)
    session.add(row)
    await session.flush()
    return int(row.id)


@pytest.mark.kiwi_id(2405)
async def test_load_prefers_request_locale(session: AsyncSession) -> None:
    """请求语言有行时取请求语言（第一级）。"""
    probe_id = await _seed_probe(session)
    session.add_all(
        [
            I18nProbeText(probe_id=probe_id, locale="zh-CN", name="菜单一-中文"),
            I18nProbeText(probe_id=probe_id, locale="en-US", name="Menu One"),
        ]
    )
    await session.flush()
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["en-US", "zh-CN"],
    )
    assert result.get(probe_id) == "Menu One"


@pytest.mark.kiwi_id(2405)
async def test_load_falls_back_to_default_locale(session: AsyncSession) -> None:
    """请求语言缺行时回退系统默认语言（第二级，而非直接回主表列）。"""
    probe_id = await _seed_probe(session)
    session.add(I18nProbeText(probe_id=probe_id, locale="zh-CN", name="菜单一-中文"))
    await session.flush()
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["ja-JP", "zh-CN"],
    )
    assert result.get(probe_id) == "菜单一-中文"


@pytest.mark.kiwi_id(2405)
async def test_load_returns_empty_when_both_locales_missing(session: AsyncSession) -> None:
    """两级语言都缺行时不返回该键（由调用方回退主表默认文案列）。"""
    probe_id = await _seed_probe(session)
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["ja-JP", "zh-CN"],
    )
    assert not result


@pytest.mark.kiwi_id(2405)
async def test_load_locale_case_insensitive(session: AsyncSession) -> None:
    """存量小写 `zh-cn` 行可被 `zh-CN` 请求命中（比较不敏感）。"""
    probe_id = await _seed_probe(session)
    session.add(I18nProbeText(probe_id=probe_id, locale="zh-cn", name="小写存量"))
    await session.flush()
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["ZH-CN"],
    )
    assert result.get(probe_id) == "小写存量"


@pytest.mark.kiwi_id(2405)
async def test_load_skips_blank_text(session: AsyncSession) -> None:
    """请求语言行文案为空白时继续回退默认语言（去空白为空即缺失）。"""
    probe_id = await _seed_probe(session)
    session.add_all(
        [
            I18nProbeText(probe_id=probe_id, locale="en-US", name="   "),
            I18nProbeText(probe_id=probe_id, locale="zh-CN", name="中文兜底"),
        ]
    )
    await session.flush()
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["en-US", "zh-CN"],
    )
    assert result.get(probe_id) == "中文兜底"


@pytest.mark.kiwi_id(2405)
async def test_load_normalizes_locales(session: AsyncSession) -> None:
    """语言序列去空白 / 去重 / 小写归一后仍按首现优先级取文。"""
    probe_id = await _seed_probe(session)
    session.add(I18nProbeText(probe_id=probe_id, locale="en-US", name="Menu One"))
    await session.flush()
    result = await load_i18n(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=[" en-US ", "en-us", "", "zh-CN"],
    )
    assert result.get(probe_id) == "Menu One"


@pytest.mark.kiwi_id(2405)
async def test_load_without_owner_ids_or_locales_returns_empty(session: AsyncSession) -> None:
    """空主表 ID 集或空语言序列直接返回空（不打库）。"""
    assert not await load_i18n(session, I18nProbeText, "probe_id", ConcurrentStableList(), locales=["zh-CN"])
    probe_id = await _seed_probe(session)
    assert not await load_i18n(session, I18nProbeText, "probe_id", ConcurrentStableList([probe_id]), locales=[])


@pytest.mark.kiwi_id(2405)
async def test_load_texts_falls_back_per_column(session: AsyncSession) -> None:
    """多文案列各列独立回退：主题有英文、正文只有中文时分别取不同语言。"""
    probe_id = await _seed_probe(session)
    session.add_all(
        [
            I18nProbeText(probe_id=probe_id, locale="zh-CN", name=None, subject="中文主题", content="中文正文"),
            I18nProbeText(probe_id=probe_id, locale="en-US", name=None, subject="English Subject", content=None),
        ]
    )
    await session.flush()
    result = await load_i18n_texts(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["en-US", "zh-CN"],
        text_columns=("subject", "content"),
    )
    bucket = result.get(probe_id)
    assert bucket is not None
    assert bucket.get("subject") == "English Subject"
    assert bucket.get("content") == "中文正文"


@pytest.mark.kiwi_id(2405)
async def test_load_all_variants(session: AsyncSession) -> None:
    """维护视图：全语言单列投影与全语言多列映射。"""
    probe_id = await _seed_probe(session)
    session.add_all(
        [
            I18nProbeText(probe_id=probe_id, locale="zh-CN", name="中文名", subject="中文主题"),
            I18nProbeText(probe_id=probe_id, locale="en-US", name="English Name", subject="English Subject"),
        ]
    )
    await session.flush()
    by_locale = await load_i18n_all(session, I18nProbeText, "probe_id", ConcurrentStableList([probe_id]))
    assert by_locale.get(probe_id) is not None
    assert (by_locale.get(probe_id) or {}).get("en-US") == "English Name"
    detailed = await load_i18n_all_texts(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        text_columns=("subject",),
    )
    detail = detailed.get(probe_id)
    assert detail is not None
    assert (detail.get("zh-CN") or {}).get("subject") == "中文主题"
    assert not await load_i18n_all(session, I18nProbeText, "probe_id", ConcurrentStableList())


@pytest.mark.kiwi_id(2405)
async def test_replace_i18n_overwrites_and_skips_blank(session: AsyncSession) -> None:
    """整体替换：旧行软删、空白语言不入库、全空等价清空。"""
    probe_id = await _seed_probe(session)
    await replace_i18n(
        session,
        I18nProbeText,
        "probe_id",
        probe_id,
        ConcurrentStableDict({"zh-CN": "旧中文", "en-US": "Old"}),
    )
    await replace_i18n(
        session,
        I18nProbeText,
        "probe_id",
        probe_id,
        ConcurrentStableDict({"zh-CN": "新中文", "en-US": "  "}),
    )
    result = await load_i18n_all(session, I18nProbeText, "probe_id", ConcurrentStableList([probe_id]))
    current = result.get(probe_id)
    assert current is not None
    assert current.get("zh-CN") == "新中文"
    assert current.get("en-US") is None
    await replace_i18n(session, I18nProbeText, "probe_id", probe_id, ConcurrentStableDict())
    assert not await load_i18n_all(session, I18nProbeText, "probe_id", ConcurrentStableList([probe_id]))


@pytest.mark.kiwi_id(2405)
async def test_replace_texts_writes_multiple_columns(session: AsyncSession) -> None:
    """多列写入：同语言一行承载多个文案列。"""
    probe_id = await _seed_probe(session)
    texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    texts.set(
        "zh-CN",
        ConcurrentStableDict({"subject": "主题一", "content": "正文一"}),
    )
    await replace_i18n_texts(
        session,
        I18nProbeText,
        "probe_id",
        probe_id,
        texts,
        text_columns=("subject", "content"),
    )
    result = await load_i18n_texts(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([probe_id]),
        locales=["zh-CN"],
        text_columns=("subject", "content"),
    )
    bucket = result.get(probe_id)
    assert bucket is not None
    assert bucket.get("subject") == "主题一"
    assert bucket.get("content") == "正文一"


@pytest.mark.kiwi_id(2405)
async def test_soft_delete_i18n_clears_rows(session: AsyncSession) -> None:
    """主表删除连带清理：附表行全部软删，重复调用幂等。"""
    probe_id = await _seed_probe(session)
    await replace_i18n(session, I18nProbeText, "probe_id", probe_id, ConcurrentStableDict({"zh-CN": "中文"}))
    await soft_delete_i18n(session, I18nProbeText, "probe_id", probe_id)
    assert not await load_i18n_all(session, I18nProbeText, "probe_id", ConcurrentStableList([probe_id]))
    await soft_delete_i18n(session, I18nProbeText, "probe_id", probe_id)


@pytest.mark.kiwi_id(2405)
async def test_load_all_texts_skips_blank_and_splits_owners(session: AsyncSession) -> None:
    """全语言多列：空白值不入结果；多个主表 / 多个语言各自成桶（含同语言多列）。"""
    first = await _seed_probe(session, name="甲", code="p1")
    second = await _seed_probe(session, name="乙", code="p2")
    session.add_all(
        [
            I18nProbeText(probe_id=first, locale="zh-CN", name="甲中文", subject="甲主题"),
            I18nProbeText(probe_id=first, locale="en-US", name="First", subject=None),
            I18nProbeText(probe_id=second, locale="zh-CN", name="   ", subject="  "),
        ]
    )
    await session.flush()
    result = await load_i18n_all_texts(
        session,
        I18nProbeText,
        "probe_id",
        ConcurrentStableList([first, second]),
        text_columns=("name", "subject"),
    )
    assert set(result.keys()) == {first}
    by_locale = result.get(first)
    assert by_locale is not None
    assert (by_locale.get("zh-CN") or {}).get("subject") == "甲主题"
    assert (by_locale.get("en-US") or {}).get("name") == "First"
