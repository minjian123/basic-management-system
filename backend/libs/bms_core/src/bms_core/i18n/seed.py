"""国际化种子（平台默认语言清单 + 固定文案语言包）：幂等下发到各租户库。

- **平台默认物化**：清单行与文案行由本种子写入租户库（`is_overridden=false`）；租户改过的行
  （`true`）**永不覆盖**——平台默认升级只刷新未覆盖行，这是「平台默认 + 租户覆盖」的落法。
- **默认语言唯一**：种子写完后校验恰一条 `is_default`；多于一条即抛 `44006`（种子期暴露），
  缺失则把出厂默认语言（`zh-CN`）置为默认。
- **文案范围**：`common.*`（通用动作与提示）、`i18n.*`（本模块页面与接口提示）、`error.*`（全量错误码，
  由 `error_seed.ERROR_MESSAGES` 提供，完整性由护栏用例断言）。
- 入口 `seed_i18n_entry(session, args)`：不建连接、不提交，写入并入种子编排的 XA 分支事务。
"""

from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import LocaleDefaultConflictError
from bms_core.db.session import DbSession
from bms_core.i18n.error_seed import ERROR_MESSAGES
from bms_core.i18n.registry import SEED_DEFAULT_LOCALE, SEED_LOCALES
from bms_core.models.platform.i18n import SysI18nLocale, SysI18nMessage
from bms_core.tenant.seed.contract import ExpectedRow

__all__ = [
    "MESSAGE_SEEDS",
    "default_message",
    "expected_rows",
    "seed_i18n_entry",
    "seed_i18n_in_session",
]

ZH_LOCALE = "zh-CN"
"""中文语言标识（种子中文文案的落库语言）。"""

EN_LOCALE = "en-US"
"""英文语言标识（种子英文文案的落库语言）。"""

_COMMON_MESSAGES: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList(
    (
        ("common.confirm", "确认", "Confirm"),
        ("common.cancel", "取消", "Cancel"),
        ("common.save", "保存", "Save"),
        ("common.delete", "删除", "Delete"),
        ("common.edit", "编辑", "Edit"),
        ("common.add", "新增", "Add"),
        ("common.search", "查询", "Search"),
        ("common.reset", "重置", "Reset"),
        ("common.submit", "提交", "Submit"),
        ("common.export", "导出", "Export"),
        ("common.import", "导入", "Import"),
        ("common.refresh", "刷新", "Refresh"),
        ("common.close", "关闭", "Close"),
        ("common.back", "返回", "Back"),
        ("common.more", "更多", "More"),
        ("common.detail", "详情", "Details"),
        ("common.status", "状态", "Status"),
        ("common.remark", "备注", "Remarks"),
        ("common.operation", "操作", "Actions"),
        ("common.enabled", "启用", "Enabled"),
        ("common.disabled", "停用", "Disabled"),
        ("common.yes", "是", "Yes"),
        ("common.no", "否", "No"),
        ("common.all", "全部", "All"),
        ("common.loading", "加载中…", "Loading…"),
        ("common.no_data", "暂无数据", "No data"),
        ("common.success", "操作成功", "Operation succeeded"),
        ("common.failed", "操作失败", "Operation failed"),
        ("common.required", "该项为必填", "This field is required"),
        ("common.delete_confirm", "确认删除？", "Delete this item?"),
        ("common.unsaved_confirm", "有未保存的修改，确认离开？", "You have unsaved changes. Leave anyway?"),
        ("common.copy", "复制", "Copy"),
        ("common.download", "下载", "Download"),
        ("common.upload", "上传", "Upload"),
    )
)
"""通用文案种子（`common.*`）。"""

_I18N_MESSAGES: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList(
    (
        ("i18n.title", "国际化管理", "Internationalization"),
        ("i18n.locale", "语言", "Language"),
        ("i18n.locale.code", "语言标识", "Locale code"),
        ("i18n.locale.name", "语言名称", "Locale name"),
        ("i18n.locale.rtl", "从右到左", "Right-to-left"),
        ("i18n.locale.default", "默认语言", "Default language"),
        ("i18n.locale.enabled_list", "启用语言", "Enabled locales"),
        ("i18n.message.key", "文案 key", "Message key"),
        ("i18n.message.value", "文案", "Text"),
        ("i18n.message.missing", "缺失", "Missing"),
        ("i18n.message.only_missing", "只看缺失", "Missing only"),
        ("i18n.cache.invalidate", "刷新语言包缓存", "Refresh message cache"),
        ("i18n.cache.invalidated", "语言包缓存已刷新", "Message cache refreshed"),
    )
)
"""本模块文案种子（`i18n.*`）。"""


def _build_message_seeds() -> ConcurrentStableList[tuple[str, str, str]]:
    """拼接种子文案（通用 + 本模块 + 全部错误码）。

    Returns:
        ConcurrentStableList[tuple[str, str, str]]: `(msg_key, 中文, 英文)` 清单。
    """
    seeds: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList()
    for item in _COMMON_MESSAGES:
        seeds.add(item)
    for item in _I18N_MESSAGES:
        seeds.add(item)
    for code, zh, en in ERROR_MESSAGES:
        seeds.add((f"error.{code}", zh, en))
    return seeds


MESSAGE_SEEDS: ConcurrentStableList[tuple[str, str, str]] = _build_message_seeds()
"""固定文案种子：`(msg_key, 中文, 英文)`（前后端共用同一份平台默认）。"""

_MESSAGE_INDEX: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    (f"{msg_key}\x00{locale}", text)
    for msg_key, zh, en in MESSAGE_SEEDS
    for locale, text in ((ZH_LOCALE, zh), (EN_LOCALE, en))
)
"""种子文案索引（`msg_key\\x00locale` → 文案）；供写路径派生 `is_overridden`。"""


def default_message(msg_key: str, locale: str) -> str | None:
    """取种子里的平台默认文案（无则 None，表示租户自建 key）。

    Args:
        msg_key: 文案 key。
        locale: 语言标识（标准形态）。

    Returns:
        str | None: 平台默认文案；不在种子里返回 None。
    """
    return _MESSAGE_INDEX.get(f"{msg_key}\x00{locale}")


async def _upsert_locale(session: DbSession, code: str, name: str, rtl: bool, is_default: bool, sort: int) -> int:
    """幂等写入语言清单行（未覆盖行按种子刷新）。

    Args:
        session: 种子会话（不提交）。
        code: 语言标识。
        name: 语言名称。
        rtl: 是否 RTL。
        is_default: 是否默认语言。
        sort: 排序。

    Returns:
        int: 新增返回 1，其余 0。
    """
    existing = (
        (
            await session.execute(
                select(SysI18nLocale).where(
                    func.lower(SysI18nLocale.code) == code.lower(),
                    SysI18nLocale.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        session.add(
            SysI18nLocale(
                code=code,
                name=name,
                rtl=rtl,
                is_default=is_default,
                sort=sort,
                status="enabled",
                is_overridden=False,
            )
        )
        await session.flush()
        return 1
    if existing.is_overridden:
        return 0
    existing.name = name
    existing.rtl = rtl
    existing.sort = sort
    existing.is_default = is_default
    return 0


async def _upsert_message(session: DbSession, msg_key: str, locale: str, value: str) -> int:
    """幂等写入文案行（未覆盖行按种子刷新；已覆盖行跳过）。

    Args:
        session: 种子会话（不提交）。
        msg_key: 文案 key。
        locale: 语言标识。
        value: 文案。

    Returns:
        int: 新增返回 1，其余 0。
    """
    existing = (
        (
            await session.execute(
                select(SysI18nMessage).where(
                    SysI18nMessage.msg_key == msg_key,
                    func.lower(SysI18nMessage.locale) == locale.lower(),
                    SysI18nMessage.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        session.add(
            SysI18nMessage(
                msg_key=msg_key,
                name=msg_key,
                locale=locale,
                value=value,
                status="enabled",
                is_overridden=False,
            )
        )
        await session.flush()
        return 1
    if existing.is_overridden:
        return 0
    existing.value = value
    existing.name = msg_key
    return 0


async def _ensure_single_default(session: DbSession) -> None:
    """校验并修复默认语言（恰一条）。

    Args:
        session: 种子会话（不提交）。

    Raises:
        LocaleDefaultConflictError: 默认语言标记多于一条（`44006`）。
    """
    rows = (
        (
            await session.execute(
                select(SysI18nLocale).where(
                    SysI18nLocale.is_default.is_(True),
                    SysI18nLocale.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(rows) > 1:
        raise LocaleDefaultConflictError(f"默认语言标记重复（{len(rows)} 条），须恰好一条")
    if rows:
        return
    fallback = (
        (
            await session.execute(
                select(SysI18nLocale).where(
                    func.lower(SysI18nLocale.code) == SEED_DEFAULT_LOCALE.lower(),
                    SysI18nLocale.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if fallback is not None:
        fallback.is_default = True


async def seed_i18n_in_session(session: DbSession) -> int:
    """在给定会话内幂等写入语言清单与语言包种子（不提交）。

    Args:
        session: 种子会话（编排层负责事务）。

    Returns:
        int: 新增行数（重复执行尽量为 0）。

    Raises:
        LocaleDefaultConflictError: 默认语言标记重复（`44006`）。
    """
    created = 0
    for code, name, rtl, is_default, sort in SEED_LOCALES:
        created += await _upsert_locale(session, code, name, rtl, is_default, sort)
    await _ensure_single_default(session)
    for msg_key, zh, en in MESSAGE_SEEDS:
        created += await _upsert_message(session, msg_key, ZH_LOCALE, zh)
        created += await _upsert_message(session, msg_key, EN_LOCALE, en)
    return created


async def seed_i18n_entry(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
    """种子编排入口（不建连接、不提交，写入并入 XA 分支事务）。

    Args:
        session: 已绑定租户库分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    await seed_i18n_in_session(session)


def _database_url() -> str:
    """取种子目标 URL（环境变量 > 配置租户库模板）。

    Returns:
        str: 数据库 URL。
    """
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    return get_settings().database.tenants.url


async def _run() -> int:
    """自建引擎执行种子写入（内部单步排障用）。

    Returns:
        int: 新增行数。
    """
    engine = create_async_engine(_database_url())
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            created = await seed_i18n_in_session(session)
            await session.commit()
            return created
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="语言清单与语言包种子（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库（不建连）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.dry_run:
        print(f"[seed_i18n] 目标库：{_database_url()}（dry-run）")
        return 0
    created = asyncio.run(_run())
    print(f"[seed_i18n] 新增 {created} 行（幂等；重复执行输出 0）")
    return 0


def expected_rows() -> ConcurrentStableList[ExpectedRow]:
    """种子期望行（供种子预检比对）。

    Returns:
        ConcurrentStableList[ExpectedRow]: 清单与文案的期望行。
    """
    rows: ConcurrentStableList[ExpectedRow] = ConcurrentStableList()
    for code, name, _rtl, _is_default, _sort in SEED_LOCALES:
        rows.add(
            ExpectedRow(
                table="sys_i18n_locale",
                key=ConcurrentStableFrozenDict({"code": code}),
                values=ConcurrentStableFrozenDict({"name": name}),
            )
        )
    for msg_key, zh, _en in MESSAGE_SEEDS:
        rows.add(
            ExpectedRow(
                table="sys_i18n_message",
                key=ConcurrentStableFrozenDict({"code": msg_key, "locale": ZH_LOCALE}),
                values=ConcurrentStableFrozenDict({"value": zh}),
            )
        )
    return rows
