"""菜单元数据服务写路径与快照用例（补齐 `services/menu.py` 覆盖面，Kiwi 2242）。

端点用例（`tests/api/test_menu_metadata.py`）已覆盖维护链主路径；本文件补齐其未触及的分支：

- **纯函数**：多语言归一（空白剔除）、默认文案派生优先级与全空失败、出参回填、请求语言回退、入口去重；
- **快照构建**：业务 / 动作 / 权限 / 表单 / 按钮 / 字段的**停用与断裂挂接**跳过（挂接链校验零容忍）；
- **菜单**：父子嵌套树、父菜单校验、路径冲突、子节点引用禁删、缺行与「行消失」竞态；
- **表单 / 按钮 / 字段**：更新全量替换与业务 1:1 冲突、各类缺行校验、表单缺失时的发件箱降级与「行消失」竞态。

运行口径（2026-11-27 重写）：平台库全 worker 共用、跨轮次叠加，故本文件**不设固定业务键**——
业务码 / 动作码 / 菜单路径一律按用例命名空间（`ns`）派生，用例结束既不清理自己的行（叠加口径），
更不触碰他人数据；断言只认本用例造出来的键。上一版按固定码造数再定点清场，跨 worker 互删与
种子行误删都由此而来。真库两阶段事务与三库方言由 CI 作业承担，本文件以共享 SQLite 承载服务层编排。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConflictError,
    MenuCodeConflictError,
    MenuI18nRequiredError,
    MenuNotFoundError,
    MenuPathConflictError,
    MenuPermissionExistsError,
    MenuReferencedError,
)
from bms_core.db.gate import LazyGatedSession, db_access_gate
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.models.base import BaseModel
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu, SysMenuForm
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.testing.gates import PLATFORM_GATE
from bms_core.testing.namespace import Namespace
from bms_platform.domains.menu_form.repositories.menu import (
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
)
from bms_platform.domains.menu_form.schemas.menu import MenuCreateRequest, MenuUpdateRequest
from bms_platform.domains.menu_form.services.menu import (
    MenuFormService,
    _snapshot_form,  # pyright: ignore[reportPrivateUsage]
    clean_i18n,
    derive_default_name,
    i18n_out,
    request_locale,
    require_i18n_name,
)
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository,
    BusinessRepository,
    PermissionRepository,
)
from bms_platform.domains.permission_meta.schemas.permission_meta import (
    ActionCreateRequest,
    ActionUpdateRequest,
    BusinessCreateRequest,
    BusinessUpdateRequest,
    PermissionCreateRequest,
    PermissionGenerateRequest,
)
from bms_platform.domains.permission_meta.services.permission_meta import PermissionMetadataService
from tests_support.shared_access import shared_engine, shared_platform_url

pytestmark = pytest.mark.kiwi_id(2242)

_MISSING_ID = 987654321
"""缺行用例的哨兵主键（只用于「查不到」的断言，不落任何业务键）。"""


class _OutboxSpy:
    """发件箱替身：记录事件信封（不落库）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.events: ConcurrentStableList[object] = ConcurrentStableList()

    async def enqueue(self, session: object, envelope: object) -> None:
        """记录一次事件入队。

        Args:
            session: 会话（未使用）。
            envelope: 事件信封。
        """
        self.events.add(envelope)


class _VanishMenus(MenuRepository):
    """菜单仓储替身：`update` 恒无行（构造取行后行消失的竞态）。"""

    async def update(self, item_id: int, **values: object) -> SysMenu | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysMenu | None: 恒 None。
        """
        return None


class _VanishForms(FormRepository):
    """表单仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysForm | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysForm | None: 恒 None。
        """
        return None


class _VanishButtons(ButtonRepository):
    """按钮仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysButton | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysButton | None: 恒 None。
        """
        return None


class _VanishFields(FieldRepository):
    """字段仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysField | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysField | None: 恒 None。
        """
        return None


class _MissingForms(FormRepository):
    """表单仓储替身：`get` 恒无行（构造表单缺失时的发件箱降级分支）。"""

    async def get(self, item_id: int) -> SysForm | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。

        Returns:
            SysForm | None: 恒 None。
        """
        return None


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """共享平台库写会话（门代理；表由数据初始化建好，用例不建表）。

    Yields:
        AsyncSession: 共享平台库门代理会话。
    """
    engine = shared_engine(shared_platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    proxy = LazyGatedSession(lambda: db_access_gate(PLATFORM_GATE, read_only=False), factory(), bind=engine)
    try:
        yield cast("AsyncSession", proxy)
    finally:
        await proxy.close()


def _names(text: str) -> ConcurrentStableDict[str, str]:
    """构造单语言（`zh-CN`）文案映射。

    Args:
        text: 文案。

    Returns:
        ConcurrentStableDict[str, str]: 文案映射。
    """
    return ConcurrentStableDict({"zh-CN": text})


def _service(
    session: AsyncSession,
    *,
    outbox: Any,
    cache: CacheRegion,
    menus: MenuRepository | None = None,
    forms: FormRepository | None = None,
    buttons: ButtonRepository | None = None,
    fields: FieldRepository | None = None,
) -> MenuFormService:
    """构造元数据服务（真实仓储 + 可替换的单仓储替身）。

    Args:
        session: 会话。
        outbox: 发件箱存储（替身）。
        cache: 缓存 Region。
        menus: 菜单仓储覆写（缺省真实仓储）。
        forms: 表单仓储覆写。
        buttons: 按钮仓储覆写。
        fields: 字段仓储覆写。

    Returns:
        MenuFormService: 元数据服务。
    """
    db = cast("DbSession", session)
    return MenuFormService(
        uow=DbUnitOfWork(db),
        businesses=BusinessRepository(db),
        actions=ActionRepository(db),
        permissions=PermissionRepository(db),
        menus=menus if menus is not None else MenuRepository(db),
        forms=forms if forms is not None else FormRepository(db),
        menu_forms=MenuFormRepository(db),
        buttons=buttons if buttons is not None else ButtonRepository(db),
        fields=fields if fields is not None else FieldRepository(db),
        outbox=outbox,
        cache=cache,
    )


def _permission_service(session: AsyncSession, *, cache: CacheRegion) -> PermissionMetadataService:
    """构造权限元数据服务（真实仓储 + 菜单表单只读探测）。

    Args:
        session: 会话。
        cache: 缓存 Region。

    Returns:
        PermissionMetadataService: 权限元数据服务。
    """
    db = cast("DbSession", session)
    return PermissionMetadataService(
        uow=DbUnitOfWork(db),
        businesses=BusinessRepository(db),
        actions=ActionRepository(db),
        permissions=PermissionRepository(db),
        buttons=ButtonRepository(db),
        forms=FormRepository(db),
        cache=cache,
    )


async def _seed[ModelT: BaseModel](session: AsyncSession, row: ModelT) -> ModelT:
    """插入并提交一条记录。

    Args:
        session: 会话。
        row: 待插入的 ORM 行。

    Returns:
        ModelT: 持久化后的同一行（主键已生成）。
    """
    session.add(row)
    await session.commit()
    return row


def _code(ns: Namespace, suffix: str) -> str:
    """本用例命名空间下的业务码 / 动作码。

    编码格式约束是 `^[a-z][a-z0-9_]*$`（不允许 `-`），故用 `{prefix}_{suffix}` 而非 `ns.code()`。

    Args:
        ns: 命名空间。
        suffix: 后缀（小写字母 / 数字 / 下划线）。

    Returns:
        str: `{prefix}_{suffix}`。
    """
    return f"{ns.prefix}_{suffix}"


def _path(ns: Namespace, leaf: str) -> str:
    """本用例命名空间下的菜单路径。

    Args:
        ns: 命名空间。
        leaf: 叶子段（如 `p` / `p/c`）。

    Returns:
        str: `/{prefix}/{leaf}`。
    """
    return f"/{ns.prefix}/{leaf}"


def test_clean_i18n_drops_blank_values() -> None:
    """多语言归一：剔除纯空白文案，保留有值语言（不改动语言集合）。"""
    cleaned = clean_i18n(ConcurrentStableDict({"zh-CN": "  菜单  ", "en-US": "   "}))
    assert cleaned.get("zh-CN") == "菜单"
    assert "en-US" not in cleaned


def test_derive_default_name_priority_and_empty_failure() -> None:
    """默认文案派生：系统默认语言 → 必填语言 → 首个有值语言；全空即拒（40208）。"""
    assert (
        derive_default_name(ConcurrentStableDict({"zh-CN": "中文", "en-US": "EN"}), required_locale="en-US") == "中文"
    )
    assert derive_default_name(ConcurrentStableDict({"fr-FR": "", "de-DE": "德语"}), required_locale="zh-CN") == "德语"
    with pytest.raises(MenuI18nRequiredError):
        derive_default_name(ConcurrentStableDict(), required_locale="zh-CN")


def test_require_i18n_name_rejects_missing_required_locale() -> None:
    """必填语言校验：有值放行，缺必填语言文案拒绝（40208）。"""
    require_i18n_name(ConcurrentStableDict({"zh-CN": "中文"}), locale="zh-CN")
    with pytest.raises(MenuI18nRequiredError):
        require_i18n_name(ConcurrentStableDict({"zh-CN": "中文"}), locale="en-US")


def test_i18n_out_handles_none_and_fills_required_locale() -> None:
    """出参多语言映射：可空入参 → 仅必填语言回填主表默认文案。"""
    assert i18n_out(None, name="缺省文案", locale="en-US").get("en-US") == "缺省文案"
    filled = i18n_out(ConcurrentStableDict({"zh-CN": "中文"}), name="默认文案", locale="en-US")
    assert filled.get("zh-CN") == "中文"
    assert filled.get("en-US") == "默认文案"


def test_request_locale_falls_back_when_unsupported() -> None:
    """请求语言：未设置时回退系统默认语言；已设置时原样采用（清单解析在 `locale_scope`，05_02）。"""
    assert request_locale() == DEFAULT_LOCALE
    token = current_dict_locale.set("fr-FR")
    try:
        assert request_locale() == "fr-FR"
    finally:
        current_dict_locale.reset(token)


def test_dedupe_removes_repeated_ids() -> None:
    """入口去重：保持首次出现序。"""
    assert list(MenuFormService._dedupe(ConcurrentStableList([1, 2, 1, 2, 3]))) == [1, 2, 3]  # pyright: ignore[reportPrivateUsage]


def test_snapshot_form_skips_buttons_with_broken_links() -> None:
    """快照表单：按钮权限码缺失 / 动作码缺失时跳过（挂接链断裂不产出按钮）。

    纯值对象场景（不落库），故用内联编号即可，不涉及共享库键。
    """
    form = SysForm(id=1, business_id=1, component=None, status="enabled")
    business = SysBusiness(id=1, code="biz", name="业务", status="enabled")
    permission = SysPermission(id=2, business_id=1, action_id=2, status="enabled")
    orphan = SysButton(id=1, form_id=1, permission_id=9, name="孤儿", type="toolbar", sort=1, status="enabled")
    no_action = SysButton(id=2, form_id=1, permission_id=2, name="缺动作", type="toolbar", sort=2, status="enabled")

    result = _snapshot_form(  # pyright: ignore[reportPrivateUsage]
        form,
        business,
        action_by_id=ConcurrentStableDict(),
        permission_by_id=ConcurrentStableDict({2: permission}),
        business_by_id=ConcurrentStableDict({1: business}),
        buttons_by_form=ConcurrentStableDict({1: ConcurrentStableList([orphan, no_action])}),
        fields_by_form=ConcurrentStableDict(),
        field_i18n=ConcurrentStableDict(),
    )
    assert list(result.buttons) == []


async def test_load_snapshot_skips_disabled_and_broken_rows(session: AsyncSession, ns: Namespace) -> None:
    """快照构建：停用业务 / 权限 / 表单 / 按钮 / 字段与断裂挂接一律跳过；多入口 / 多按钮 / 多字段归集。"""
    biz_first = _code(ns, "biz_first")
    biz_disabled = _code(ns, "biz_disabled")
    biz_third = _code(ns, "biz_third")
    act_first = _code(ns, "act_first")
    act_second = _code(ns, "act_second")
    act_third = _code(ns, "act_third")

    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    first_business = await _seed(session, SysBusiness(code=biz_first, name="业务一", status="enabled"))
    first_business_id = first_business.id
    disabled_business = await _seed(session, SysBusiness(code=biz_disabled, name="业务二", status="disabled"))
    third_business = await _seed(session, SysBusiness(code=biz_third, name="业务三", status="enabled"))
    first_action = await _seed(session, SysAction(code=act_first, name="动作一", status="enabled"))
    first_action_id = first_action.id
    second_action = await _seed(session, SysAction(code=act_second, name="动作二", status="enabled"))
    second_action_id = second_action.id
    third_action = await _seed(session, SysAction(code=act_third, name="动作三", status="enabled"))
    third_action_id = third_action.id
    first_permission = await _seed(
        session, SysPermission(business_id=first_business_id, action_id=first_action_id, status="enabled")
    )
    first_permission_id = first_permission.id
    second_permission = await _seed(
        session, SysPermission(business_id=first_business_id, action_id=second_action_id, status="enabled")
    )
    second_permission_id = second_permission.id
    third_permission = await _seed(
        session, SysPermission(business_id=first_business_id, action_id=third_action_id, status="enabled")
    )
    third_permission_id = third_permission.id
    await _seed(session, SysPermission(business_id=third_business.id, action_id=first_action_id, status="disabled"))
    await _seed(session, SysPermission(business_id=_MISSING_ID, action_id=first_action_id, status="enabled"))
    await _seed(session, SysPermission(business_id=first_business_id, action_id=_MISSING_ID, status="enabled"))
    menu = await _seed(session, SysMenu(parent_id=0, name="菜单", path=_path(ns, "snap"), status="enabled"))
    menu_id = menu.id
    first_form = await _seed(session, SysForm(business_id=first_business_id, component=None, status="enabled"))
    first_form_id = first_form.id
    second_form = await _seed(session, SysForm(business_id=third_business.id, component=None, status="enabled"))
    disabled_form = await _seed(session, SysForm(business_id=disabled_business.id, component=None, status="disabled"))
    await _seed(session, SysMenuForm(menu_id=menu_id, form_id=first_form_id))
    await _seed(session, SysMenuForm(menu_id=menu_id, form_id=second_form.id))
    await _seed(session, SysMenuForm(menu_id=menu_id, form_id=disabled_form.id))
    await _seed(
        session,
        SysButton(
            form_id=first_form_id,
            permission_id=first_permission_id,
            name="停用按钮",
            type="toolbar",
            sort=1,
            status="disabled",
        ),
    )
    await _seed(
        session,
        SysButton(
            form_id=first_form_id,
            permission_id=second_permission_id,
            name="按钮一",
            type="toolbar",
            sort=2,
            status="enabled",
        ),
    )
    await _seed(
        session,
        SysButton(
            form_id=first_form_id,
            permission_id=third_permission_id,
            name="按钮二",
            type="toolbar",
            sort=3,
            status="enabled",
        ),
    )
    await _seed(
        session,
        SysField(form_id=first_form_id, field_key="kd", name="停用字段", type="input", sort=1, status="disabled"),
    )
    await _seed(
        session, SysField(form_id=first_form_id, field_key="ka", name="字段一", type="input", sort=2, status="enabled")
    )
    await _seed(
        session, SysField(form_id=first_form_id, field_key="kb", name="字段二", type="input", sort=3, status="enabled")
    )

    snapshot = await service.load_snapshot(locale=DEFAULT_LOCALE, tenant_id=None, ttl=300)

    assert snapshot.version == 0
    assert {
        f"{biz_first}:{act_first}",
        f"{biz_first}:{act_second}",
        f"{biz_first}:{act_third}",
    } <= set(snapshot.permission_codes)
    assert not any(code.startswith(f"{biz_disabled}:") for code in snapshot.permission_codes)
    mine = next(menu for menu in snapshot.menus if menu.path == _path(ns, "snap"))
    forms = list(mine.forms)
    assert len(forms) == 2
    assert forms[0].business_code == biz_first
    assert [button.name for button in forms[0].buttons] == ["按钮一", "按钮二"]
    assert [field.field_key for field in forms[0].fields] == ["ka", "kb"]

    permissions = await _permission_service(session, cache=MemoryCacheRegion()).list_permissions(None)
    codes = [item.code for item in permissions.items]
    assert {
        f"{biz_first}:{act_first}",
        f"{biz_first}:{act_second}",
        f"{biz_first}:{act_third}",
        f"{biz_third}:{act_first}",
    } <= set(codes)
    assert not any(code.startswith(f"{biz_disabled}:") for code in codes)


async def test_business_action_permission_write_paths(session: AsyncSession, ns: Namespace) -> None:
    """业务码 / 动作码 / 权限码写路径：创建冲突、停用联动、恢复、删除引用保护、批量补生成。

    覆盖 `services/menu.py` 三类写接口的分支：码重复 40209、停用连带停用权限码、软删除后同键恢复、
    被引用时禁删、权限码组合重复 40210、批量补生成含停用项。
    """
    business_code = _code(ns, "biz_write")
    action_code = _code(ns, "act_write")

    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    permission = _permission_service(session, cache=MemoryCacheRegion())

    # 业务码：创建 / 重复 40209 / 更新停用 / 软删除后同键恢复
    business = await permission.create_business(BusinessCreateRequest(code=business_code, i18n=_names("业务甲")))
    business_id = business.id
    with pytest.raises(MenuCodeConflictError):
        await permission.create_business(BusinessCreateRequest(code=business_code, i18n=_names("重复")))
    await session.rollback()

    # 动作码：创建 / 重复
    action = await permission.create_action(ActionCreateRequest(code=action_code, i18n=_names("动作甲")))
    action_id = action.id
    with pytest.raises(MenuCodeConflictError):
        await permission.create_action(ActionCreateRequest(code=action_code, i18n=_names("重复")))
    await session.rollback()

    # 权限码：手工新增 / 组合重复 40210
    permission_row = await permission.create_permission(
        PermissionCreateRequest(business_id=business_id, action_id=action_id)
    )
    permission_id = permission_row.id
    with pytest.raises(MenuPermissionExistsError):
        await permission.create_permission(PermissionCreateRequest(business_id=business_id, action_id=action_id))
    await session.rollback()

    # 停用动作码：连带停用其权限码（update_action 的联动分支）
    stopped = await permission.update_action(action_id, ActionUpdateRequest(status="disabled", i18n=_names("动作甲")))
    assert stopped.status == "disabled"
    await session.rollback()

    # 停用业务码：连带停用其权限码（update_business 的联动分支）
    stopped_business = await permission.update_business(
        business_id, BusinessUpdateRequest(status="disabled", i18n=_names("业务甲"))
    )
    assert stopped_business.status == "disabled"
    await session.rollback()

    # 被引用时禁删：权限码存在则业务码 / 动作码不可删
    with pytest.raises(MenuReferencedError):
        await permission.delete_business(business_id)
    await session.rollback()
    with pytest.raises(MenuReferencedError):
        await permission.delete_action(action_id)
    await session.rollback()

    # 删除权限码后业务码可删，再同键重建走软删除恢复分支
    await permission.delete_permission(permission_id)
    await session.rollback()
    await permission.delete_business(business_id)
    await session.rollback()
    restored_business = await permission.create_business(
        BusinessCreateRequest(code=business_code, i18n=_names("业务甲重建"))
    )
    assert restored_business.code == business_code
    await session.rollback()

    # 缺行分支：更新 / 删除不存在的业务码与动作码
    with pytest.raises(MenuNotFoundError):
        await permission.update_business(_MISSING_ID, BusinessUpdateRequest(i18n=_names("无")))
    await session.rollback()
    with pytest.raises(MenuNotFoundError):
        await permission.delete_business(_MISSING_ID)
    await session.rollback()
    with pytest.raises(MenuNotFoundError):
        await permission.update_action(_MISSING_ID, ActionUpdateRequest(i18n=_names("无")))
    await session.rollback()
    with pytest.raises(MenuNotFoundError):
        await permission.delete_action(_MISSING_ID)
    await session.rollback()

    # 表单挂接引用：业务码被表单挂接时禁删
    form = await service.create_form(
        business_id=business_id,
        component="comp",
        menu_ids=ConcurrentStableList(),
        status="enabled",
    )
    form_id = form.id
    with pytest.raises(MenuReferencedError):
        await permission.delete_business(business_id)
    await session.rollback()
    await service.delete_form(form_id)
    await session.rollback()

    # 动作码软删除后同键重建：走恢复分支
    await permission.delete_action(action_id)
    await session.rollback()
    restored_action = await permission.create_action(ActionCreateRequest(code=action_code, i18n=_names("动作甲重建")))
    assert restored_action.code == action_code
    await session.rollback()

    # 权限码缺行校验
    with pytest.raises(MenuNotFoundError):
        await permission.create_permission(PermissionCreateRequest(business_id=_MISSING_ID, action_id=action_id))
    await session.rollback()
    with pytest.raises(MenuNotFoundError):
        await permission.create_permission(PermissionCreateRequest(business_id=business_id, action_id=_MISSING_ID))
    await session.rollback()

    # 权限码软删除后同组合重建：走恢复分支
    deleted_permission = await permission.create_permission(
        PermissionCreateRequest(business_id=business_id, action_id=action_id)
    )
    deleted_permission_id = deleted_permission.id
    await permission.delete_permission(deleted_permission_id)
    await session.rollback()
    restored_permission = await permission.create_permission(
        PermissionCreateRequest(business_id=business_id, action_id=action_id)
    )
    assert restored_permission.id == deleted_permission_id
    await session.rollback()

    # 批量补生成：含停用项开关（generate_permissions 的两个分支）
    generated = await permission.generate_permissions(PermissionGenerateRequest())
    assert generated.created >= 0
    await session.rollback()
    generated_all = await permission.generate_permissions(PermissionGenerateRequest(include_disabled=True))
    assert generated_all.created >= 0
    await session.rollback()


async def test_menu_write_paths(session: AsyncSession, ns: Namespace) -> None:
    """菜单写路径：父子嵌套树、父校验、路径冲突、缺行、子节点引用禁删、行消失竞态。"""
    parent_path = _path(ns, "p")
    child_path = _path(ns, "p/c")
    ghost_path = _path(ns, "p/x")
    renamed_path = _path(ns, "p2")

    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    parent, _ = await service.create_menu(MenuCreateRequest(path=parent_path, i18n=_names("父")))
    parent_id = parent.id
    child, _ = await service.create_menu(MenuCreateRequest(parent_id=parent_id, path=child_path, i18n=_names("子")))
    child_id = child.id
    with pytest.raises(MenuNotFoundError):
        await service.create_menu(MenuCreateRequest(parent_id=_MISSING_ID, path=ghost_path, i18n=_names("无")))

    tree = await service.list_menu_tree()
    root = next(node for node in tree.items if node.id == parent_id)
    assert [node.id for node in root.children] == [child_id]
    await session.rollback()  # 读查询会 autobegin，写路径前先结束隐式事务

    with pytest.raises(MenuPathConflictError):
        await service.update_menu(child_id, MenuUpdateRequest(parent_id=0, path=parent_path, i18n=_names("子")))
    with pytest.raises(MenuNotFoundError):
        await service.update_menu(_MISSING_ID, MenuUpdateRequest(parent_id=0, path=renamed_path, i18n=_names("无")))

    vanishing = _service(
        session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), menus=_VanishMenus(cast("DbSession", session))
    )
    with pytest.raises(MenuNotFoundError):
        await vanishing.update_menu(parent_id, MenuUpdateRequest(parent_id=0, path=renamed_path, i18n=_names("父")))

    with pytest.raises(MenuReferencedError):
        await service.delete_menu(parent_id)
    await service.delete_menu(child_id)
    await service.delete_menu(parent_id)
    with pytest.raises(MenuNotFoundError):
        await service.delete_menu(parent_id)


async def test_form_write_paths(session: AsyncSession, ns: Namespace) -> None:
    """表单写路径：入口全量替换、业务 1:1 冲突、缺行校验、行消失竞态与删除。"""
    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    first_business = await _seed(session, SysBusiness(code=_code(ns, "fb1"), name="业务一", status="enabled"))
    first_business_id = first_business.id
    second_business = await _seed(session, SysBusiness(code=_code(ns, "fb2"), name="业务二", status="enabled"))
    second_business_id = second_business.id
    first_menu = await _seed(session, SysMenu(parent_id=0, name="甲", path=_path(ns, "fm1"), status="enabled"))
    first_menu_id = first_menu.id
    second_menu = await _seed(session, SysMenu(parent_id=0, name="乙", path=_path(ns, "fm2"), status="enabled"))
    second_menu_id = second_menu.id
    form = await service.create_form(
        menu_ids=ConcurrentStableList([first_menu_id]),
        business_id=first_business_id,
        component=None,
        status="enabled",
    )
    form_id = form.id
    await service.create_form(
        menu_ids=ConcurrentStableList(), business_id=second_business_id, component=None, status="enabled"
    )

    updated = await service.update_form(
        form_id,
        menu_ids=ConcurrentStableList([first_menu_id, second_menu_id, second_menu_id]),
        business_id=first_business_id,
        component="c",
        status="disabled",
    )
    assert updated.status == "disabled"
    links = await MenuFormRepository(cast("DbSession", session)).list_by_form(form_id)
    assert sorted(link.menu_id for link in links) == sorted([first_menu_id, second_menu_id])
    await session.rollback()  # 读查询会 autobegin，写路径前先结束隐式事务

    with pytest.raises(MenuNotFoundError):
        await service.update_form(
            _MISSING_ID,
            menu_ids=ConcurrentStableList(),
            business_id=first_business_id,
            component=None,
            status="enabled",
        )
    with pytest.raises(MenuNotFoundError):
        await service.update_form(
            form_id, menu_ids=ConcurrentStableList(), business_id=_MISSING_ID, component=None, status="enabled"
        )
    with pytest.raises(MenuNotFoundError):
        await service.update_form(
            form_id,
            menu_ids=ConcurrentStableList([_MISSING_ID]),
            business_id=first_business_id,
            component=None,
            status="enabled",
        )
    with pytest.raises(ConflictError):
        await service.update_form(
            form_id,
            menu_ids=ConcurrentStableList(),
            business_id=second_business_id,
            component=None,
            status="enabled",
        )

    vanishing = _service(
        session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_VanishForms(cast("DbSession", session))
    )
    with pytest.raises(MenuNotFoundError):
        await vanishing.update_form(
            form_id,
            menu_ids=ConcurrentStableList(),
            business_id=first_business_id,
            component=None,
            status="enabled",
        )

    await service.delete_form(form_id)
    with pytest.raises(MenuNotFoundError):
        await service.delete_form(_MISSING_ID)


async def test_button_write_paths(session: AsyncSession, ns: Namespace) -> None:
    """按钮写路径：表单 / 权限码缺行、业务不一致、同权限冲突、表单缺失降级与行消失竞态。"""
    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    first_business = await _seed(session, SysBusiness(code=_code(ns, "bb1"), name="业务一", status="enabled"))
    first_business_id = first_business.id
    second_business = await _seed(session, SysBusiness(code=_code(ns, "bb2"), name="业务二", status="enabled"))
    second_business_id = second_business.id
    first_action = await _seed(session, SysAction(code=_code(ns, "ba1"), name="动作一", status="enabled"))
    first_action_id = first_action.id
    second_action = await _seed(session, SysAction(code=_code(ns, "ba2"), name="动作二", status="enabled"))
    second_action_id = second_action.id
    first_permission = await _seed(
        session, SysPermission(business_id=first_business_id, action_id=first_action_id, status="enabled")
    )
    first_permission_id = first_permission.id
    foreign_permission = await _seed(
        session, SysPermission(business_id=second_business_id, action_id=first_action_id, status="enabled")
    )
    foreign_permission_id = foreign_permission.id
    second_permission = await _seed(
        session, SysPermission(business_id=first_business_id, action_id=second_action_id, status="enabled")
    )
    second_permission_id = second_permission.id
    form = await service.create_form(
        menu_ids=ConcurrentStableList(), business_id=first_business_id, component=None, status="enabled"
    )
    form_id = form.id

    with pytest.raises(MenuNotFoundError):
        await service.create_button(
            form_id=_MISSING_ID, permission_id=first_permission_id, name="X", type="toolbar", sort=0, status="enabled"
        )
    with pytest.raises(MenuNotFoundError):
        await service.create_button(
            form_id=form_id, permission_id=_MISSING_ID, name="X", type="toolbar", sort=0, status="enabled"
        )
    with pytest.raises(ConflictError):
        await service.create_button(
            form_id=form_id,
            permission_id=foreign_permission_id,
            name="X",
            type="toolbar",
            sort=0,
            status="enabled",
        )

    first_button = await service.create_button(
        form_id=form_id, permission_id=first_permission_id, name="一", type="toolbar", sort=1, status="enabled"
    )
    first_button_id = first_button.id
    second_button = await service.create_button(
        form_id=form_id, permission_id=second_permission_id, name="二", type="interface", sort=2, status="enabled"
    )
    second_button_id = second_button.id

    with pytest.raises(MenuNotFoundError):
        await service.update_button(
            _MISSING_ID, permission_id=first_permission_id, name="X", type="toolbar", sort=0, status="enabled"
        )
    with pytest.raises(MenuNotFoundError):
        await service.update_button(
            first_button_id, permission_id=_MISSING_ID, name="X", type="toolbar", sort=0, status="enabled"
        )
    with pytest.raises(ConflictError):
        await service.update_button(
            first_button_id, permission_id=foreign_permission_id, name="X", type="toolbar", sort=0, status="enabled"
        )
    with pytest.raises(ConflictError):
        await service.update_button(
            first_button_id, permission_id=second_permission_id, name="X", type="toolbar", sort=0, status="enabled"
        )

    changed = await service.update_button(
        first_button_id, permission_id=first_permission_id, name="改", type="interface", sort=9, status="disabled"
    )
    assert changed.name == "改"

    missing_form = _service(
        session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_MissingForms(cast("DbSession", session))
    )
    published = await missing_form.update_button(
        second_button_id, permission_id=second_permission_id, name="三", type="toolbar", sort=3, status="enabled"
    )
    assert published.name == "三"

    vanishing = _service(
        session,
        outbox=_OutboxSpy(),
        cache=MemoryCacheRegion(),
        buttons=_VanishButtons(cast("DbSession", session)),
    )
    with pytest.raises(MenuNotFoundError):
        await vanishing.update_button(
            second_button_id,
            permission_id=second_permission_id,
            name="四",
            type="toolbar",
            sort=4,
            status="enabled",
        )

    await service.delete_button(second_button_id)
    with pytest.raises(MenuNotFoundError):
        await service.delete_button(second_button_id)


async def test_field_write_paths(session: AsyncSession, ns: Namespace) -> None:
    """字段写路径：表单缺行、更新重派生、表单缺失降级、行消失竞态与删除。"""
    service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
    business = await _seed(session, SysBusiness(code=_code(ns, "db1"), name="业务", status="enabled"))
    business_id = business.id
    form = await service.create_form(
        menu_ids=ConcurrentStableList(), business_id=business_id, component=None, status="enabled"
    )
    form_id = form.id

    with pytest.raises(MenuNotFoundError):
        await service.create_field(
            form_id=_MISSING_ID, field_key="k", type="input", sort=0, status="enabled", i18n=_names("字段")
        )

    field, _ = await service.create_field(
        form_id=form_id, field_key="k", type="input", sort=1, status="enabled", i18n=_names("字段")
    )
    field_id = field.id
    updated, i18n = await service.update_field(
        field_id, type="select", sort=2, status="disabled", i18n=_names("字段改")
    )
    assert updated.type == "select"
    assert i18n.get("zh-CN") == "字段改"

    with pytest.raises(MenuNotFoundError):
        await service.update_field(_MISSING_ID, type="input", sort=0, status="enabled", i18n=_names("无"))

    missing_form = _service(
        session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_MissingForms(cast("DbSession", session))
    )
    renamed, _ = await missing_form.update_field(field_id, type="text", sort=3, status="enabled", i18n=_names("再改"))
    assert renamed.type == "text"

    vanishing = _service(
        session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), fields=_VanishFields(cast("DbSession", session))
    )
    with pytest.raises(MenuNotFoundError):
        await vanishing.update_field(field_id, type="text", sort=4, status="enabled", i18n=_names("又改"))

    await service.delete_field(field_id)
    with pytest.raises(MenuNotFoundError):
        await service.delete_field(field_id)
