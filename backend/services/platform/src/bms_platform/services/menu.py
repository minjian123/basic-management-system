"""平台服务 services 层：菜单与权限元数据服务。

职责：

- **维护（平台超管）**：菜单 / 表单 / 按钮 / 字段的增改删 + 挂接链完整性校验；业务 / 动作码只读列示；
- **缓存**：菜单树与表单元数据按 `locale` 维度缓存（键 `bms:{租户}:menu:{locale}:{version}`，
  版本号经 `bms:global:menu:version` 计数器递增实现即时失效；TTL 与随机偏移由缓存基座承担）；
- **事件**：变更与元数据落库**同一事务**内经发件箱发布 `sys.form.updated`（当前无消费者，消费归阶段十）。

写路径统一「单次 `uow.begin()` 包住探测 + 写 + 发件箱」，避免会话重复开启事务。
"""

from typing import Annotated, cast

from pydantic import Field

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import (
    ConflictError,
    MenuFieldKeyConflictError,
    MenuI18nRequiredError,
    MenuNotFoundError,
    MenuPathConflictError,
    MenuReferencedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.serialization import normalize_collections
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.dict.sql import current_dict_locale
from bms_core.events.base import EventEnvelope
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.menu import menu_tree_key, menu_version_key
from bms_core.outbox.base import BaseOutboxStore
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema
from bms_platform.models.menu import (
    SysAction,
    SysBusiness,
    SysButton,
    SysField,
    SysForm,
    SysMenu,
    SysPermission,
)
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
    PermissionRepository,
)
from bms_platform.schemas.menu import (
    ActionItem,
    ActionList,
    BusinessItem,
    BusinessList,
    ButtonItem,
    ButtonList,
    FieldItem,
    FieldList,
    FormItem,
    FormList,
    MenuCreateRequest,
    MenuItem,
    MenuTree,
    MenuUpdateRequest,
    PermissionItem,
    PermissionList,
)

FORM_UPDATED_EVENT = "sys.form.updated"
"""菜单 / 表单 / 字段 / 按钮变更事件（契约已登记于 `bms_core/events/platform_events.py`）。"""

CHANGED_MENU = "menu"
CHANGED_FORM = "form"
CHANGED_BUTTON = "button"
CHANGED_FIELD = "field"


def request_locale() -> str:
    """当前请求语言（＝必填语言口径；不支持时回退系统默认语言）。

    Returns:
        str: 生效请求语言。
    """
    locale = current_dict_locale.get() or DEFAULT_LOCALE
    return locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE


def clean_i18n(names: ConcurrentStableDict[str, str]) -> ConcurrentStableDict[str, str]:
    """归一多语言文案映射（剔空白值；不改动语言集合，停用语言存量值原样保留）。

    Args:
        names: 语言标识 → 文案。

    Returns:
        ConcurrentStableDict[str, str]: 归一后的映射。
    """
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for locale, text in names.items():
        value = (text or "").strip()
        if value:
            result.set(locale, value)
    return result


def require_i18n_name(names: ConcurrentStableDict[str, str], *, locale: str) -> None:
    """必填语言校验（缺文案即拒绝）。

    Args:
        names: 归一后的多语言文案映射。
        locale: 必填语言（请求语言）。

    Raises:
        MenuI18nRequiredError: 必填语言缺文案（40208）。
    """
    if not (names.get(locale) or ""):
        raise MenuI18nRequiredError(f"缺少必填语言（{locale}）的文案")


def derive_default_name(names: ConcurrentStableDict[str, str], *, required_locale: str) -> str:
    """派生主表默认文案（系统默认语言 → 必填语言 → 首个有值语言）。

    主表默认文案列是**派生快照**（供列表零关联展示与排序），不由调用方单独提交。

    Args:
        names: 归一后的多语言文案映射。
        required_locale: 必填语言（请求语言）。

    Returns:
        str: 主表默认文案。

    Raises:
        MenuI18nRequiredError: 全部语言皆无文案（40208）。
    """
    for candidate in (DEFAULT_LOCALE, required_locale):
        value = names.get(candidate) or ""
        if value:
            return value
    for text in names.values():
        if text:
            return text
    raise MenuI18nRequiredError("多语言文案为空：至少一种语言须有文案")


def i18n_out(names: ConcurrentStableDict[str, str] | None, *, name: str, locale: str) -> ConcurrentStableDict[str, str]:
    """出参多语言映射：完整语言映射 + 必填语言缺失时以主表默认文案回填（不改写存储）。

    Args:
        names: 该主表行的多语言文案映射（可空）。
        name: 主表默认文案。
        locale: 必填语言（请求语言）。

    Returns:
        ConcurrentStableDict[str, str]: 补全后的映射。
    """
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if names is not None:
        for key, value in names.items():
            result.set(key, value)
    if not (result.get(locale) or ""):
        result.set(locale, name)
    return result


class SnapshotButton(BaseSchema):
    """缓存快照：按钮元数据。"""

    id: int = Field(description="按钮主键")
    permission_id: int = Field(description="权限码 ID")
    permission_code: str = Field(description="权限码（{业务码}:{动作码}）")
    name: str = Field(description="按钮名")
    type: str = Field(description="按钮形态")
    sort: int = Field(description="排序")


class SnapshotField(BaseSchema):
    """缓存快照：字段元数据。"""

    id: int = Field(description="字段主键")
    field_key: str = Field(description="字段键")
    name: str = Field(description="字段名（按 locale 本地化，缺省回退默认文案）")
    type: str = Field(description="字段类型")
    sort: int = Field(description="排序")


class SnapshotForm(BaseSchema):
    """缓存快照：表单元数据（含按钮 / 字段）。"""

    id: int = Field(description="表单主键")
    business_id: int = Field(description="业务码 ID")
    business_code: str = Field(description="业务权限码")
    component: str | None = Field(description="表单视图组件标识")
    buttons: Annotated[ConcurrentStableList[SnapshotButton], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="按钮元数据"
    )
    fields: Annotated[ConcurrentStableList[SnapshotField], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段元数据"
    )


class SnapshotMenu(BaseSchema):
    """缓存快照：菜单节点（含挂接的表单元数据，多对多）。"""

    id: int = Field(description="菜单主键")
    parent_id: int = Field(description="父菜单 ID（0 为根）")
    name: str = Field(description="菜单名（本地化）")
    path: str = Field(description="前端路由路径")
    component: str | None = Field(description="视图组件标识")
    icon: str | None = Field(description="完整 icon key")
    sort: int = Field(description="排序")
    hidden: bool = Field(description="仅隐藏侧栏入口")
    forms: Annotated[ConcurrentStableList[SnapshotForm], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="该入口关联的表单元数据（挂接链完整时非空）"
    )


class MenuSnapshot(BaseSchema):
    """缓存快照：未按用户过滤的菜单与权限元数据（按 locale 维度缓存）。"""

    locale: str = Field(description="语言标识")
    version: int = Field(description="元数据版本号")
    permission_codes: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="全部权限码（业务码:动作码）"
    )
    menus: Annotated[ConcurrentStableList[SnapshotMenu], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="菜单元数据（保持 sort 顺序）"
    )


def _snapshot_form(
    form: SysForm,
    business: SysBusiness,
    *,
    action_by_id: ConcurrentStableDict[int, SysAction],
    permission_by_id: ConcurrentStableDict[int, SysPermission],
    business_by_id: ConcurrentStableDict[int, SysBusiness],
    buttons_by_form: ConcurrentStableDict[int, ConcurrentStableList[SysButton]],
    fields_by_form: ConcurrentStableDict[int, ConcurrentStableList[SysField]],
    field_i18n: ConcurrentStableDict[int, str],
) -> SnapshotForm:
    """表单实体 → 快照（含按钮与字段元数据）。

    Args:
        form: 表单记录。
        business: 表单挂接的业务码记录。
        action_by_id: 动作码 ID → 记录（仅启用态）。
        permission_by_id: 权限码 ID → 记录（仅启用态）。
        business_by_id: 业务码 ID → 记录（仅启用态）。
        buttons_by_form: 表单 ID → 按钮列表。
        fields_by_form: 表单 ID → 字段列表。
        field_i18n: 字段 ID → 本地化文案。

    Returns:
        SnapshotForm: 表单元数据快照。
    """
    buttons: ConcurrentStableList[SnapshotButton] = ConcurrentStableList()
    for button in buttons_by_form.get(form.id) or ():
        permission = permission_by_id.get(button.permission_id)
        if permission is None:
            continue
        action = action_by_id.get(permission.action_id)
        permission_business = business_by_id.get(permission.business_id)
        if action is None or permission_business is None:
            continue
        buttons.add(
            SnapshotButton(
                id=button.id,
                permission_id=button.permission_id,
                permission_code=f"{permission_business.code}:{action.code}",
                name=button.name,
                type=button.type,
                sort=button.sort,
            )
        )
    return SnapshotForm(
        id=form.id,
        business_id=business.id,
        business_code=business.code,
        component=form.component,
        buttons=buttons,
        fields=ConcurrentStableList(
            SnapshotField(
                id=field.id,
                field_key=field.field_key,
                name=field_i18n.get(field.id, field.name),
                type=field.type,
                sort=field.sort,
            )
            for field in (fields_by_form.get(form.id) or ())
        ),
    )


def _menu_item(row: SysMenu, i18n: ConcurrentStableDict[str, str]) -> MenuItem:
    """菜单记录 → 契约行（不含子节点）。

    Args:
        row: 菜单记录。
        i18n: 该菜单的多语言文案映射（含必填语言回填）。

    Returns:
        MenuItem: 菜单契约行。
    """
    return MenuItem(
        id=row.id,
        parent_id=row.parent_id,
        name=row.name,
        path=row.path,
        component=row.component,
        icon=row.icon,
        sort=row.sort,
        hidden=row.hidden,
        status=row.status,
        i18n=i18n,
    )


class MenuMetadataService(BaseFrameworkObject):
    """菜单与权限元数据服务（维护 + 缓存 + 事件）。

    组合多仓储与横切能力（工作单元 / 发件箱 / 缓存），故沿框架对象层派生
    （口径同 `org` 服务的仓储直承型服务）。
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        businesses: BusinessRepository,
        actions: ActionRepository,
        permissions: PermissionRepository,
        menus: MenuRepository,
        forms: FormRepository,
        menu_forms: MenuFormRepository,
        buttons: ButtonRepository,
        fields: FieldRepository,
        outbox: BaseOutboxStore,
        cache: CacheRegion,
    ) -> None:
        """初始化。

        Args:
            uow: 请求级工作单元。
            businesses: 业务码字典仓储。
            actions: 动作码字典仓储。
            permissions: 权限码仓储（业务码 × 动作码组合）。
            menus: 菜单仓储。
            forms: 表单仓储。
            menu_forms: 菜单 ↔ 表单关联仓储（多对多）。
            buttons: 按钮仓储。
            fields: 字段仓储。
            outbox: 发件箱存储（事件发布）。
            cache: 缓存 Region（应用级）。
        """
        self._uow = uow
        self._businesses = businesses
        self._actions = actions
        self._permissions = permissions
        self._menus = menus
        self._forms = forms
        self._menu_forms = menu_forms
        self._buttons = buttons
        self._fields = fields
        self._outbox = outbox
        self._cache = cache

    @property
    def _session(self) -> DbSession:
        """请求级会话。

        Returns:
            DbSession: 工作单元绑定的会话。
        """
        return cast("DbSession", self._uow.session)

    # ------------------------------------------------------------------ 缓存

    async def version(self) -> int:
        """当前元数据版本号（缓存计数器；未初始化按 0）。

        Returns:
            int: 元数据版本号。
        """
        raw = await self._cache.aget(menu_version_key())
        return raw if isinstance(raw, int) else 0

    async def invalidate(self) -> None:
        """递增版本号并删除当前语言旧键（变更即时生效；语言与租户取请求上下文）。"""
        locale = current_dict_locale.get() or DEFAULT_LOCALE
        tenant_id = current_tenant_id_str()
        old_version = await self.version()
        await self._cache.aincrease(menu_version_key())
        await self._cache.adelete(menu_tree_key(tenant_id, locale, old_version))

    async def load_snapshot(self, *, locale: str, tenant_id: str | None, ttl: int) -> MenuSnapshot:
        """装载未过滤的菜单与权限元数据（缓存优先、未命中回源 DB）。

        Args:
            locale: 语言标识。
            tenant_id: 租户主键字符串（缓存键租户位）。
            ttl: 缓存有效期（秒）。

        Returns:
            MenuSnapshot: 元数据快照。
        """
        version = await self.version()
        key = menu_tree_key(tenant_id, locale, version)
        cached = await self._cache.aget(key)
        if isinstance(cached, dict):
            try:
                return MenuSnapshot.model_validate(cached)
            except ValueError:  # pragma: no cover - 脏缓存按未命中处理
                pass
        snapshot = await self._build_snapshot(locale=locale, version=version)
        payload = cast("dict[str, object]", normalize_collections(snapshot.model_dump()))
        await self._cache.aset(key, payload, ttl)
        return snapshot

    async def _build_snapshot(self, *, locale: str, version: int) -> MenuSnapshot:
        """由库构建元数据快照（仅启用态；本地化名称就地解析）。

        Args:
            locale: 语言标识。
            version: 元数据版本号。

        Returns:
            MenuSnapshot: 元数据快照。
        """
        businesses = await self._businesses.list_all()
        actions = await self._actions.list_all()
        permissions = await self._permissions.list_all()
        menus = await self._menus.list_all()
        forms = await self._forms.list_all()
        menu_forms = await self._menu_forms.list_all()
        buttons = await self._buttons.list_all()
        fields = await self._fields.list_all()

        menu_i18n = await self._menus.list_i18n(ConcurrentStableList(row.id for row in menus), locale)
        field_i18n = await self._fields.list_i18n(ConcurrentStableList(row.id for row in fields), locale)

        business_by_id = ConcurrentStableDict[int, SysBusiness](
            {row.id: row for row in businesses if row.status == "enabled"}
        )
        action_by_id = ConcurrentStableDict[int, SysAction]({row.id: row for row in actions if row.status == "enabled"})
        permission_by_id = ConcurrentStableDict[int, SysPermission](
            {row.id: row for row in permissions if row.status == "enabled"}
        )
        form_by_id = ConcurrentStableDict[int, SysForm]({row.id: row for row in forms if row.status == "enabled"})
        forms_by_menu = ConcurrentStableDict[int, ConcurrentStableList[SysForm]]()
        for link in menu_forms:
            form = form_by_id.get(link.form_id)
            if form is None:
                continue
            form_bucket = forms_by_menu.get(link.menu_id)
            if form_bucket is None:
                form_bucket = ConcurrentStableList[SysForm]()
                forms_by_menu.set(link.menu_id, form_bucket)
            form_bucket.add(form)

        buttons_by_form = ConcurrentStableDict[int, ConcurrentStableList[SysButton]]()
        for button in buttons:
            if button.status != "enabled":
                continue
            bucket = buttons_by_form.get(button.form_id)
            if bucket is None:
                bucket = ConcurrentStableList[SysButton]()
                buttons_by_form.set(button.form_id, bucket)
            bucket.add(button)
        fields_by_form = ConcurrentStableDict[int, ConcurrentStableList[SysField]]()
        for field in fields:
            if field.status != "enabled":
                continue
            field_bucket = fields_by_form.get(field.form_id)
            if field_bucket is None:
                field_bucket = ConcurrentStableList[SysField]()
                fields_by_form.set(field.form_id, field_bucket)
            field_bucket.add(field)

        permission_codes = ConcurrentStableList[str]()
        for permission in permissions:
            if permission.status != "enabled":
                continue
            business = business_by_id.get(permission.business_id)
            action = action_by_id.get(permission.action_id)
            if business is None or action is None:
                continue
            permission_codes.add(f"{business.code}:{action.code}")

        snapshots = ConcurrentStableList[SnapshotMenu]()
        for menu in menus:
            if menu.status != "enabled":
                continue
            form_metas = ConcurrentStableList[SnapshotForm]()
            for form in forms_by_menu.get(menu.id) or ():
                business = business_by_id.get(form.business_id)
                if business is None:
                    continue
                form_metas.add(
                    _snapshot_form(
                        form,
                        business,
                        action_by_id=action_by_id,
                        permission_by_id=permission_by_id,
                        business_by_id=business_by_id,
                        buttons_by_form=buttons_by_form,
                        fields_by_form=fields_by_form,
                        field_i18n=field_i18n,
                    )
                )
            snapshots.add(
                SnapshotMenu(
                    id=menu.id,
                    parent_id=menu.parent_id,
                    name=menu_i18n.get(menu.id, menu.name),
                    path=menu.path,
                    component=menu.component,
                    icon=menu.icon,
                    sort=menu.sort,
                    hidden=menu.hidden,
                    forms=form_metas,
                )
            )
        return MenuSnapshot(
            locale=locale,
            version=version,
            permission_codes=permission_codes,
            menus=snapshots,
        )

    # ------------------------------------------------------------------ 事件

    async def _publish_form_updated(
        self, *, form_id: int | None, menu_id: int | None, business_id: int | None, changed_type: str
    ) -> None:
        """在同一事务内发布 `sys.form.updated`（无消费者，消费归阶段十）。

        Args:
            form_id: 表单 ID（菜单 / 表单变更可空）。
            menu_id: 菜单 ID。
            business_id: 业务码 ID。
            changed_type: 变更对象类别（menu / form / button / field）。
        """
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=FORM_UPDATED_EVENT,
                payload=ConcurrentStableDict(
                    {
                        "form_id": "" if form_id is None else str(form_id),
                        "menu_id": "" if menu_id is None else str(menu_id),
                        "business_id": "" if business_id is None else str(business_id),
                        "changed_type": changed_type,
                    }
                ),
                aggregate_key=f"form:{form_id}" if form_id is not None else f"menu:{menu_id}",
            ),
        )

    # ------------------------------------------------------------------ 读取（平台维护视图）

    async def list_menu_tree(self) -> MenuTree:
        """菜单树（平台维护视图，含 disabled 与 hidden）。

        出参含每个菜单的**完整多语言映射**（多语言文案字段据此回显全部语言）；必填语言缺文案时以
        主表默认文案回填，便于界面直接编辑而不出现空白格。

        Returns:
            MenuTree: 根级菜单列表（子节点嵌套）。
        """
        rows = await self._menus.list_all()
        locale = request_locale()
        all_i18n = await self._menus.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        nodes = ConcurrentStableDict[int, MenuItem](
            {row.id: _menu_item(row, i18n_out(all_i18n.get(row.id), name=row.name, locale=locale)) for row in rows}
        )
        roots = ConcurrentStableList[MenuItem]()
        for row in rows:
            node = nodes[row.id]
            parent = nodes.get(row.parent_id)
            if parent is None:
                roots.add(node)
            else:
                parent.children.add(node)
        return MenuTree(items=roots)

    async def list_forms(self, menu_id: int | None) -> FormList:
        """表单清单（`menu_id` 非空时**按菜单关联过滤**；None 为全量，含无入口表单）。

        Args:
            menu_id: 菜单 ID；None 表示全量。

        Returns:
            FormList: 表单清单（每行带关联菜单入口清单 `menu_ids`）。
        """
        associations = await self._menu_forms.list_all()
        menu_ids_by_form = ConcurrentStableDict[int, ConcurrentStableList[int]]()
        for link in associations:
            entry = menu_ids_by_form.get(link.form_id)
            if entry is None:
                entry = ConcurrentStableList[int]()
                menu_ids_by_form.set(link.form_id, entry)
            entry.add(link.menu_id)
        rows = await self._forms.list_all()
        items = ConcurrentStableList(
            FormItem(
                id=row.id,
                menu_ids=ConcurrentStableList(menu_ids_by_form.get(row.id) or ()),
                business_id=row.business_id,
                component=row.component,
                status=row.status,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
            if menu_id is None or menu_id in (menu_ids_by_form.get(row.id) or ())
        )
        return FormList(items=items)

    async def list_buttons(self, form_id: int | None) -> ButtonList:
        """按钮清单（按表单过滤，可空 = 全部）。

        Args:
            form_id: 表单 ID；None 表示全部。

        Returns:
            ButtonList: 按钮清单。
        """
        rows = await self._buttons.list_by_form(form_id) if form_id is not None else await self._buttons.list_all()
        return ButtonList(
            items=ConcurrentStableList(
                ButtonItem(
                    id=row.id,
                    form_id=row.form_id,
                    permission_id=row.permission_id,
                    name=row.name,
                    type=row.type,
                    sort=row.sort,
                    status=row.status,
                )
                for row in rows
            )
        )

    async def list_fields(self, form_id: int | None) -> FieldList:
        """字段清单（按表单过滤，可空 = 全部；出参含各字段的完整多语言映射）。

        Args:
            form_id: 表单 ID；None 表示全部。

        Returns:
            FieldList: 字段清单。
        """
        rows = await self._fields.list_by_form(form_id) if form_id is not None else await self._fields.list_all()
        locale = request_locale()
        all_i18n = await self._fields.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        return FieldList(
            items=ConcurrentStableList(
                FieldItem(
                    id=row.id,
                    form_id=row.form_id,
                    field_key=row.field_key,
                    name=row.name,
                    type=row.type,
                    sort=row.sort,
                    status=row.status,
                    i18n=i18n_out(all_i18n.get(row.id), name=row.name, locale=locale),
                )
                for row in rows
            )
        )

    async def list_businesses(self) -> BusinessList:
        """业务码清单（纯资源维度；平台维护视图 / 租户只读；出参含完整多语言映射）。

        Returns:
            BusinessList: 业务码清单。
        """
        rows = await self._businesses.list_all()
        locale = request_locale()
        all_i18n = await self._businesses.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        return BusinessList(
            items=ConcurrentStableList(
                BusinessItem(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    status=row.status,
                    i18n=i18n_out(all_i18n.get(row.id), name=row.name, locale=locale),
                )
                for row in rows
            )
        )

    async def list_actions(self) -> ActionList:
        """动作码清单（全局字典；平台维护视图 / 租户只读；出参含完整多语言映射）。

        Returns:
            ActionList: 动作码清单。
        """
        rows = await self._actions.list_all()
        locale = request_locale()
        all_i18n = await self._actions.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        return ActionList(
            items=ConcurrentStableList(
                ActionItem(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    status=row.status,
                    i18n=i18n_out(all_i18n.get(row.id), name=row.name, locale=locale),
                )
                for row in rows
            )
        )

    async def list_permissions(self, business_id: int | None) -> PermissionList:
        """权限码清单（业务码 × 动作码组合；平台维护视图 / 租户只读）。

        Args:
            business_id: 业务码 ID；None 表示全部。

        Returns:
            PermissionList: 权限码清单（code 由业务码与动作码组合派生）。
        """
        rows = await self._permissions.list_by_business(business_id)
        businesses = ConcurrentStableDict[int, SysBusiness]({row.id: row for row in await self._businesses.list_all()})
        actions = ConcurrentStableDict[int, SysAction]({row.id: row for row in await self._actions.list_all()})
        items: ConcurrentStableList[PermissionItem] = ConcurrentStableList()
        for row in rows:
            business = businesses.get(row.business_id)
            action = actions.get(row.action_id)
            if business is None or action is None:
                continue
            items.add(
                PermissionItem(
                    id=row.id,
                    code=f"{business.code}:{action.code}",
                    business_id=row.business_id,
                    business_code=business.code,
                    action_id=row.action_id,
                    action_code=action.code,
                    status=row.status,
                )
            )
        return PermissionList(items=items)

    # ------------------------------------------------------------------ 写（菜单）

    async def create_menu(self, req: MenuCreateRequest) -> tuple[SysMenu, ConcurrentStableDict[str, str]]:
        """新增菜单（只收多语言文案映射；主表默认文案由服务端派生）。

        Args:
            req: 新增请求。

        Returns:
            tuple[SysMenu, ConcurrentStableDict[str, str]]: 新建菜单与该菜单的完整多语言映射（出参用）。

        Raises:
            MenuI18nRequiredError: 缺少必填语言（请求语言）的文案（40208）。
            MenuPathConflictError: 路由路径已存在（40203）。
            MenuNotFoundError: 父菜单不存在（40201）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            await self._ensure_parent(req.parent_id)
            if await self._menus.get_by_path(req.path) is not None:
                raise MenuPathConflictError(f"路由路径已存在：{req.path}")
            row = await self._menus.create(
                parent_id=req.parent_id,
                name=name,
                path=req.path,
                component=req.component,
                icon=req.icon,
                sort=req.sort,
                hidden=req.hidden,
                status=req.status,
            )
            await self._menus.replace_i18n(row.id, names)
            await self._publish_form_updated(form_id=None, menu_id=row.id, business_id=None, changed_type=CHANGED_MENU)
        await self.invalidate()
        return row, i18n_out(names, name=name, locale=locale)

    async def update_menu(self, menu_id: int, req: MenuUpdateRequest) -> tuple[SysMenu, ConcurrentStableDict[str, str]]:
        """更新菜单（整体替换；只收多语言文案映射，主表默认文案重新派生）。

        Args:
            menu_id: 菜单主键。
            req: 更新请求。

        Returns:
            tuple[SysMenu, ConcurrentStableDict[str, str]]: 更新后菜单与该菜单的完整多语言映射（出参用）。

        Raises:
            MenuI18nRequiredError: 缺少必填语言（请求语言）的文案（40208）。
            MenuNotFoundError: 菜单不存在（40201）。
            MenuPathConflictError: 路由路径与他人冲突（40203）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            current = await self._menus.get(menu_id)
            if current is None:
                raise MenuNotFoundError(f"菜单不存在：{menu_id}")
            await self._ensure_parent(req.parent_id)
            existing = await self._menus.get_by_path(req.path)
            if existing is not None and existing.id != menu_id:
                raise MenuPathConflictError(f"路由路径已存在：{req.path}")
            updated = await self._menus.update(
                menu_id,
                parent_id=req.parent_id,
                name=name,
                path=req.path,
                component=req.component,
                icon=req.icon,
                sort=req.sort,
                hidden=req.hidden,
                status=req.status,
            )
            if updated is None:
                raise MenuNotFoundError(f"菜单不存在：{menu_id}")
            await self._menus.replace_i18n(menu_id, names)
            await self._publish_form_updated(form_id=None, menu_id=menu_id, business_id=None, changed_type=CHANGED_MENU)
        await self.invalidate()
        return updated, i18n_out(names, name=name, locale=locale)

    async def delete_menu(self, menu_id: int) -> None:
        """删除菜单（软删除；被表单 / 子菜单引用时拒绝）。

        Args:
            menu_id: 菜单主键。

        Raises:
            MenuNotFoundError: 菜单不存在（40201）。
            MenuReferencedError: 被引用，禁止删除（40206）。
        """
        async with self._uow.begin():
            if await self._menus.get(menu_id) is None:
                raise MenuNotFoundError(f"菜单不存在：{menu_id}")
            if await self._menu_forms.list_by_menu(menu_id):
                raise MenuReferencedError(f"菜单已挂表单，先解除挂接：{menu_id}")
            children = await self._menus.list_all()
            if any(row.parent_id == menu_id for row in children):
                raise MenuReferencedError(f"菜单存在子节点，先删除子节点：{menu_id}")
            await self._menus.soft_delete(menu_id)
            await self._publish_form_updated(form_id=None, menu_id=menu_id, business_id=None, changed_type=CHANGED_MENU)
        await self.invalidate()

    async def _ensure_parent(self, parent_id: int) -> None:
        """父菜单存在性校验（0 为根）。

        Args:
            parent_id: 父菜单 ID。

        Raises:
            MenuNotFoundError: 父菜单不存在（40201）。
        """
        if parent_id == 0:
            return
        if await self._menus.get(parent_id) is None:
            raise MenuNotFoundError(f"父菜单不存在：{parent_id}")

    # ------------------------------------------------------------------ 写（表单）

    async def create_form(
        self,
        *,
        menu_ids: ConcurrentStableList[int],
        business_id: int,
        component: str | None,
        status: str,
    ) -> SysForm:
        """新增表单（业务 1:1；菜单入口多对多，可空 = 孤儿表单）。

        Args:
            menu_ids: 关联菜单 ID 清单（去重；空 = 不关联任何入口）。
            business_id: 业务码 ID。
            component: 表单视图组件标识。
            status: 状态。

        Returns:
            SysForm: 新建表单。

        Raises:
            MenuNotFoundError: 菜单或业务码不存在（40201）。
            ConflictError: 业务码已被其它表单挂接（1:1）。
        """
        async with self._uow.begin():
            normalized = self._dedupe(menu_ids)
            await self._ensure_menus(normalized)
            if await self._businesses.get(business_id) is None:
                raise MenuNotFoundError(f"业务码不存在：{business_id}")
            if await self._forms.get_by_business(business_id) is not None:
                raise ConflictError(f"业务码已挂表单：{business_id}")
            row = await self._forms.create(business_id=business_id, component=component, status=status)
            for menu_id in normalized:
                await self._menu_forms.create(menu_id=menu_id, form_id=row.id)
            await self._publish_form_updated(
                form_id=row.id, menu_id=None, business_id=business_id, changed_type=CHANGED_FORM
            )
        await self.invalidate()
        return row

    async def update_form(
        self,
        form_id: int,
        *,
        menu_ids: ConcurrentStableList[int],
        business_id: int,
        component: str | None,
        status: str,
    ) -> SysForm:
        """更新表单（菜单入口关联**全量替换**）。

        Args:
            form_id: 表单主键。
            menu_ids: 关联菜单 ID 清单（全量；空 = 解除全部入口）。
            business_id: 业务码 ID。
            component: 表单视图组件标识。
            status: 状态。

        Returns:
            SysForm: 更新后表单。

        Raises:
            MenuNotFoundError: 表单 / 菜单 / 业务码不存在（40201）。
            ConflictError: 业务码已被其它表单挂接（1:1）。
        """
        async with self._uow.begin():
            current = await self._forms.get(form_id)
            if current is None:
                raise MenuNotFoundError(f"表单不存在：{form_id}")
            normalized = self._dedupe(menu_ids)
            await self._ensure_menus(normalized)
            if await self._businesses.get(business_id) is None:
                raise MenuNotFoundError(f"业务码不存在：{business_id}")
            existing = await self._forms.get_by_business(business_id)
            if existing is not None and existing.id != form_id:
                raise ConflictError(f"业务码已挂表单：{business_id}")
            updated = await self._forms.update(form_id, business_id=business_id, component=component, status=status)
            if updated is None:
                raise MenuNotFoundError(f"表单不存在：{form_id}")
            await self._menu_forms.delete_by_form(form_id)
            for menu_id in normalized:
                await self._menu_forms.create(menu_id=menu_id, form_id=form_id)
            await self._publish_form_updated(
                form_id=form_id, menu_id=None, business_id=business_id, changed_type=CHANGED_FORM
            )
        await self.invalidate()
        return updated

    @staticmethod
    def _dedupe(menu_ids: ConcurrentStableList[int]) -> ConcurrentStableList[int]:
        """菜单入口清单去重（保持首次出现序）。

        Args:
            menu_ids: 原始菜单 ID 清单。

        Returns:
            ConcurrentStableList[int]: 去重后的菜单 ID 清单。
        """
        seen: ConcurrentStableSet[int] = ConcurrentStableSet()
        result: ConcurrentStableList[int] = ConcurrentStableList()
        for menu_id in menu_ids:
            if menu_id in seen:
                continue
            seen.add(menu_id)
            result.add(menu_id)
        return result

    async def _ensure_menus(self, menu_ids: ConcurrentStableList[int]) -> None:
        """菜单入口存在性校验。

        Args:
            menu_ids: 菜单 ID 清单。

        Raises:
            MenuNotFoundError: 存在不存在的菜单（40201）。
        """
        for menu_id in menu_ids:
            if await self._menus.get(menu_id) is None:
                raise MenuNotFoundError(f"菜单不存在：{menu_id}")

    async def delete_form(self, form_id: int) -> None:
        """删除表单（软删除；存在按钮 / 字段时拒绝）。

        Args:
            form_id: 表单主键。

        Raises:
            MenuNotFoundError: 表单不存在（40201）。
            MenuReferencedError: 存在按钮 / 字段引用（40206）。
        """
        async with self._uow.begin():
            current = await self._forms.get(form_id)
            if current is None:
                raise MenuNotFoundError(f"表单不存在：{form_id}")
            if await self._buttons.list_by_form(form_id) or await self._fields.list_by_form(form_id):
                raise MenuReferencedError(f"表单存在按钮 / 字段，先删除：{form_id}")
            await self._forms.soft_delete(form_id)
            await self._menu_forms.delete_by_form(form_id)
            await self._publish_form_updated(
                form_id=form_id,
                menu_id=None,
                business_id=current.business_id,
                changed_type=CHANGED_FORM,
            )
        await self.invalidate()

    # ------------------------------------------------------------------ 写（按钮）

    async def create_button(
        self, *, form_id: int, permission_id: int, name: str, type: str, sort: int, status: str
    ) -> SysButton:
        """新增按钮（表单 + 权限码 1:1）。

        Args:
            form_id: 表单 ID。
            permission_id: 权限码 ID。
            name: 按钮名。
            type: 按钮形态。
            sort: 排序。
            status: 状态。

        Returns:
            SysButton: 新建按钮。

        Raises:
            MenuNotFoundError: 表单或权限码不存在（40201）。
            ConflictError: 同表单同权限码已存在按钮，或权限码业务与表单业务不一致。
        """
        async with self._uow.begin():
            form = await self._forms.get(form_id)
            if form is None:
                raise MenuNotFoundError(f"表单不存在：{form_id}")
            permission = await self._permissions.get(permission_id)
            if permission is None:
                raise MenuNotFoundError(f"权限码不存在：{permission_id}")
            if permission.business_id != form.business_id:
                raise ConflictError(f"权限码业务与表单业务不一致：{permission_id}")
            if await self._buttons.get_by_form_permission(form_id, permission_id) is not None:
                raise ConflictError(f"同表单同权限码按钮已存在：{form_id}/{permission_id}")
            row = await self._buttons.create(
                form_id=form_id, permission_id=permission_id, name=name, type=type, sort=sort, status=status
            )
            await self._publish_form_updated(
                form_id=form_id, menu_id=None, business_id=form.business_id, changed_type=CHANGED_BUTTON
            )
        await self.invalidate()
        return row

    async def update_button(
        self, button_id: int, *, permission_id: int, name: str, type: str, sort: int, status: str
    ) -> SysButton:
        """更新按钮。

        Args:
            button_id: 按钮主键。
            permission_id: 权限码 ID。
            name: 按钮名。
            type: 按钮形态。
            sort: 排序。
            status: 状态。

        Returns:
            SysButton: 更新后按钮。

        Raises:
            MenuNotFoundError: 按钮或权限码不存在（40201）。
            ConflictError: 改后与同表单其它按钮同权限码，或权限码业务与表单业务不一致。
        """
        async with self._uow.begin():
            current = await self._buttons.get(button_id)
            if current is None:
                raise MenuNotFoundError(f"按钮不存在：{button_id}")
            permission = await self._permissions.get(permission_id)
            if permission is None:
                raise MenuNotFoundError(f"权限码不存在：{permission_id}")
            form = await self._forms.get(current.form_id)
            if form is not None and permission.business_id != form.business_id:
                raise ConflictError(f"权限码业务与表单业务不一致：{permission_id}")
            existing = await self._buttons.get_by_form_permission(current.form_id, permission_id)
            if existing is not None and existing.id != button_id:
                raise ConflictError(f"同表单同权限码按钮已存在：{current.form_id}/{permission_id}")
            updated = await self._buttons.update(
                button_id, permission_id=permission_id, name=name, type=type, sort=sort, status=status
            )
            if updated is None:
                raise MenuNotFoundError(f"按钮不存在：{button_id}")
            await self._publish_form_updated(
                form_id=current.form_id,
                menu_id=None,
                business_id=form.business_id if form is not None else None,
                changed_type=CHANGED_BUTTON,
            )
        await self.invalidate()
        return updated

    async def delete_button(self, button_id: int) -> None:
        """删除按钮（软删除）。

        Args:
            button_id: 按钮主键。

        Raises:
            MenuNotFoundError: 按钮不存在（40201）。
        """
        async with self._uow.begin():
            current = await self._buttons.get(button_id)
            if current is None:
                raise MenuNotFoundError(f"按钮不存在：{button_id}")
            await self._buttons.soft_delete(button_id)
            form = await self._forms.get(current.form_id)
            await self._publish_form_updated(
                form_id=current.form_id,
                menu_id=None,
                business_id=form.business_id if form is not None else None,
                changed_type=CHANGED_BUTTON,
            )
        await self.invalidate()

    # ------------------------------------------------------------------ 写（字段）

    async def create_field(
        self,
        *,
        form_id: int,
        field_key: str,
        type: str,
        sort: int,
        status: str,
        i18n: ConcurrentStableDict[str, str],
    ) -> tuple[SysField, ConcurrentStableDict[str, str]]:
        """新增字段（表单内字段键唯一；只收多语言文案映射，字段名由服务端派生）。

        Args:
            form_id: 表单 ID。
            field_key: 字段键。
            type: 字段类型。
            sort: 排序。
            status: 状态。
            i18n: 多语言文案映射（必含请求语言文案）。

        Returns:
            tuple[SysField, ConcurrentStableDict[str, str]]: 新建字段与该字段的完整多语言映射（出参用）。

        Raises:
            MenuI18nRequiredError: 缺少必填语言（请求语言）的文案（40208）。
            MenuNotFoundError: 表单不存在（40201）。
            MenuFieldKeyConflictError: 字段键在表单内重复（40205）。
        """
        locale = request_locale()
        names = clean_i18n(i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            form = await self._forms.get(form_id)
            if form is None:
                raise MenuNotFoundError(f"表单不存在：{form_id}")
            if await self._fields.get_by_form_key(form_id, field_key) is not None:
                raise MenuFieldKeyConflictError(f"字段键在表单内重复：{field_key}")
            row = await self._fields.create(
                form_id=form_id, field_key=field_key, name=name, type=type, sort=sort, status=status
            )
            await self._fields.replace_i18n(row.id, names)
            await self._publish_form_updated(
                form_id=form_id, menu_id=None, business_id=form.business_id, changed_type=CHANGED_FIELD
            )
        await self.invalidate()
        return row, i18n_out(names, name=name, locale=locale)

    async def update_field(
        self,
        field_id: int,
        *,
        type: str,
        sort: int,
        status: str,
        i18n: ConcurrentStableDict[str, str],
    ) -> tuple[SysField, ConcurrentStableDict[str, str]]:
        """更新字段（只收多语言文案映射，字段名重新派生）。

        Args:
            field_id: 字段主键。
            type: 字段类型。
            sort: 排序。
            status: 状态。
            i18n: 多语言文案映射（必含请求语言文案）。

        Returns:
            tuple[SysField, ConcurrentStableDict[str, str]]: 更新后字段与该字段的完整多语言映射（出参用）。

        Raises:
            MenuI18nRequiredError: 缺少必填语言（请求语言）的文案（40208）。
            MenuNotFoundError: 字段不存在（40201）。
        """
        locale = request_locale()
        names = clean_i18n(i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            current = await self._fields.get(field_id)
            if current is None:
                raise MenuNotFoundError(f"字段不存在：{field_id}")
            updated = await self._fields.update(field_id, name=name, type=type, sort=sort, status=status)
            if updated is None:
                raise MenuNotFoundError(f"字段不存在：{field_id}")
            await self._fields.replace_i18n(field_id, names)
            form = await self._forms.get(current.form_id)
            await self._publish_form_updated(
                form_id=current.form_id,
                menu_id=None,
                business_id=form.business_id if form is not None else None,
                changed_type=CHANGED_FIELD,
            )
        await self.invalidate()
        return updated, i18n_out(names, name=name, locale=locale)

    async def delete_field(self, field_id: int) -> None:
        """删除字段（软删除）。

        Args:
            field_id: 字段主键。

        Raises:
            MenuNotFoundError: 字段不存在（40201）。
        """
        async with self._uow.begin():
            current = await self._fields.get(field_id)
            if current is None:
                raise MenuNotFoundError(f"字段不存在：{field_id}")
            await self._fields.soft_delete(field_id)
            form = await self._forms.get(current.form_id)
            await self._publish_form_updated(
                form_id=current.form_id,
                menu_id=None,
                business_id=form.business_id if form is not None else None,
                changed_type=CHANGED_FIELD,
            )
        await self.invalidate()
