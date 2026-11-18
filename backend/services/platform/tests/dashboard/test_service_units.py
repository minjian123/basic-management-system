"""服务层分支：空回退 / 平台模板权限与删除 / 缓存与图表配置容错（Kiwi 2528）。

**为什么用替身**：平台默认模板全库唯一，直接改删会影响并行用例；这些分支用替身验证语义，
真库路径由接口用例覆盖。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.exceptions import DashboardPlatformTemplateExistsError, DashboardRoleTemplateExistsError
from bms_core.core.exceptions import PermissionError as BizPermissionError
from bms_core.dashboard.layout import CardSize
from bms_core.models.platform.dashboard import SCOPE_PLATFORM
from bms_platform.domains.dashboard.dto import BadgeCountView
from bms_platform.domains.dashboard.repositories.adapters import NullDatasetProbe, NullTodoCountProvider
from bms_platform.domains.dashboard.schemas.template import (
    DashboardTemplateCreate,
    DashboardTemplateUpdate,
)
from bms_platform.domains.dashboard.services.dashboard import DashboardService

pytestmark = pytest.mark.kiwi_id(2528)

@dataclass
class _RoleSummaryStub:
    """角色摘要替身（只含工作台读面所需字段）。"""

    id: int
    status: str


@dataclass
class _CardStub:
    """卡片行替身（只含工作台读面所需字段）。"""

    id: int
    code: str
    name: str
    card_type: str
    render_key: str
    dataset_id: str | None
    chart_type: str | None
    chart_config: str | None
    data_endpoint: str
    default_width: int
    default_height: int
    mobile_supported: bool
    sort: int
    status: str


def _empty_layout() -> ConcurrentStableDict[str, object]:
    """空布局配置（契约字段为并发字典，测试构造同口径）。

    Returns:
        ConcurrentStableDict[str, object]: `{"cards": []}`。
    """
    return ConcurrentStableDict({"cards": []})


_ADMIN: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList((("platform_admin", 1),))
_USER: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList((("custom", 2),))


class _FakeUow:
    """工作单元替身（回滚与事务边界均为空操作）。"""

    async def rollback(self) -> None:
        """空回滚。"""
        return None

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """空事务边界。

        Yields:
            None: 上下文。
        """
        yield None


class _FakeSession:
    """会话替身（`flush` 不落库，但补齐主键以便契约组装）。"""

    async def flush(self) -> None:
        """空刷写（主键已在 `add` 时补齐）。"""
        return None

    def add(self, row: object) -> None:
        """记录新增并补齐主键。

        Args:
            row: ORM 行。
        """
        if getattr(row, "id", None) is None:
            row.id = 1  # type: ignore[attr-defined]


class _FakeCache:
    """缓存替身（内存字典 + 版本号）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.data: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    def build_key(self, business_key: str, *, tenant: str | None = None) -> str:
        """拼 key。

        Args:
            business_key: 业务键。
            tenant: 租户。

        Returns:
            str: 缓存键。
        """
        return f"{tenant}:{business_key}"

    async def aget(self, key: str) -> object | None:
        """读缓存。

        Args:
            key: 缓存键。

        Returns:
            object | None: 值。
        """
        return self.data.get(key)

    async def aset(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存。

        Args:
            key: 缓存键。
            value: 值。
            ttl: 有效期。
        """
        del ttl
        self.data.set(key, value)

    async def adelete(self, key: str) -> bool:
        """删缓存。

        Args:
            key: 缓存键。

        Returns:
            bool: 是否命中。
        """
        return key in self.data

    async def aincrease(self, key: str) -> int:
        """版本自增。

        Args:
            key: 缓存键。

        Returns:
            int: 新值。
        """
        current = self.data.get(key)
        value = (current if isinstance(current, int) else 0) + 1
        self.data.set(key, value)
        return value


class _FakePrefs:
    """偏好存储替身。"""

    def __init__(self, value: object = None) -> None:
        """初始化。

        Args:
            value: `get` 返回值。
        """
        self.value = value
        self.sets: ConcurrentStableList[object] = ConcurrentStableList()
        self.resets = 0

    async def get(self, key: str, *, default: object = None) -> object | None:
        """读偏好。

        Args:
            key: 键。
            default: 默认值。

        Returns:
            object | None: 值。
        """
        del key
        return self.value if self.value is not None else default

    async def set(self, key: str, value: object) -> None:
        """写偏好。

        Args:
            key: 键。
            value: 值。
        """
        del key
        self.sets.add(value)

    async def reset(self, key: str) -> bool:
        """重置偏好。

        Args:
            key: 键。

        Returns:
            bool: 恒 True。
        """
        del key
        self.resets += 1
        return True


class _FakeTemplate:
    """模板行替身。"""

    def __init__(self, *, scope: str = SCOPE_PLATFORM, role_id: int = 0, status: str = "enabled") -> None:
        """初始化。

        Args:
            scope: 层级。
            role_id: 角色主键。
            status: 状态。
        """
        self.id = 11
        self.scope = scope
        self.role_id = role_id
        self.status = status
        self.name = "模板"
        self.layout_config = '{"cards": []}'
        self.deleted = False

    def soft_delete(self) -> None:
        """标记软删除。"""
        self.deleted = True


class _FakeTemplates:
    """模板仓储替身。"""

    def __init__(self, *, platform: _FakeTemplate | None = None, role: _FakeTemplate | None = None) -> None:
        """初始化。

        Args:
            platform: 平台模板行。
            role: 角色模板行。
        """
        self.platform = platform
        self.role = role

    async def get(self, _template_id: int) -> _FakeTemplate | None:
        """按主键取模板。

        Args:
            _template_id: 主键。

        Returns:
            _FakeTemplate | None: 模板行。
        """
        return self.platform or self.role

    async def get_platform(self) -> _FakeTemplate | None:
        """取平台模板。

        Returns:
            _FakeTemplate | None: 模板行。
        """
        return self.platform

    async def find_by_role(self, _role_id: int) -> _FakeTemplate | None:
        """按角色取模板。

        Args:
            _role_id: 角色主键。

        Returns:
            _FakeTemplate | None: 模板行。
        """
        return self.role

    async def list_role_templates(self, *, enabled_only: bool = True) -> ConcurrentStableList[_FakeTemplate]:
        """取角色模板。

        Args:
            enabled_only: 仅启用。

        Returns:
            ConcurrentStableList[_FakeTemplate]: 模板清单。
        """
        del enabled_only
        items: ConcurrentStableList[_FakeTemplate] = ConcurrentStableList()
        if self.role is not None:
            items.add(self.role)
        return items

    async def list_templates(self, *, scope: str | None = None) -> ConcurrentStableList[_FakeTemplate]:
        """取模板清单。

        Args:
            scope: 层级。

        Returns:
            ConcurrentStableList[_FakeTemplate]: 模板清单。
        """
        del scope
        items: ConcurrentStableList[_FakeTemplate] = ConcurrentStableList()
        if self.platform is not None:
            items.add(self.platform)
        if self.role is not None:
            items.add(self.role)
        return items


class _FakeCards:
    """卡片仓储替身。"""

    def __init__(self, rows: ConcurrentStableList[Any] | None = None) -> None:
        """初始化。

        Args:
            rows: 卡片行。
        """
        self.rows = rows or ConcurrentStableList()
        self.created: ConcurrentStableList[Any] = ConcurrentStableList()
        self.updated: ConcurrentStableList[Any] = ConcurrentStableList()
        self.deleted: ConcurrentStableList[Any] = ConcurrentStableList()

    async def list_cards(
        self, *, card_type: str | None = None, enabled_only: bool = False
    ) -> ConcurrentStableList[Any]:
        """取卡片。

        Args:
            card_type: 类型筛选。
            enabled_only: 仅启用。

        Returns:
            ConcurrentStableList[Any]: 卡片行。
        """
        del card_type, enabled_only
        return self.rows

    async def get_by_code(self, code: str) -> Any | None:
        """按码取卡片。

        Args:
            code: 标识。

        Returns:
            Any | None: 卡片行。
        """
        for row in self.rows:
            if row.code == code:
                return row
        return None


class _FakeI18n:
    """多语言仓储替身。"""

    async def load_names(
        self, card_ids: ConcurrentStableList[int], *, locales: ConcurrentStableList[str]
    ) -> ConcurrentStableDict[int, str]:
        """装载名称。

        Args:
            card_ids: 主键。
            locales: 语言序。

        Returns:
            ConcurrentStableDict[int, str]: 名称映射。
        """
        del card_ids, locales
        return ConcurrentStableDict()

    async def load_all_names(
        self, card_ids: ConcurrentStableList[int], *, locales: ConcurrentStableList[str]
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """装载全部名称。

        Args:
            card_ids: 主键。
            locales: 语言序。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 名称映射。
        """
        del card_ids, locales
        return ConcurrentStableDict()

    async def replace_names(self, card_id: int, names: ConcurrentStableDict[str, str]) -> None:
        """替换名称。

        Args:
            card_id: 主键。
            names: 名称。
        """
        del card_id, names
        return None

    async def soft_delete_names(self, card_id: int) -> None:
        """软删名称。

        Args:
            card_id: 主键。
        """
        del card_id
        return None


class _FakeRoles:
    """角色读面替身。"""

    def __init__(self, *, status: str = "enabled") -> None:
        """初始化。

        Args:
            status: 摘要状态。
        """
        self.status = status

    async def roles_of_user(self, user_id: int) -> ConcurrentStableList[tuple[str, int]]:
        """取用户角色。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色集。
        """
        del user_id
        return ConcurrentStableList()

    async def roles_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[Any]:
        """按主键取角色（替身恒返回启用摘要）。

        Args:
            role_ids: 主键。

        Returns:
            ConcurrentStableList[Any]: 角色摘要。
        """
        items: ConcurrentStableList[Any] = ConcurrentStableList()
        for role_id in role_ids:
            items.add(_RoleSummaryStub(id=role_id, status=self.status))
        return items


class _FakeDatasets:
    """数据集探测替身（固定返回给定结论）。"""

    def __init__(self, available: bool | None) -> None:
        """初始化。

        Args:
            available: 探测结论。
        """
        self.available = available

    async def is_available(self, dataset_id: str) -> bool | None:
        """返回固定结论。

        Args:
            dataset_id: 数据集标识。

        Returns:
            bool | None: 结论。
        """
        del dataset_id
        return self.available


def _service(
    *,
    cards: _FakeCards | None = None,
    templates: _FakeTemplates | None = None,
    prefs: _FakePrefs | None = None,
    cache: _FakeCache | None = None,
    roles: _FakeRoles | None = None,
    datasets: _FakeDatasets | None = None,
) -> DashboardService:
    """构造带替身的服务。

    Args:
        cards: 卡片仓储。
        templates: 模板仓储。
        prefs: 偏好存储。
        cache: 缓存。
        roles: 角色读面。
        datasets: 数据集探测。

    Returns:
        DashboardService: 服务实例。
    """
    session = cast("Any", _FakeSession())
    return DashboardService(
        session=session,
        uow=cast("Any", _FakeUow()),
        cards=cast("Any", cards or _FakeCards()),
        card_i18n=cast("Any", _FakeI18n()),
        templates=cast("Any", templates or _FakeTemplates()),
        preferences=cast("Any", prefs or _FakePrefs()),
        roles=cast("Any", roles or _FakeRoles()),
        todo=NullTodoCountProvider(),
        notifications=cast("Any", _Badge()),
        datasets=cast("Any", datasets or NullDatasetProbe()),
        cache=cast("Any", cache or _FakeCache()),
        tenant="demo",
    )


class _Badge:
    """未读角标替身。"""

    async def unread_count(self, user_id: int) -> BadgeCountView:
        """取未读。

        Args:
            user_id: 用户主键。

        Returns:
            BadgeCountView: 角标。
        """
        del user_id
        return BadgeCountView(count=3, available=True)


def _card_row(code: str, *, status: str = "enabled", width: int = 4, height: int = 2) -> Any:
    """构造卡片行替身。

    Args:
        code: 标识。
        status: 状态。
        width: 宽。
        height: 高。

    Returns:
        Any: 卡片行。
    """
    return _CardStub(
        id=1,
        code=code,
        name=code,
        card_type="builtin",
        render_key=code,
        dataset_id=None,
        chart_type=None,
        chart_config=None,
        data_endpoint="",
        default_width=width,
        default_height=height,
        mobile_supported=True,
        sort=10,
        status=status,
    )


async def test_empty_fallback_when_everything_missing() -> None:
    """三级皆空 → 内置最小布局（`source=empty`、`fallback=true`）。"""
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))))
    data = await service.resolve_layout(user_id=1, role_types=ConcurrentStableList(), locale="zh-CN")
    assert data.source == "empty"
    assert data.fallback is True
    assert [item.code for item in data.layout.cards] == ["todo"]
    assert data.available_cards and data.available_cards[0].code == "todo"


async def test_catalog_cache_hit_returns_cached_items() -> None:
    """可选卡片清单命中缓存时直接复用（不再读库）。"""
    cache = _FakeCache()
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))), cache=cache)
    first = await service.resolve_layout(user_id=1, role_types=ConcurrentStableList(), locale="zh-CN")
    cache.data.set("demo:layout:v0:1", {"layout": {"cards": []}, "source": "empty", "role_id": 0,
                                        "template_id": 0, "fallback": True, "warnings": []})
    second = await service.resolve_layout(user_id=1, role_types=ConcurrentStableList(), locale="zh-CN")
    assert [item.code for item in first.available_cards] == [item.code for item in second.available_cards]
    assert second.source == "empty"


async def test_version_bump_and_structure_cache() -> None:
    """版本号自增使旧缓存失效（key 含版本）。"""
    cache = _FakeCache()
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))), cache=cache)
    assert await service.version() == 0
    await service._bump_version()  # pyright: ignore[reportPrivateUsage]
    assert await service.version() == 1


async def test_create_platform_template_requires_admin_and_singleton() -> None:
    """平台模板：非超管 `30001`；已存在 `40306`。"""
    templates = _FakeTemplates(platform=_FakeTemplate())
    service = _service(templates=templates)
    payload = DashboardTemplateCreate(scope="platform", name="x", layout_config=_empty_layout())
    with pytest.raises(BizPermissionError):
        await service.create_template(payload=payload, role_types=_USER)
    with pytest.raises(DashboardPlatformTemplateExistsError):
        await service.create_template(payload=payload, role_types=_ADMIN)


async def test_create_role_template_conflict() -> None:
    """角色模板已存在 → `40307`。"""
    templates = _FakeTemplates(role=_FakeTemplate(scope="role", role_id=5))
    service = _service(templates=templates)
    payload = DashboardTemplateCreate(scope="role", role_id=5, name="x", layout_config=_empty_layout())
    with pytest.raises(DashboardRoleTemplateExistsError):
        await service.create_template(payload=payload, role_types=_USER)


async def test_update_platform_template_branches() -> None:
    """平台模板编辑：非超管 `30001`；超管改名称 / 状态成功。"""
    platform = _FakeTemplate()
    service = _service(templates=_FakeTemplates(platform=platform))
    payload = DashboardTemplateUpdate(name="新名", status="disabled")
    with pytest.raises(BizPermissionError):
        await service.update_template(template_id=11, payload=payload, role_types=_USER)
    row = await service.update_template(template_id=11, payload=payload, role_types=_ADMIN)
    assert row.name == "新名"
    assert row.status == "disabled"


async def test_delete_platform_template_branches() -> None:
    """平台模板删除：非超管 `30001`；超管软删成功。"""
    platform = _FakeTemplate()
    service = _service(templates=_FakeTemplates(platform=platform))
    with pytest.raises(BizPermissionError):
        await service.delete_template(template_id=11, role_types=_USER)
    assert await service.delete_template(template_id=11, role_types=_ADMIN) is True
    assert platform.deleted is True


async def test_chart_config_invalid_json_is_ignored() -> None:
    """图表配置非法 JSON / 非对象 → 按未配置处理（不抛错）。"""
    service = _service()
    row = _card_row("dataset_card")
    row.chart_config = "{not json"
    assert service._chart_config_of(row) is None  # pyright: ignore[reportPrivateUsage]
    row.chart_config = '["x"]'
    assert service._chart_config_of(row) is None  # pyright: ignore[reportPrivateUsage]
    row.chart_config = '{"legend": {"show": false}}'
    assert service._chart_config_of(row) is not None  # pyright: ignore[reportPrivateUsage]


async def test_resolve_uses_preference_when_present() -> None:
    """个人布局存在时命中个人层级。"""
    prefs = _FakePrefs(
        ConcurrentStableDict(
            {"cards": ConcurrentStableList((ConcurrentStableDict({"code": "todo", "x": 0, "y": 0, "w": 4, "h": 2}),))}
        )
    )
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))), prefs=prefs)
    data = await service.resolve_layout(user_id=1, role_types=ConcurrentStableList(), locale="zh-CN")
    assert data.source == "personal"
    assert data.layout.cards[0].code == "todo"


async def test_badges_uses_ports() -> None:
    """角标聚合：待办占位不可用 + 未读端口计数。"""
    service = _service()
    data = await service.badges(user_id=1)
    assert data.todo.available is False
    assert data.notification.count == 3


def test_role_template_create_payload_defaults() -> None:
    """角色模板请求默认状态为启用（契约默认值稳定）。"""
    payload = DashboardTemplateCreate(scope="role", role_id=3, name="x", layout_config=_empty_layout())
    assert payload.status == "enabled"


def test_card_size_defaults() -> None:
    """卡片尺寸值对象缺省值（归一输入口径）。"""
    size = CardSize(code="todo")
    assert (size.width, size.height) == (4, 2)
    assert isinstance(ConcurrentStableFrozenDict({}), ConcurrentStableFrozenDict)


async def test_create_card_rejects_unavailable_dataset() -> None:
    """数据集探测为不可用 → `40303`。"""
    from bms_core.core.exceptions import DashboardDatasetUnavailableError
    from bms_platform.domains.dashboard.schemas.card import DashboardCardCreate

    service = _service(datasets=_FakeDatasets(False))
    payload = DashboardCardCreate(code="ds_card", name="x", dataset_id="ds-1", chart_type="bar")
    with pytest.raises(DashboardDatasetUnavailableError):
        await service.create_card(payload=payload, locale="zh-CN")


async def test_create_card_derives_name_with_fallback() -> None:
    """多语言只有空白值时按请求语言兜底；`_derive_name` 无命中回落兜底值。"""
    from bms_platform.domains.dashboard.schemas.card import DashboardCardCreate

    service = _service(datasets=_FakeDatasets(None))
    payload = DashboardCardCreate(
        code="name_card", name="兜底名", dataset_id="ds-1", chart_type="bar", i18n=ConcurrentStableDict({"en-US": "  "})
    )
    row = await service.create_card(payload=payload, locale="zh-CN")
    assert row.name == "兜底名"

    names: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    assert service._derive_name(names, "兜底", "zh-CN") == "兜底"  # pyright: ignore[reportPrivateUsage]


async def test_create_platform_template_when_absent() -> None:
    """平台模板不存在且当前用户为超管 → 创建成功（`role_id` 固定 0）。"""
    service = _service(templates=_FakeTemplates(platform=None))
    payload = DashboardTemplateCreate(scope="platform", name="平台布局", layout_config=_empty_layout())
    row = await service.create_template(payload=payload, role_types=_ADMIN)
    assert row.scope == "platform"
    assert int(row.role_id) == 0


async def test_role_template_requires_valid_role() -> None:
    """角色模板：`role_id<=0` 或角色停用 → `40305`。"""
    from bms_core.core.exceptions import DashboardRoleNotFoundError
    from bms_platform.domains.dashboard.schemas.template import DashboardTemplateCreate

    service = _service()
    invalid = DashboardTemplateCreate(scope="role", role_id=0, name="x", layout_config=_empty_layout())
    with pytest.raises(DashboardRoleNotFoundError):
        await service.create_template(payload=invalid, role_types=_USER)

    disabled = _service(roles=_FakeRoles(status="disabled"))
    payload = DashboardTemplateCreate(scope="role", role_id=5, name="x", layout_config=_empty_layout())
    with pytest.raises(DashboardRoleNotFoundError):
        await disabled.create_template(payload=payload, role_types=_USER)


async def test_catalog_skips_non_dict_cache_entries() -> None:
    """缓存载荷含非对象项时跳过（防脏缓存导致解析崩溃）。"""
    cache = _FakeCache()
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))), cache=cache)
    cache.data.set("demo:cards:v0:zh-CN", ["bad", {"code": "todo", "name": "待办", "card_type": "builtin",
                                                   "render_key": "todo", "default_width": 4, "default_height": 2,
                                                   "mobile_supported": True, "sort": 10}])
    data = await service.resolve_layout(user_id=1, role_types=ConcurrentStableList(), locale="zh-CN")
    assert [item.code for item in data.available_cards] == ["todo"]


async def test_create_card_with_available_dataset() -> None:
    """数据集探测为可用 → 正常创建（不告警、不拒绝）。"""
    from bms_platform.domains.dashboard.schemas.card import DashboardCardCreate

    service = _service(datasets=_FakeDatasets(True))
    payload = DashboardCardCreate(code="ok_card", name="x", dataset_id="ds-1", chart_type="bar")
    row = await service.create_card(payload=payload, locale="zh-CN")
    assert row.code == "ok_card"


async def test_derive_name_uses_any_language_when_locale_missing() -> None:
    """请求语言与系统默认语言均无文案时取首个有值语言。"""
    service = _service()
    names: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    names.set("fr-FR", "Bonjour")
    assert service._derive_name(names, "兜底", "zh-CN") == "Bonjour"  # pyright: ignore[reportPrivateUsage]

    blank: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    blank.set("fr-FR", "")
    assert service._derive_name(blank, "兜底", "zh-CN") == "兜底"  # pyright: ignore[reportPrivateUsage]


async def test_role_level_returns_none_when_no_template_matches() -> None:
    """用户有角色但无角色模板 → 角色层级返回 None（继续平台 / 空回退）。"""
    service = _service(cards=_FakeCards(ConcurrentStableList((_card_row("todo"),))), templates=_FakeTemplates())
    data = await service.resolve_layout(
        user_id=1, role_types=ConcurrentStableList((("custom", 7),)), locale="zh-CN"
    )
    assert data.source == "empty"
