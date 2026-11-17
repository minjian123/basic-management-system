"""帮助内容读取的公共小助手：租户默认语言（08_03）。

帮助装载 / 解析需要知道「租户语言清单的系统默认语言」以派生文章主表快照与回退目标。
该查询只读 `sys_i18n_locale` 一张表，但帮助域不应直接 import 国际化域的模型（跨域 import
护栏 D1），故把这一条读面放在基座仓储层（与 `bms_core.repositories.i18n` 同层、不承载业务语义），
供帮助域与后续内容面复用。
"""

from __future__ import annotations

from sqlalchemy import select

from bms_core.db.session import DbSession
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.i18n.rules import normalize_locale
from bms_core.models.platform.i18n import SysI18nLocale

__all__ = ["load_help_default_locale"]


async def load_help_default_locale(session: DbSession) -> str:
    """取租户语言清单的系统默认语言（缺失回退出厂默认语言）。

    默认语言由 `sys_i18n_locale.is_default` 标记确定（全清单恰一条）；读取侧只做「取第一条默认」，
    完整性由语言清单维护入口的 44006 校验兜底。

    Args:
        session: 租户库会话。

    Returns:
        str: 默认语言标识（标准形态）。
    """
    statement = select(SysI18nLocale.code).where(
        SysI18nLocale.is_default.is_(True),
        SysI18nLocale.deleted_at.is_(None),
    )
    code = (await session.execute(statement)).scalars().first()
    return normalize_locale(str(code)) if code else DEFAULT_LOCALE
