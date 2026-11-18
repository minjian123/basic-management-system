"""首页工作台服务：卡片 / 模板 / 布局 / 角标编排 + 缓存失效（11_01）。

分层：解析逻辑在 `services/resolve.py`（`LayoutResolver`）；本模块负责写路径、缓存、契约组装与
跨端口编排（待办 / 未读 / 数据集探测）。

口径：

- 卡片表体量小，写路径直读库；**读路径**缓存解析结构（`layout:v{version}:{user}`）与可选卡片清单
  （`cards:v{version}:{locale}`），版本键 `version` 由卡片 / 模板写操作递增（架构 29 §6）；
- 保存 / 重置个人布局只失效本人解析缓存，**不递增版本**（不惊动其他用户）；
- 内置卡只允许改 `status`，其余字段与删除一律 `40308`；数据集卡可增删改。
"""

from __future__ import annotations

import json
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.exceptions import (
    DashboardBuiltinCardLockedError,
    DashboardCardCodeConflictError,
    DashboardCardNotFoundError,
    DashboardDatasetUnavailableError,
    DashboardLayoutInvalidError,
    DashboardPlatformTemplateExistsError,
    DashboardRoleNotFoundError,
    DashboardRoleTemplateExistsError,
    NotFoundError,
    ParamError,
)
from bms_core.core.exceptions import PermissionError as BizPermissionError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.dashboard.layout import (
    CARD_CODE_PATTERN,
    CHART_TYPES,
    DashboardLayout,
    LayoutIssue,
    is_valid_card_code,
    layout_json,
    load_layout_config,
    normalize_layout,
    parse_layout,
)
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.base import get_default_locale
from bms_core.models.platform.dashboard import (
    CARD_TYPE_BUILTIN,
    CARD_TYPE_DATASET,
    SCOPE_PLATFORM,
    SCOPE_ROLE,
    STATUS_ENABLED,
    STATUSES,
    TEMPLATE_SCOPES,
    SysDashboardCard,
    SysDashboardTemplate,
)
from bms_core.preference.base import BasePreferenceStore
from bms_platform.domains.dashboard.dto import BadgeCountView
from bms_platform.domains.dashboard.ports import (
    DatasetProbePort,
    NotificationBadgePort,
    RolePort,
    TodoCountPort,
)
from bms_platform.domains.dashboard.repositories.card import (
    DashboardCardI18nRepository,
    DashboardCardRepository,
)
from bms_platform.domains.dashboard.repositories.template import DashboardTemplateRepository
from bms_platform.domains.dashboard.schemas.badge import DashboardBadgeCount, DashboardBadges
from bms_platform.domains.dashboard.schemas.card import (
    DashboardCardCreate,
    DashboardCardList,
    DashboardCardMeta,
    DashboardCardRow,
    DashboardCardUpdate,
)
from bms_platform.domains.dashboard.schemas.layout import (
    DashboardLayoutIssue,
    DashboardLayoutResetResult,
    DashboardLayoutResolve,
    DashboardLayoutSaveResult,
    DashboardLayoutStructure,
)
from bms_platform.domains.dashboard.schemas.template import (
    DashboardTemplateCreate,
    DashboardTemplateRow,
    DashboardTemplateUpdate,
)
from bms_platform.domains.dashboard.services.resolve import (
    PERSONAL_LAYOUT_KEY,
    LayoutResolver,
)

__all__ = ["CACHE_DOMAIN", "DashboardService"]

_LOGGER = get_logger("bms.dashboard")

CACHE_DOMAIN = "dashboard"
"""缓存域简称（key 形如 `bms:{tenant}:dashboard:layout:v0:1001`）。"""

CACHE_TTL_CARDS = 300
"""可选卡片清单缓存 TTL（秒；实际写入带随机偏移）。"""

CACHE_TTL_LAYOUT = 60
"""解析结构缓存 TTL（秒；实际写入带随机偏移）。"""


class DashboardService(BaseFrameworkObject):
    """首页工作台服务：解析 / 卡片 / 模板 / 布局 / 角标。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        cards: DashboardCardRepository,
        card_i18n: DashboardCardI18nRepository,
        templates: DashboardTemplateRepository,
        preferences: BasePreferenceStore,
        roles: RolePort,
        todo: TodoCountPort,
        notifications: NotificationBadgePort,
        datasets: DatasetProbePort,
        cache: CacheRegion,
        tenant: str | None,
    ) -> None:
        """初始化。

        Args:
            session: 请求级会话（租户库）。
            uow: 请求级工作单元。
            cards: 卡片仓储。
            card_i18n: 卡片名多语言仓储。
            templates: 模板仓储。
            preferences: 用户偏好存储（个人布局）。
            roles: 角色读面。
            todo: 待办角标读面。
            notifications: 未读角标读面。
            datasets: 数据集可用性探测。
            cache: 缓存 Region。
            tenant: 租户标识（缓存 key 用）。
        """
        self._session = session
        self._uow = uow
        self._cards = cards
        self._card_i18n = card_i18n
        self._templates = templates
        self._preferences = preferences
        self._roles = roles
        self._todo = todo
        self._notifications = notifications
        self._datasets = datasets
        self._cache = cache
        self._tenant = tenant
        self._resolver = LayoutResolver(cards=cards, templates=templates, preferences=preferences)

    # ------------------------------------------------------------------ 缓存

    def _version_key(self) -> str:
        """版本键。

        Returns:
            str: `bms:{tenant}:dashboard:version`。
        """
        return self._cache.build_key("version", tenant=self._tenant)

    async def version(self) -> int:
        """取租户级版本号（缓存不可用 / 未初始化按 0）。

        Returns:
            int: 版本号。
        """
        raw = await self._cache.aget(self._version_key())
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0

    async def _bump_version(self) -> None:
        """递增租户级版本号（旧缓存自然过期，不遍历删除）。"""
        await self._cache.aincrease(self._version_key())

    async def _drop_layout_cache(self, user_id: int) -> None:
        """失效某用户的解析缓存。

        Args:
            user_id: 用户主键。
        """
        version = await self.version()
        key = self._cache.build_key(f"layout:v{version}:{user_id}", tenant=self._tenant)
        await self._cache.adelete(key)

    # ------------------------------------------------------------------ 布局

    async def _catalog(self, locale: str) -> ConcurrentStableList[DashboardCardMeta]:
        """取可选卡片清单（启用卡，本地化名称；按 `sort` 升序）。

        Args:
            locale: 请求语言。

        Returns:
            ConcurrentStableList[DashboardCardMeta]: 卡片元数据清单。
        """
        version = await self.version()
        key = self._cache.build_key(f"cards:v{version}:{locale}", tenant=self._tenant)
        cached = await self._cache.aget(key)
        if isinstance(cached, list):
            cached_items: ConcurrentStableList[DashboardCardMeta] = ConcurrentStableList()
            for entry in cast("list[object]", cached):
                if isinstance(entry, dict):
                    cached_items.add(DashboardCardMeta.model_validate(cast("dict[str, object]", entry)))
            return cached_items
        rows = await self._cards.list_cards(enabled_only=True)
        names = await self._card_i18n.load_names(
            ConcurrentStableList(int(row.id) for row in rows), locales=self._locale_chain(locale)
        )
        catalog: ConcurrentStableList[DashboardCardMeta] = ConcurrentStableList()
        for row in rows:
            catalog.add(self._card_meta(row, names.get(int(row.id)) or row.name))
        await self._cache.aset(key, [item.model_dump(mode="json") for item in catalog], CACHE_TTL_CARDS)
        return catalog

    def _locale_chain(self, locale: str) -> ConcurrentStableList[str]:
        """语言优先级链（请求语言 → 系统默认语言，去空去重）。

        Args:
            locale: 请求语言。

        Returns:
            ConcurrentStableList[str]: 语言优先级序。
        """
        chain: ConcurrentStableList[str] = ConcurrentStableList()
        for candidate in (locale, get_default_locale()):
            text = (candidate or "").strip()
            if text and text not in chain:
                chain.add(text)
        return chain

    def _card_meta(self, row: SysDashboardCard, name: str) -> DashboardCardMeta:
        """卡片行转元数据契约。

        Args:
            row: 卡片行。
            name: 当前语言名称。

        Returns:
            DashboardCardMeta: 卡片元数据。
        """
        return DashboardCardMeta(
            code=row.code,
            name=name,
            card_type=row.card_type,
            render_key=row.render_key,
            dataset_id=row.dataset_id,
            chart_type=row.chart_type,
            chart_config=self._chart_config_of(row),
            default_width=int(row.default_width),
            default_height=int(row.default_height),
            mobile_supported=bool(row.mobile_supported),
            data_endpoint=row.data_endpoint,
            sort=int(row.sort),
        )

    def _chart_config_of(self, row: SysDashboardCard) -> ConcurrentStableDict[str, object] | None:
        """解析卡片图表样式覆盖（非法 JSON 视为未配置）。

        Args:
            row: 卡片行。

        Returns:
            ConcurrentStableDict[str, object] | None: 样式覆盖；未配置 / 非法为 None。
        """
        if not row.chart_config:
            return None
        try:
            parsed = json.loads(row.chart_config)
        except (TypeError, ValueError):
            _LOGGER.warning("卡片图表配置非法（按未配置处理）", code=row.code)
            return None
        if not isinstance(parsed, dict):
            return None
        return ConcurrentStableDict(cast("dict[str, object]", parsed))

    async def resolve_layout(
        self,
        *,
        user_id: int,
        role_types: ConcurrentStableList[tuple[str, int]],
        locale: str,
    ) -> DashboardLayoutResolve:
        """解析当前用户生效布局 + 可选卡片清单。

        Args:
            user_id: 用户主键。
            role_types: 用户角色集。
            locale: 请求语言。

        Returns:
            DashboardLayoutResolve: 布局解析响应。
        """
        version = await self.version()
        key = self._cache.build_key(f"layout:v{version}:{user_id}", tenant=self._tenant)
        cached = await self._cache.aget(key)
        structure: DashboardLayoutStructure | None = None
        if isinstance(cached, dict):
            structure = DashboardLayoutStructure.model_validate(cached)
        if structure is None:
            structure = await self._resolver.resolve(role_types=role_types)
            await self._cache.aset(key, structure.model_dump(mode="json"), CACHE_TTL_LAYOUT)
        catalog = await self._catalog(locale)
        return DashboardLayoutResolve(
            layout=structure.layout,
            source=structure.source,
            role_id=structure.role_id,
            template_id=structure.template_id,
            fallback=structure.fallback,
            warnings=structure.warnings,
            available_cards=catalog,
        )

    async def save_layout(self, *, user_id: int, layout_config: object) -> DashboardLayoutSaveResult:
        """保存个人布局（整份覆盖；严格校验）。

        Args:
            user_id: 用户主键。
            layout_config: 布局配置（请求体 `layout`）。

        Returns:
            DashboardLayoutSaveResult: 保存结果（含引用已停用卡片的告警）。

        Raises:
            DashboardLayoutInvalidError: 布局结构非法（`40304`）。
            DashboardCardNotFoundError: 引用未注册卡片（`40301`）。
        """
        enabled, sizes = await self._resolver.cards_and_sizes()
        layout, issues = parse_layout(layout_config, sizes=sizes)
        if issues:
            raise DashboardLayoutInvalidError(
                "工作台布局校验失败：" + self._describe_issues(issues),
                data={"issues": [{"code": issue.code, "reason": issue.reason} for issue in issues]},
            )
        unknown: ConcurrentStableList[str] = ConcurrentStableList(
            placement.code for placement in layout.cards if placement.code not in enabled
        )
        if unknown:
            raise DashboardCardNotFoundError("布局引用未注册卡片：" + "、".join(unknown))
        warnings: ConcurrentStableList[DashboardLayoutIssue] = ConcurrentStableList(
            DashboardLayoutIssue(code=placement.code, reason="card_disabled")
            for placement in layout.cards
            if not enabled.get(placement.code)
        )
        await self._preferences.set(PERSONAL_LAYOUT_KEY, json.loads(layout_json(layout)))
        await self._drop_layout_cache(user_id)
        return DashboardLayoutSaveResult(applied=True, warnings=warnings)

    def _describe_issues(self, issues: ConcurrentStableList[LayoutIssue]) -> str:
        """把布局问题项拼成可读描述。

        Args:
            issues: 问题项清单。

        Returns:
            str: 描述文本。
        """
        parts: ConcurrentStableList[str] = ConcurrentStableList(
            f"{issue.code or '-'}:{issue.reason}" for issue in issues
        )
        return "、".join(parts)

    async def reset_layout(self, *, user_id: int) -> DashboardLayoutResetResult:
        """一键重置个人布局（删除偏好，回退角色 / 平台 / 内置最小布局）。

        Args:
            user_id: 用户主键。

        Returns:
            DashboardLayoutResetResult: 是否删除到既有个人布局。
        """
        removed = await self._preferences.reset(PERSONAL_LAYOUT_KEY)
        await self._drop_layout_cache(user_id)
        return DashboardLayoutResetResult(applied=removed)

    # ------------------------------------------------------------------ 卡片

    async def list_cards(self, *, card_type: str | None, locale: str) -> DashboardCardList:
        """卡片列表（含停用；按 `sort` 升序）。

        Args:
            card_type: 卡片类型筛选（None 不筛选）。
            locale: 请求语言。

        Returns:
            DashboardCardList: 卡片清单。
        """
        rows = await self._cards.list_cards(card_type=card_type)
        ids: ConcurrentStableList[int] = ConcurrentStableList(int(row.id) for row in rows)
        names = await self._card_i18n.load_names(ids, locales=self._locale_chain(locale))
        all_names = await self._card_i18n.load_all_names(ids, locales=self._locale_chain(locale))
        items: ConcurrentStableList[DashboardCardRow] = ConcurrentStableList()
        for row in rows:
            meta = self._card_meta(row, names.get(int(row.id)) or row.name)
            items.add(
                DashboardCardRow(
                    **meta.model_dump(),
                    id=int(row.id),
                    status=row.status,
                    i18n=all_names.get(int(row.id)) or ConcurrentStableDict(),
                )
            )
        return DashboardCardList(items=items, total=len(items))

    async def create_card(self, *, payload: DashboardCardCreate, locale: str) -> DashboardCardRow:
        """新建数据集卡。

        Args:
            payload: 新建请求。
            locale: 请求语言。

        Returns:
            DashboardCardRow: 新建的卡片行。

        Raises:
            DashboardBuiltinCardLockedError: 试图新建内置卡（`40308`）。
            DashboardCardCodeConflictError: 标识重复（`40302`）。
            DashboardDatasetUnavailableError: 数据集不可用（`40303`）。
            ParamError: 标识 / 类型 / 状态非法（`10001`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            if payload.card_type != CARD_TYPE_DATASET:
                raise DashboardBuiltinCardLockedError("内置卡由平台种子登记，租户不可新建")
            self._assert_card_payload(payload.code, payload.chart_type, payload.status)
            if await self._cards.get_by_code(payload.code) is not None:
                raise DashboardCardCodeConflictError(f"卡片标识已存在：{payload.code}")
            available = await self._datasets.is_available(payload.dataset_id)
            if available is False:
                raise DashboardDatasetUnavailableError(f"数据集不可用：{payload.dataset_id}")
            if available is None:
                _LOGGER.warning("数据集未接入校验（按未校验通过）", dataset_id=payload.dataset_id)
            names = self._names_of(payload.i18n, payload.name, locale)
            row = SysDashboardCard(
                code=payload.code,
                name=self._derive_name(names, payload.name, locale),
                card_type=CARD_TYPE_DATASET,
                render_key="",
                dataset_id=payload.dataset_id,
                chart_type=payload.chart_type,
                chart_config=json.dumps(dict(payload.chart_config), ensure_ascii=False)
                if payload.chart_config is not None
                else None,
                data_endpoint="",
                default_width=payload.default_width,
                default_height=payload.default_height,
                mobile_supported=payload.mobile_supported,
                sort=payload.sort,
                status=payload.status,
            )
            self._session.add(row)
            await self._session.flush()
            await self._card_i18n.replace_names(int(row.id), names)
            await self._bump_version()
            return self._card_row(row, names)

    async def update_card(self, *, code: str, payload: DashboardCardUpdate, locale: str) -> DashboardCardRow:
        """编辑卡片（数据集卡全字段；内置卡只允许 `status`）。

        Args:
            code: 卡片标识。
            payload: 编辑请求。
            locale: 请求语言。

        Returns:
            DashboardCardRow: 更新后的卡片行。

        Raises:
            DashboardCardNotFoundError: 卡片不存在（`40301`）。
            DashboardBuiltinCardLockedError: 内置卡改定义（`40308`）。
            ParamError: 图表类型 / 状态非法（`10001`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._cards.get_by_code(code)
            if row is None:
                raise DashboardCardNotFoundError(f"卡片不存在：{code}")
            if row.card_type == CARD_TYPE_BUILTIN and (payload.model_fields_set - {"status"}):
                raise DashboardBuiltinCardLockedError(f"内置卡不可修改定义：{code}")
            if payload.chart_type is not None and payload.chart_type not in CHART_TYPES:
                raise ParamError(f"图表类型不在白名单：{payload.chart_type}")
            if payload.status is not None and payload.status not in STATUSES:
                raise ParamError(f"状态非法：{payload.status}")
            if payload.dataset_id is not None:
                row.dataset_id = payload.dataset_id
            if payload.chart_type is not None:
                row.chart_type = payload.chart_type
            if payload.chart_config is not None:
                row.chart_config = json.dumps(dict(payload.chart_config), ensure_ascii=False)
            if payload.default_width is not None:
                row.default_width = payload.default_width
            if payload.default_height is not None:
                row.default_height = payload.default_height
            if payload.mobile_supported is not None:
                row.mobile_supported = payload.mobile_supported
            if payload.sort is not None:
                row.sort = payload.sort
            if payload.status is not None:
                row.status = payload.status
            names: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            if payload.i18n is not None:
                names = self._names_of(payload.i18n, row.name, locale)
                row.name = self._derive_name(names, row.name, locale)
                await self._card_i18n.replace_names(int(row.id), names)
            elif payload.name is not None:
                row.name = payload.name
            await self._session.flush()
            await self._bump_version()
            return self._card_row(row, names)

    async def delete_card(self, *, code: str) -> bool:
        """删除卡片（数据集卡软删除；内置卡拒绝）。

        Args:
            code: 卡片标识。

        Returns:
            bool: 是否删除到既有卡片。

        Raises:
            DashboardCardNotFoundError: 卡片不存在（`40301`）。
            DashboardBuiltinCardLockedError: 内置卡不可删（`40308`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._cards.get_by_code(code)
            if row is None:
                raise DashboardCardNotFoundError(f"卡片不存在：{code}")
            if row.card_type == CARD_TYPE_BUILTIN:
                raise DashboardBuiltinCardLockedError(f"内置卡不可删除：{code}")
            row.soft_delete()
            await self._card_i18n.soft_delete_names(int(row.id))
            await self._session.flush()
            await self._bump_version()
            return True

    def _assert_card_payload(self, code: str, chart_type: str, status: str) -> None:
        """校验卡片标识 / 图表类型 / 状态形态。

        Args:
            code: 卡片标识。
            chart_type: 图表类型。
            status: 状态。

        Raises:
            ParamError: 形态非法（`10001`）。
        """
        if not is_valid_card_code(code):
            raise ParamError(f"卡片标识非法（应匹配 {CARD_CODE_PATTERN}）：{code}")
        if chart_type not in CHART_TYPES:
            raise ParamError(f"图表类型不在白名单：{chart_type}")
        if status not in STATUSES:
            raise ParamError(f"状态非法：{status}")

    def _names_of(
        self, i18n: ConcurrentStableDict[str, str], fallback: str, locale: str
    ) -> ConcurrentStableDict[str, str]:
        """整理多语言文案（缺省补请求语言与系统默认语言）。

        Args:
            i18n: 请求提供的多语言文案。
            fallback: 主表文案兜底值。
            locale: 请求语言。

        Returns:
            ConcurrentStableDict[str, str]: 语言 → 文案（至少含请求语言）。
        """
        names: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for key, value in i18n.items():
            text = (value or "").strip()
            if text:
                names.set(key, text)
        if len(names) == 0:
            names.set(locale, fallback)
            names.set(get_default_locale(), fallback)
        return names

    def _derive_name(self, names: ConcurrentStableDict[str, str], fallback: str, locale: str) -> str:
        """派生主表默认文案（请求语言 → 系统默认语言 → 首个有值 → 兜底）。

        Args:
            names: 语言 → 文案。
            fallback: 兜底值。
            locale: 请求语言。

        Returns:
            str: 主表文案（恒非空）。
        """
        for candidate in (locale, get_default_locale()):
            text = names.get(candidate)
            if text:
                return text
        for value in names.values():
            if value:
                return value
        return fallback

    def _card_row(self, row: SysDashboardCard, names: ConcurrentStableDict[str, str]) -> DashboardCardRow:
        """卡片行转管理面契约。

        Args:
            row: 卡片行。
            names: 语言 → 文案（本次写入的文案；空表示沿用主表）。

        Returns:
            DashboardCardRow: 管理面行。
        """
        meta = self._card_meta(row, row.name)
        return DashboardCardRow(**meta.model_dump(), id=int(row.id), status=row.status, i18n=names)

    # ------------------------------------------------------------------ 模板

    async def list_templates(self, *, scope: str | None) -> ConcurrentStableList[DashboardTemplateRow]:
        """模板列表。

        Args:
            scope: 层级筛选（None 不筛选）。

        Returns:
            ConcurrentStableList[DashboardTemplateRow]: 模板清单。
        """
        rows = await self._templates.list_templates(scope=scope)
        items: ConcurrentStableList[DashboardTemplateRow] = ConcurrentStableList()
        for row in rows:
            items.add(self._template_row(row))
        return items

    def _template_row(self, row: SysDashboardTemplate) -> DashboardTemplateRow:
        """模板行转契约。

        Args:
            row: 模板行。

        Returns:
            DashboardTemplateRow: 模板契约行。
        """
        layout = normalize_layout(load_layout_config(row.layout_config), sizes=ConcurrentStableFrozenDict({}))
        return DashboardTemplateRow(
            id=int(row.id),
            scope=row.scope,
            role_id=int(row.role_id),
            name=row.name,
            status=row.status,
            card_count=len(layout.cards),
        )

    async def create_template(
        self,
        *,
        payload: DashboardTemplateCreate,
        role_types: ConcurrentStableList[tuple[str, int]],
    ) -> DashboardTemplateRow:
        """新建模板（平台默认唯一 + 角色唯一）。

        Args:
            payload: 新建请求。
            role_types: 当前用户角色集（平台层级要求超管）。

        Returns:
            DashboardTemplateRow: 新建的模板行。

        Raises:
            ParamError: 层级 / 状态非法（`10001`）。
            PermissionError: 非平台超管（`30001`）。
            DashboardPlatformTemplateExistsError: 平台模板已存在（`40306`）。
            DashboardRoleTemplateExistsError: 角色模板已存在（`40307`）。
            DashboardRoleNotFoundError: 角色不存在或停用（`40305`）。
            DashboardLayoutInvalidError: 布局非法（`40304`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            if payload.scope not in TEMPLATE_SCOPES:
                raise ParamError(f"模板层级非法：{payload.scope}")
            if payload.status not in STATUSES:
                raise ParamError(f"状态非法：{payload.status}")
            if payload.scope == SCOPE_PLATFORM:
                self._assert_platform_admin(role_types)
                if await self._templates.get_platform() is not None:
                    raise DashboardPlatformTemplateExistsError("平台默认模板仅允许一份")
            else:
                await self._assert_role_available(payload.role_id)
                if await self._templates.find_by_role(payload.role_id) is not None:
                    raise DashboardRoleTemplateExistsError(f"该角色已存在模板：{payload.role_id}")
            layout = await self._strict_layout(payload.layout_config)
            row = SysDashboardTemplate(
                scope=payload.scope,
                role_id=payload.role_id if payload.scope == SCOPE_ROLE else 0,
                name=payload.name,
                layout_config=layout_json(layout),
                status=payload.status,
            )
            self._session.add(row)
            await self._session.flush()
            await self._bump_version()
            return self._template_row(row)

    async def update_template(
        self,
        *,
        template_id: int,
        payload: DashboardTemplateUpdate,
        role_types: ConcurrentStableList[tuple[str, int]],
    ) -> DashboardTemplateRow:
        """编辑模板（`scope` 与 `role_id` 不可改）。

        Args:
            template_id: 模板主键。
            payload: 编辑请求。
            role_types: 当前用户角色集（平台层级要求超管）。

        Returns:
            DashboardTemplateRow: 更新后的模板行。

        Raises:
            NotFoundError: 模板不存在（`10002`）。
            PermissionError: 非平台超管（`30001`）。
            ParamError: 状态非法（`10001`）。
            DashboardLayoutInvalidError: 布局非法（`40304`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._templates.get(template_id)
            if row is None:
                raise NotFoundError(f"模板不存在：{template_id}")
            if row.scope == SCOPE_PLATFORM:
                self._assert_platform_admin(role_types)
            if payload.status is not None:
                if payload.status not in STATUSES:
                    raise ParamError(f"状态非法：{payload.status}")
                row.status = payload.status
            if payload.name is not None:
                row.name = payload.name
            if payload.layout_config is not None:
                layout = await self._strict_layout(payload.layout_config)
                row.layout_config = layout_json(layout)
            await self._session.flush()
            await self._bump_version()
            return self._template_row(row)

    async def delete_template(
        self, *, template_id: int, role_types: ConcurrentStableList[tuple[str, int]]
    ) -> bool:
        """删除模板（平台模板删后回退内置最小布局）。

        Args:
            template_id: 模板主键。
            role_types: 当前用户角色集（平台层级要求超管）。

        Returns:
            bool: 是否删除到既有模板。

        Raises:
            NotFoundError: 模板不存在（`10002`）。
            PermissionError: 非平台超管（`30001`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._templates.get(template_id)
            if row is None:
                raise NotFoundError(f"模板不存在：{template_id}")
            if row.scope == SCOPE_PLATFORM:
                self._assert_platform_admin(role_types)
            row.soft_delete()
            await self._session.flush()
            await self._bump_version()
            return True

    async def _strict_layout(self, config: object) -> DashboardLayout:
        """严格校验模板布局。

        Args:
            config: 布局配置（请求体）。

        Returns:
            DashboardLayout: 布局。

        Raises:
            DashboardLayoutInvalidError: 布局非法（`40304`）。
        """
        _enabled, sizes = await self._resolver.cards_and_sizes()
        layout, issues = parse_layout(config, sizes=sizes)
        if issues:
            raise DashboardLayoutInvalidError(
                "工作台布局校验失败：" + self._describe_issues(issues),
                data={"issues": [{"code": issue.code, "reason": issue.reason} for issue in issues]},
            )
        return layout

    def _assert_platform_admin(self, role_types: ConcurrentStableList[tuple[str, int]]) -> None:
        """校验当前用户为平台超管（平台默认模板写操作要求）。

        Args:
            role_types: 当前用户角色集。

        Raises:
            PermissionError: 非平台超管（`30001`）。
        """
        if not any(role_type == "platform_admin" for role_type, _role_id in role_types):
            raise BizPermissionError("平台默认模板仅平台超管可维护")

    async def _assert_role_available(self, role_id: int) -> None:
        """校验角色模板绑定的角色存在且启用。

        Args:
            role_id: 角色主键。

        Raises:
            DashboardRoleNotFoundError: 角色不存在或停用（`40305`）。
        """
        if role_id <= 0:
            raise DashboardRoleNotFoundError("角色模板必须绑定有效角色")
        summaries = await self._roles.roles_by_ids(ConcurrentStableList((role_id,)))
        for summary in summaries:
            if int(summary.id) == role_id and summary.status == STATUS_ENABLED:
                return
        raise DashboardRoleNotFoundError(f"角色不存在或已停用：{role_id}")

    # ------------------------------------------------------------------ 角标

    async def badges(self, *, user_id: int) -> DashboardBadges:
        """取待办与未读角标（统一出口）。

        Args:
            user_id: 用户主键。

        Returns:
            DashboardBadges: 角标聚合响应。
        """
        todo = await self._todo.todo_count(user_id)
        notification = await self._notifications.unread_count(user_id)
        return DashboardBadges(todo=self._badge(todo), notification=self._badge(notification))

    def _badge(self, view: BadgeCountView) -> DashboardBadgeCount:
        """角标视图转契约。

        Args:
            view: 角标视图。

        Returns:
            DashboardBadgeCount: 角标契约。
        """
        return DashboardBadgeCount(count=view.count, available=view.available, reason=view.reason)
