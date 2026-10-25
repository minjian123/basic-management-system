"""平台服务：自定义图标落库实现（`IconStore` 协议；供 `DbIconRegistry` 委托）。

- 图标键租户内唯一（软删除同键恢复）；`icon_key = custom:{code}` 由基座派生；
- SVG 仅做**基础拒绝**：类型前缀 / 大小上限 / 脚本、事件属性、外链与 `javascript:`；
  内容深度清洗（白名单重写）归文件管理阶段；
- 删除前置引用检查：被菜单 `icon` 列引用时拒绝（`40206`）。
"""

import re
from typing import cast

import sqlalchemy as sa

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ConflictError, MenuReferencedError, NotFoundError, ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.icon.base import (
    DEFAULT_ICON_STATUS,
    ICON_SVG_MAX_BYTES,
    IconDraft,
    IconInfo,
    IconPatch,
    build_icon_key,
)
from bms_core.models.platform.icon import SysIcon
from bms_platform.domains.menu_form.public import SysMenu
from bms_platform.domains.permission_meta.repositories.icon import IconRepository

_SCRIPT_RE = re.compile(r"<\s*script", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
_EXTERNAL_URL_RE = re.compile(r"(?:href|xlink:href)\s*=\s*[\"']\s*(?:https?:|//)", re.IGNORECASE)
_JAVASCRIPT_RE = re.compile(r"javascript:", re.IGNORECASE)


def _request_locale() -> str:
    """当前请求语言（不支持时回退系统默认语言）。

    Returns:
        str: 生效语言标识。
    """
    locale = current_dict_locale.get() or DEFAULT_LOCALE
    return locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE


def validate_svg(svg: str) -> None:
    """SVG 基础校验（类型 / 大小 / 危险内容拒绝）。

    Args:
        svg: 内联 SVG 内容。

    Raises:
        ParamError: 内容为空、超限、非 SVG 或含脚本 / 事件属性 / 外链。
    """
    if not svg.strip():
        raise ParamError("SVG 内容不得为空")
    if len(svg.encode("utf-8")) > ICON_SVG_MAX_BYTES:
        raise ParamError(f"SVG 内容超过上限（{ICON_SVG_MAX_BYTES} 字节）")
    if "<svg" not in svg.lower():
        raise ParamError("仅支持 SVG 内容（缺少 <svg> 根元素）")
    if _SCRIPT_RE.search(svg):
        raise ParamError("SVG 不得包含 script 标签")
    if _EVENT_ATTR_RE.search(svg):
        raise ParamError("SVG 不得包含内联事件属性")
    if _JAVASCRIPT_RE.search(svg):
        raise ParamError("SVG 不得包含 javascript: 协议")
    if _EXTERNAL_URL_RE.search(svg):
        raise ParamError("SVG 不得引用外部资源")


def _derive_name(names: ConcurrentStableDict[str, str], fallback: str) -> str:
    """从多语言映射派生默认名称（优先请求语言，其次默认语言，最后回退）。

    Args:
        names: 语言标识 → 文案。
        fallback: 回退名称。

    Returns:
        str: 派生名称。
    """
    locale = _request_locale()
    return names.get(locale) or names.get(DEFAULT_LOCALE) or fallback


class IconStore(BaseFrameworkObject):
    """请求级图标落库实现（实现 `bms_core.icon.base.IconStore` 协议）。"""

    def __init__(self, uow: UnitOfWork, platform_uow: UnitOfWork) -> None:
        """初始化。

        Args:
            uow: 请求级工作单元（租户库：`sys_icon` / `sys_icon_i18n`）。
            platform_uow: 平台库工作单元（只读：`sys_menu` 引用计数）。
        """
        self._uow = uow
        self._platform_session = cast("DbSession", platform_uow.session)
        self._icons = IconRepository(cast("DbSession", uow.session))

    async def list(
        self, *, category: str | None = None, status: str | None = None, keyword: str | None = None
    ) -> ConcurrentStableList[IconInfo]:
        """列示图标（含多语言名称与引用计数）。

        Args:
            category: 图标分组（None 表示全部）。
            status: 状态（None 表示全部）。
            keyword: 关键字（None 表示不过滤）。

        Returns:
            ConcurrentStableList[IconInfo]: 图标清单。
        """
        rows = await self._icons.list_filtered(category=category, status=status, keyword=keyword)
        i18n = await self._icons.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        items: ConcurrentStableList[IconInfo] = ConcurrentStableList()
        for row in rows:
            items.add(
                await self._to_info(
                    row,
                    i18n.get(row.id) or ConcurrentStableDict[str, str](),
                )
            )
        return items

    async def get(self, code: str) -> IconInfo:
        """按图标键取详情。

        Args:
            code: 图标键。

        Returns:
            IconInfo: 图标定义。

        Raises:
            NotFoundError: 图标不存在（10002）。
        """
        row = await self._icons.get_by_code(code)
        if row is None:
            raise NotFoundError(f"图标不存在：{code}")
        i18n = await self._icons.list_i18n_all(ConcurrentStableList([row.id]))
        return await self._to_info(row, i18n.get(row.id) or ConcurrentStableDict[str, str]())

    async def create(self, draft: IconDraft) -> IconInfo:
        """新增图标（同键软删除行自动恢复）。

        Args:
            draft: 新增入参。

        Returns:
            IconInfo: 新增后的图标。

        Raises:
            ParamError: SVG 非法（10001）。
            ConflictError: 图标键已存在（10003）。
        """
        validate_svg(draft.svg)
        names = draft.i18n or ConcurrentStableDict({_request_locale(): draft.name})
        name = _derive_name(names, draft.name)
        async with self._uow.begin():
            if await self._icons.get_by_code(draft.code) is not None:
                raise ConflictError(f"图标键已存在：{draft.code}")
            deleted = await self._icons.get_deleted_by_code(draft.code)
            values = {
                "code": draft.code,
                "name": name,
                "category": draft.category,
                "tags": ",".join(draft.tags),
                "svg": draft.svg,
                "status": DEFAULT_ICON_STATUS,
            }
            if deleted is not None:
                # 先清 `deleted_at` 再更新：`update` 内部 `get()` 带软删过滤，不先恢复会取不到行。
                deleted.restore()
                row = await self._icons.update(deleted.id, **values)
            else:
                row = await self._icons.create(**values)
            if row is None:  # pragma: no cover - 恢复后行必存在
                raise NotFoundError(f"图标不存在：{draft.code}")
            await self._icons.replace_i18n(row.id, names)
        return await self._to_info(row, names)

    async def update(self, code: str, patch: IconPatch) -> IconInfo:
        """更新图标（按图标键定位；None 字段保持不变）。

        Args:
            code: 图标键。
            patch: 更新入参。

        Returns:
            IconInfo: 更新后的图标。

        Raises:
            NotFoundError: 图标不存在（10002）。
            ParamError: SVG 非法（10001）。
        """
        async with self._uow.begin():
            row = await self._icons.get_by_code(code)
            if row is None:
                raise NotFoundError(f"图标不存在：{code}")
            values: dict[str, object] = {}  # bare-collections:allow（局部 kwargs 组装，不跨边界）
            if patch.category is not None:
                values["category"] = patch.category
            if patch.tags is not None:
                values["tags"] = ",".join(patch.tags)
            if patch.svg is not None:
                validate_svg(patch.svg)
                values["svg"] = patch.svg
            if patch.status is not None:
                values["status"] = patch.status
            if patch.i18n is not None:
                values["name"] = _derive_name(patch.i18n, row.name)
            elif patch.name is not None:
                values["name"] = patch.name
            updated = await self._icons.update(row.id, **values)
            if updated is None:  # pragma: no cover - 已探测存在
                raise NotFoundError(f"图标不存在：{code}")
            if patch.i18n is not None:
                await self._icons.replace_i18n(row.id, patch.i18n)
        i18n = await self._icons.list_i18n_all(ConcurrentStableList([updated.id]))
        return await self._to_info(updated, i18n.get(updated.id) or ConcurrentStableDict[str, str]())

    async def delete(self, code: str) -> bool:
        """删除图标（被菜单引用时拒绝）。

        Args:
            code: 图标键。

        Returns:
            bool: 是否删除了既有图标。

        Raises:
            MenuReferencedError: 被菜单引用（40206）。
        """
        async with self._uow.begin():
            row = await self._icons.get_by_code(code)
            if row is None:
                return False
            if await self._count_menu_refs(code) > 0:
                raise MenuReferencedError(f"图标已被菜单引用，先解除引用或停用：{code}")
            await self._icons.soft_delete(row.id)
        return True

    async def _count_menu_refs(self, code: str) -> int:
        """统计引用该图标键的菜单数（平台库 `sys_menu.icon`）。

        Args:
            code: 图标键。

        Returns:
            int: 引用菜单数。
        """
        statement = (
            sa.select(sa.func.count())
            .select_from(SysMenu)
            .where(SysMenu.icon == build_icon_key(code), SysMenu.deleted_at.is_(None))
        )
        return int((await self._platform_session.execute(statement)).scalar_one())

    async def _to_info(self, row: SysIcon, names: ConcurrentStableDict[str, str]) -> IconInfo:
        """行 → 图标定义（含派生 icon key、标签拆分与引用计数）。

        Args:
            row: 图标行。
            names: 多语言名称映射。

        Returns:
            IconInfo: 图标定义。
        """
        tags = ConcurrentStableList(tag for tag in row.tags.split(",") if tag)
        return IconInfo(
            id=str(row.id),
            code=row.code,
            name=row.name,
            category=row.category,
            tags=tags,
            svg=row.svg,
            status=row.status,
            icon_key=build_icon_key(row.code),
            i18n=names,
            reference_count=await self._count_menu_refs(row.code),
        )
