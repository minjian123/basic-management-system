"""国际化种子测试（Kiwi 2404）：幂等 / 只刷新未覆盖行 / 默认语言唯一 / 期望行。"""

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.exceptions import LocaleDefaultConflictError
from bms_core.i18n.seed import (
    MESSAGE_SEEDS,
    default_message,
    expected_rows,
    seed_i18n_in_session,
)
from bms_core.models.base import Base
from bms_core.models.platform.i18n import SysI18nLocale, SysI18nMessage

pytestmark = [
    pytest.mark.kiwi_id(2404),
    pytest.mark.own_db("种子写入与建表即被测：临时库验证幂等、默认语言唯一与未覆盖行刷新"),
]

_ZH = "zh-CN"
_EN = "en-US"


async def _session(db_path: Path) -> AsyncSession:
    """建临时库并建 i18n 两表。

    Args:
        db_path: 临时库文件路径。

    Returns:
        AsyncSession: 会话（用完关闭）。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    tables = [cast("Table", SysI18nLocale.__table__), cast("Table", SysI18nMessage.__table__)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _count(session: AsyncSession, model: type) -> int:
    """统计表行数。

    Args:
        session: 会话。
        model: 模型类。

    Returns:
        int: 行数。
    """
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_seed_writes_locales_and_messages(tmp_path: Path) -> None:
    """首次下发：清单两行、默认语言唯一、文案 = 种子 × 两语言。"""
    session = await _session(tmp_path / "seed.db")
    try:
        created = await seed_i18n_in_session(session)
        await session.commit()
        assert created == 2 + len(MESSAGE_SEEDS) * 2
        assert await _count(session, SysI18nLocale) == 2
        assert await _count(session, SysI18nMessage) == len(MESSAGE_SEEDS) * 2
        rows = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.is_default.is_(True)))).scalars().all()
        assert [row.code for row in rows] == [_ZH]

        zh = (
            (
                await session.execute(
                    select(SysI18nMessage).where(
                        SysI18nMessage.msg_key == "common.confirm", SysI18nMessage.locale == _ZH
                    )
                )
            )
            .scalars()
            .first()
        )
        assert zh is not None
        assert zh.value == "确认"
        assert zh.is_overridden is False
        eng = (
            (
                await session.execute(
                    select(SysI18nMessage).where(
                        SysI18nMessage.msg_key == "common.confirm", SysI18nMessage.locale == _EN
                    )
                )
            )
            .scalars()
            .first()
        )
        assert eng is not None
        assert eng.value == "Confirm"

        assert await seed_i18n_in_session(session) == 0
        await session.commit()
    finally:
        await session.close()


async def test_seed_refreshes_only_unoverridden(tmp_path: Path) -> None:
    """平台默认升级：未覆盖行按种子刷新，租户改过的行不被覆盖。"""
    session = await _session(tmp_path / "refresh.db")
    try:
        await seed_i18n_in_session(session)
        await session.commit()
        plain = (
            (
                await session.execute(
                    select(SysI18nMessage).where(
                        SysI18nMessage.msg_key == "common.confirm", SysI18nMessage.locale == _ZH
                    )
                )
            )
            .scalars()
            .first()
        )
        assert plain is not None
        plain.value = "被平台误改的值"
        tenant = (
            (
                await session.execute(
                    select(SysI18nMessage).where(
                        SysI18nMessage.msg_key == "common.cancel", SysI18nMessage.locale == _ZH
                    )
                )
            )
            .scalars()
            .first()
        )
        assert tenant is not None
        tenant.value = "取消（租户定制）"
        tenant.is_overridden = True
        await session.commit()

        await seed_i18n_in_session(session)
        await session.commit()
        await session.refresh(plain)
        await session.refresh(tenant)
        assert plain.value == "确认"
        assert tenant.value == "取消（租户定制）"

        locale = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.code == _EN))).scalars().first()
        assert locale is not None
        locale.name = "英文（租户改）"
        locale.is_overridden = True
        await session.commit()
        await seed_i18n_in_session(session)
        await session.commit()
        await session.refresh(locale)
        assert locale.name == "英文（租户改）"
    finally:
        await session.close()


async def test_seed_rejects_duplicate_default(tmp_path: Path) -> None:
    """默认语言标记多于一条 → 44006。"""
    session = await _session(tmp_path / "dup.db")
    try:
        await seed_i18n_in_session(session)
        await session.commit()
        zh = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.code == _ZH))).scalars().first()
        en = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.code == _EN))).scalars().first()
        assert zh is not None
        assert en is not None
        # 两条都标记为租户覆盖，种子不会把它们刷回平台默认 → 默认标记重复被检出
        zh.is_overridden = True
        en.is_overridden = True
        en.is_default = True
        await session.commit()
        with pytest.raises(LocaleDefaultConflictError):
            await seed_i18n_in_session(session)
    finally:
        await session.close()


async def test_seed_restores_missing_default(tmp_path: Path) -> None:
    """默认语言标记缺失 → 种子补回出厂默认语言。"""
    session = await _session(tmp_path / "restore.db")
    try:
        await seed_i18n_in_session(session)
        await session.commit()
        zh = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.code == _ZH))).scalars().first()
        assert zh is not None
        zh.is_default = False
        await session.commit()
        await seed_i18n_in_session(session)
        await session.commit()
        await session.refresh(zh)
        assert zh.is_default is True
    finally:
        await session.close()


async def test_seed_restores_default_when_row_overridden(tmp_path: Path) -> None:
    """默认语言行被租户改过（跳过刷新）且标记丢失 → 种子按回退目标补回。"""
    session = await _session(tmp_path / "overridden.db")
    try:
        await seed_i18n_in_session(session)
        await session.commit()
        zh = (await session.execute(select(SysI18nLocale).where(SysI18nLocale.code == _ZH))).scalars().first()
        assert zh is not None
        zh.is_overridden = True
        zh.is_default = False
        await session.commit()
        await seed_i18n_in_session(session)
        await session.commit()
        await session.refresh(zh)
        assert zh.is_default is True
    finally:
        await session.close()


def test_expected_rows_and_default_message() -> None:
    """期望行数量与种子一致；默认文案按 key + 语言可取。"""
    rows = expected_rows()
    assert len(rows) == 2 + len(MESSAGE_SEEDS)
    assert default_message("common.confirm", _EN) == "Confirm"
    assert default_message("common.confirm", "fr-FR") is None
    assert default_message("not.exists", _ZH) is None
    assert default_message("error.44001", _ZH) == "语言标识已存在"
