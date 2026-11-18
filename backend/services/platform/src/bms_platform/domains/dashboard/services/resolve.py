"""三级布局解析：个人偏好 → 角色模板 → 平台默认 → 内置最小布局（11_01）。

**为什么独立成类**：解析是工作台的热路径，且被「读取布局」「保存后校验」「用例断言」三处复用；
把「取数 + 回退 + 过滤」收在一处，服务层只管缓存与契约组装。

口径（架构 29 §4）：

- 个人布局非空即命中（`source=personal`）；
- 否则按角色集命中角色模板（角色类型优先级 + 角色主键升序取首个非空，规则在基座 `role_priority`）；
- 再否则取平台默认模板（`scope=platform` 且启用）；
- 三级皆空 → 启用内置卡按 `sort` 行流式最小布局（`source=empty`、`fallback=true`）；
- 每级命中后都**过滤未注册 / 已停用卡片**并保留告警，绝不因坏配置报错。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.dashboard.layout import (
    CardPlacement,
    CardSize,
    DashboardLayout,
    filter_placements,
    is_layout_empty,
    load_layout_config,
    minimal_layout,
    normalize_layout,
)
from bms_core.models.platform.dashboard import SCOPE_PLATFORM, STATUS_ENABLED
from bms_core.permission.role_priority import pick_role_candidate
from bms_core.preference.base import BasePreferenceStore
from bms_platform.domains.dashboard.repositories.card import DashboardCardRepository
from bms_platform.domains.dashboard.repositories.template import DashboardTemplateRepository
from bms_platform.domains.dashboard.schemas.layout import (
    DashboardLayoutCard,
    DashboardLayoutIssue,
    DashboardLayoutPayload,
    DashboardLayoutStructure,
)

__all__ = [
    "PERSONAL_LAYOUT_KEY",
    "SOURCE_EMPTY",
    "SOURCE_PERSONAL",
    "SOURCE_PLATFORM",
    "SOURCE_ROLE",
    "LayoutResolver",
    "to_layout_payload",
]

PERSONAL_LAYOUT_KEY = "dashboard.layout"
"""个人布局偏好键（偏好基座 `{域}.{键}` 规范；PC 与移动端同源）。"""

SOURCE_PERSONAL = "personal"
"""来源层级：个人布局。"""

SOURCE_ROLE = "role"
"""来源层级：角色模板。"""

SOURCE_PLATFORM = "platform"
"""来源层级：平台默认模板。"""

SOURCE_EMPTY = "empty"
"""来源层级：三级皆空，回退内置最小布局。"""


def _to_placements(layout: DashboardLayout) -> ConcurrentStableList[DashboardLayoutCard]:
    """布局放置项转契约项。

    Args:
        layout: 布局。

    Returns:
        ConcurrentStableList[DashboardLayoutCard]: 契约项（插入序）。
    """
    items: ConcurrentStableList[DashboardLayoutCard] = ConcurrentStableList()
    for placement in layout.cards:
        items.add(_to_placement(placement))
    return items


def _to_placement(placement: CardPlacement) -> DashboardLayoutCard:
    """单张卡片放置项转契约项。

    Args:
        placement: 放置项。

    Returns:
        DashboardLayoutCard: 契约项。
    """
    return DashboardLayoutCard(
        code=placement.code,
        x=placement.x,
        y=placement.y,
        w=placement.w,
        h=placement.h,
        visible=placement.visible,
    )


def to_layout_payload(layout: DashboardLayout) -> DashboardLayoutPayload:
    """布局转契约载荷。

    Args:
        layout: 布局。

    Returns:
        DashboardLayoutPayload: 契约载荷。
    """
    return DashboardLayoutPayload(cards=_to_placements(layout))


class LayoutResolver(BaseFrameworkObject):
    """三级解析器（读卡表 / 模板表 / 个人偏好，产出结构侧解析结果）。"""

    def __init__(
        self,
        *,
        cards: DashboardCardRepository,
        templates: DashboardTemplateRepository,
        preferences: BasePreferenceStore,
    ) -> None:
        """初始化。

        Args:
            cards: 卡片仓储。
            templates: 模板仓储。
            preferences: 用户偏好存储（个人布局）。
        """
        self._cards = cards
        self._templates = templates
        self._preferences = preferences

    async def cards_and_sizes(
        self,
    ) -> tuple[ConcurrentStableFrozenDict[str, bool], ConcurrentStableFrozenDict[str, CardSize]]:
        """取卡片启用状态与默认尺寸（全量卡片，含停用）。

        Returns:
            tuple: （卡片标识 → 是否启用, 卡片标识 → 默认尺寸）。
        """
        rows = await self._cards.list_cards()
        enabled: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
        sizes: ConcurrentStableDict[str, CardSize] = ConcurrentStableDict()
        for row in rows:
            enabled.set(row.code, row.status == STATUS_ENABLED)
            sizes.set(row.code, CardSize(code=row.code, width=int(row.default_width), height=int(row.default_height)))
        return ConcurrentStableFrozenDict(enabled), ConcurrentStableFrozenDict(sizes)

    async def resolve(
        self,
        *,
        role_types: ConcurrentStableList[tuple[str, int]],
    ) -> DashboardLayoutStructure:
        """解析当前用户生效布局（不含可选卡片清单）。

        Args:
            role_types: 用户角色集（`(role_type, role_id)` 插入序）。

        Returns:
            DashboardLayoutStructure: 解析结果（`source` / `template_id` / 告警齐全）。
        """
        enabled, sizes = await self.cards_and_sizes()
        personal = await self._personal_structure(enabled=enabled, sizes=sizes)
        if personal is not None:
            return personal
        role = await self._role_structure(role_types=role_types, enabled=enabled, sizes=sizes)
        if role is not None:
            return role
        platform = await self._platform_structure(enabled=enabled, sizes=sizes)
        if platform is not None:
            return platform
        return self._empty_structure(enabled=enabled, sizes=sizes)

    async def _personal_structure(
        self,
        *,
        enabled: ConcurrentStableFrozenDict[str, bool],
        sizes: ConcurrentStableFrozenDict[str, CardSize],
    ) -> DashboardLayoutStructure | None:
        """个人布局层级（无个人布局 / 全不可见时返回 None）。

        Args:
            enabled: 卡片启用状态。
            sizes: 卡片默认尺寸。

        Returns:
            DashboardLayoutStructure | None: 命中结果。
        """
        raw = await self._preferences.get(PERSONAL_LAYOUT_KEY)
        layout = normalize_layout(raw, sizes=sizes)
        return self._structure_from(
            layout=layout,
            source=SOURCE_PERSONAL,
            role_id=0,
            template_id=0,
            enabled=enabled,
        )

    async def _role_structure(
        self,
        *,
        role_types: ConcurrentStableList[tuple[str, int]],
        enabled: ConcurrentStableFrozenDict[str, bool],
        sizes: ConcurrentStableFrozenDict[str, CardSize],
    ) -> DashboardLayoutStructure | None:
        """角色模板层级（按角色优先级取首个非空）。

        Args:
            role_types: 用户角色集。
            enabled: 卡片启用状态。
            sizes: 卡片默认尺寸。

        Returns:
            DashboardLayoutStructure | None: 命中结果。
        """
        if not role_types:
            return None
        templates = await self._templates.list_role_templates()
        by_role: ConcurrentStableDict[int, tuple[DashboardLayout, int]] = ConcurrentStableDict()
        for template in templates:
            by_role.set(
                int(template.role_id),
                (normalize_layout(load_layout_config(template.layout_config), sizes=sizes), int(template.id)),
            )
        candidates: ConcurrentStableList[tuple[str, int, DashboardLayout | None]] = ConcurrentStableList()
        for role_type, role_id in role_types:
            entry = by_role.get(role_id)
            candidates.add((role_type, role_id, entry[0] if entry is not None else None))
        role_id, layout = pick_role_candidate(candidates, is_empty=is_layout_empty)
        if role_id is None or layout is None:
            return None
        entry = by_role.get(role_id)
        template_id = entry[1] if entry is not None else 0
        return self._structure_from(
            layout=layout,
            source=SOURCE_ROLE,
            role_id=role_id,
            template_id=template_id,
            enabled=enabled,
        )

    async def _platform_structure(
        self,
        *,
        enabled: ConcurrentStableFrozenDict[str, bool],
        sizes: ConcurrentStableFrozenDict[str, CardSize],
    ) -> DashboardLayoutStructure | None:
        """平台默认模板层级。

        Args:
            enabled: 卡片启用状态。
            sizes: 卡片默认尺寸。

        Returns:
            DashboardLayoutStructure | None: 命中结果。
        """
        template = await self._templates.get_platform()
        if template is None or template.status != STATUS_ENABLED or template.scope != SCOPE_PLATFORM:
            return None
        layout = normalize_layout(load_layout_config(template.layout_config), sizes=sizes)
        return self._structure_from(
            layout=layout,
            source=SOURCE_PLATFORM,
            role_id=0,
            template_id=int(template.id),
            enabled=enabled,
        )

    def _empty_structure(
        self,
        *,
        enabled: ConcurrentStableFrozenDict[str, bool],
        sizes: ConcurrentStableFrozenDict[str, CardSize],
    ) -> DashboardLayoutStructure:
        """内置最小布局（三级皆空时）。

        Args:
            enabled: 卡片启用状态。
            sizes: 卡片默认尺寸。

        Returns:
            DashboardLayoutStructure: 解析结果（`source=empty`、`fallback=true`）。
        """
        ordered: ConcurrentStableList[CardSize] = ConcurrentStableList(
            size for code, size in sizes.items() if enabled.get(code)
        )
        layout = minimal_layout(ConcurrentStableFrozenList(ordered))
        return DashboardLayoutStructure(
            layout=to_layout_payload(layout),
            source=SOURCE_EMPTY,
            role_id=0,
            template_id=0,
            fallback=True,
            warnings=ConcurrentStableList(),
        )

    def _structure_from(
        self,
        *,
        layout: DashboardLayout,
        source: str,
        role_id: int,
        template_id: int,
        enabled: ConcurrentStableFrozenDict[str, bool],
    ) -> DashboardLayoutStructure | None:
        """过滤失效卡片并组装解析结果（全空返回 None 以继续回退）。

        Args:
            layout: 归一后的布局。
            source: 来源层级。
            role_id: 角色主键（无则 0）。
            template_id: 模板主键（无则 0）。
            enabled: 卡片启用状态。

        Returns:
            DashboardLayoutStructure | None: 非空结果；布局无可见卡片时为 None。
        """
        filtered, issues = filter_placements(layout, enabled=enabled)
        if is_layout_empty(filtered):
            return None
        warnings: ConcurrentStableList[DashboardLayoutIssue] = ConcurrentStableList()
        for issue in issues:
            warnings.add(DashboardLayoutIssue(code=issue.code, reason=issue.reason))
        return DashboardLayoutStructure(
            layout=to_layout_payload(filtered),
            source=source,
            role_id=role_id,
            template_id=template_id,
            fallback=False,
            warnings=warnings,
        )
