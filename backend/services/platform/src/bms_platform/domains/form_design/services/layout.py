"""布局与字段属性服务：三级读写 / 缓存失效 / 事件发布 / 生效解析（10_01）。

- **写入**：整份覆盖式（同 `(form_code, scope, role_id)` 存在则改、否则建）；保存后**先提交、再失效缓存**
  （《架构设计 · 数据架构》§5.2「先写库后删缓存」），并在同一事务内发 `sys.form.updated`；
- **恢复默认**：删当前层级行 → 自然回退下一级（角色 → 租户 → 平台 → 空布局）；
- **读**：`list_by_form` 取三层行（属性同层同源），解析在 `services/assemble.py`；
- **缓存**：`bms:{tenant}:form:layout:{form_code}` 与 `bms:{tenant}:form:fields:{form_code}` 两 key +
  版本键 `bms:{tenant}:form:version`；缓存不可用降级直连库（语义不变，仅变慢）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import (
    FormLayoutInvalidError,
    FormNotCustomizableError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.formdesign.attrs import (
    FieldAttrs,
    dump_attrs,
    dump_attrs_config,
    parse_attrs_config,
    validate_attrs,
)
from bms_core.formdesign.layout import (
    FormLayout,
    dump_layout_config,
    layout_to_config,
    normalize_layout,
    parse_layout_config,
    validate_layout_refs,
)
from bms_core.models.platform.form_design import (
    LAYOUT_SCOPES,
    NO_ROLE_ID,
    SysFieldExt,
    SysFormFieldAttr,
    SysFormLayout,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_platform.domains.form_design.ports import (
    FormMetadataPort,
    OptionSetPort,
    PermissionPort,
    RolePort,
)
from bms_platform.domains.form_design.repositories.field_ext_i18n import FieldExtI18nRepository
from bms_platform.domains.form_design.repositories.layout import (
    FieldAttrRepository,
    FieldExtRepository,
    FormLayoutRepository,
)
from bms_platform.domains.form_design.services.assemble import (
    AssembledLayout,
    assemble_layout,
    collect_levels,
    pick_role_level,
)

if TYPE_CHECKING:
    from bms_core.lock.base import BaseDistributedLock
    from bms_platform.domains.form_design.services.field_ext import ExtFieldService

__all__ = ["CACHE_DOMAIN", "FORM_UPDATED_EVENT", "FormDesignService"]

_LOGGER = get_logger("bms.form_design")

FORM_UPDATED_EVENT = "sys.form.updated"
"""表单变更事件（已登记契约，不新增事件类型）。"""

CACHE_DOMAIN = "form"
"""缓存域简称（key 形如 `bms:{tenant}:form:layout:{form_code}`）。"""

DEFAULT_CACHE_TTL = 300
"""布局 / 字段清单缓存 TTL（秒；实际写入带随机偏移）。"""


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: UTC naive 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class FormDesignService(BaseFrameworkObject):
    """表单定制服务：布局 / 属性读写、层级恢复默认、生效解析。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        layouts: FormLayoutRepository,
        attrs: FieldAttrRepository,
        ext_fields: FieldExtRepository,
        ext_i18n: FieldExtI18nRepository,
        metadata: FormMetadataPort,
        permissions: PermissionPort | None,
        roles: RolePort | None,
        option_sets: OptionSetPort,
        cache: CacheRegion,
        outbox: BaseOutboxStore,
        tenant: str | None,
    ) -> None:
        """初始化。

        Args:
            session: 请求级会话（租户库）。
            uow: 请求级工作单元。
            layouts: 布局仓储。
            attrs: 字段属性仓储。
            ext_fields: 自建字段仓储。
            ext_i18n: 自建字段多语言仓储。
            metadata: 平台库表单元数据读面。
            permissions: 字段权限读面（None 表示不叠加：全开）。
            roles: 角色集读面（None 表示无角色视图，按租户 / 平台层解析）。
            option_sets: 选项集读面。
            cache: 缓存 Region。
            outbox: 事务性发件箱。
            tenant: 租户标识（缓存 key / 锁 key 用）。
        """
        self._session = session
        self._uow = uow
        self._layouts = layouts
        self._attrs = attrs
        self._ext_fields = ext_fields
        self._ext_i18n = ext_i18n
        self._metadata = metadata
        self._permissions = permissions
        self._roles = roles
        self._option_sets = option_sets
        self._cache = cache
        self._outbox = outbox
        self._tenant = tenant
        self._ddl: object | None = None
        self._invalidate_hook: object | None = None

    async def role_types(self, user_id: int | None) -> ConcurrentStableList[tuple[str, int]]:
        """取当前用户的角色集（`(role_type, role_id)` 插入序）。

        Args:
            user_id: 当前用户主键（None 表示未登录上下文，返回空）。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色集（无读面 / 无用户时为空）。
        """
        if self._roles is None or user_id is None:
            return ConcurrentStableList()
        return await self._roles.roles_of_user(user_id)

    # ------------------------------------------------------------------ 依赖注入（装配面）

    def bind_ddl(self, executor: object, *, invalidate: object | None = None) -> None:
        """注入 DDL 执行器与缓存失效回调（装配面调用；避免服务层直接依赖具体执行器）。

        Args:
            executor: DDL 执行器（`FormDdlExecutor`）。
            invalidate: 缓存失效回调（`Callable[[str], Awaitable[None]]`；None 表示用本服务自带的失效）。
        """
        self._ddl = executor
        self._invalidate_hook = invalidate

    @property
    def ddl(self) -> object | None:
        """DDL 执行器（未注入为 None）。

        Returns:
            object | None: 执行器实例。
        """
        return self._ddl

    async def invalidate_form(self, form_code: str) -> None:
        """外部可调的表单缓存失效（自建字段服务经回调复用）。

        Args:
            form_code: 表单标识。
        """
        await self._invalidate(form_code)

    def ext_field_service(self, lock: BaseDistributedLock) -> ExtFieldService:
        """按本服务的依赖构造自建字段服务（共用会话 / 元数据 / 选项集 / 发件箱 / 缓存失效）。

        Args:
            lock: 分布式锁（DDL 单租户串行）。

        Returns:
            ExtFieldService: 自建字段服务实例。
        """
        from bms_platform.domains.form_design.services.ddl import FormDdlExecutor
        from bms_platform.domains.form_design.services.field_ext import ExtFieldService

        executor = FormDdlExecutor(self._session, lock=lock, tenant=self._tenant)
        return ExtFieldService(
            session=self._session,
            uow=self._uow,
            fields=self._ext_fields,
            i18n=self._ext_i18n,
            metadata=self._metadata,
            option_sets=self._option_sets,
            outbox=self._outbox,
            lock=lock,
            ddl_executor=executor,
            tenant=self._tenant,
            invalidate=self.invalidate_form,
        )

    # ------------------------------------------------------------------ 读取

    async def list_levels(
        self, form_code: str
    ) -> tuple[
        ConcurrentStableList[SysFormLayout],
        ConcurrentStableList[SysFormFieldAttr],
        ConcurrentStableList[SysFieldExt],
    ]:
        """取该表单的三层布局、三层属性与自建字段（管理面用）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            tuple: （布局行, 属性行, 自建字段行）。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
        """
        snapshot = await self._metadata.load(form_code)
        if snapshot is None:
            raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
        layouts = await self._layouts.list_by_form(form_code)
        attr_rows = await self._attrs.list_by_form(form_code)
        ext_rows = await self._ext_fields.list_by_form(form_code)
        return layouts, attr_rows, ext_rows

    async def effect(
        self,
        form_code: str,
        *,
        level: str,
        role_types: ConcurrentStableList[tuple[str, int]],
    ) -> AssembledLayout:
        """解析生效布局（渲染路径核心）。

        Args:
            form_code: 表单标识（业务码）。
            level: 请求层级（渲染路径传 `role`）。
            role_types: 当前用户角色集（`(role_type, role_id)` 插入序）。

        Returns:
            AssembledLayout: 组装结果。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
        """
        snapshot = await self._metadata.load(form_code)
        if snapshot is None:
            raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
        layouts = await self._layouts.list_by_form(form_code)
        attr_rows = await self._attrs.list_by_form(form_code)
        ext_rows = await self._ext_fields.list_active(form_code)
        levels = collect_levels(layouts=layouts, attr_rows=attr_rows)
        candidates: ConcurrentStableList[tuple[str, int, FormLayout | None]] = ConcurrentStableList()
        role_map = levels.get("role") or ConcurrentStableDict()
        for role_type, role_id in role_types:
            candidate = role_map.get(role_id)
            candidates.add((role_type, role_id, candidate.layout if candidate is not None else None))
        role_id, role_layout = pick_role_level(candidates=candidates)
        platform_fields: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            ConcurrentStableDict(
                {
                    "key": field.field_key,
                    "label": field.name,
                    "type": field.type,
                    "group": "platform",
                    "sort": field.sort,
                    "status": "active" if field.status == "enabled" else "disabled",
                    "disabled": field.status != "enabled",
                }
            )
            for field in snapshot.fields
        )
        permission_map = (
            await self._permissions.resolve(
                form_id=snapshot.form_id,
                role_ids=ConcurrentStableList(role_id_pair for _role_type, role_id_pair in role_types),
            )
            if self._permissions is not None
            else ConcurrentStableDict()
        )
        permissions: ConcurrentStableDict[str, ConcurrentStableDict[str, object]] = ConcurrentStableDict()
        hidden: ConcurrentStableList[str] = ConcurrentStableList()
        for field_key, narrowing in permission_map.items():
            merged: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            visible = True
            editable = True
            for item in narrowing:
                if item.get("visible") is False:
                    visible = False
                if item.get("editable") is False:
                    editable = False
            if not visible:
                hidden.add(field_key)
            merged.set("visible", visible)
            merged.set("editable", editable)
            permissions.set(field_key, merged)
        assembled = assemble_layout(
            levels=levels,
            level=level,
            role_hint=(role_id, role_layout),
            platform_fields=platform_fields,
            ext_fields=ext_rows,
            hidden_keys=ConcurrentStableFrozenList(hidden),
            permissions=permissions,
            option_sets=self._collect_option_sets(ext_rows, attr_rows),
        )
        return assembled

    def _collect_option_sets(
        self,
        ext_fields: ConcurrentStableList[SysFieldExt],
        attr_rows: ConcurrentStableList[SysFormFieldAttr],
    ) -> ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]:
        """按 `option_set_key` 去重解析选项集快照（随响应一次下发）。

        Args:
            ext_fields: 自建字段（取 `option_set_key`）。
            attr_rows: 属性行（取 `attrs.optionSetKey`）。

        Returns:
            ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]: `{optionSetKey, items[]}` 列表。
        """
        keys: ConcurrentStableList[str] = ConcurrentStableList()
        for row in ext_fields:
            if row.option_set_key is not None and row.option_set_key not in keys:
                keys.add(row.option_set_key)
        for row in attr_rows:
            try:
                parsed = json.loads(row.attrs)
            except json.JSONDecodeError:  # pragma: no cover - 库内损坏由 parse_attrs 容错
                continue
            if isinstance(parsed, dict):
                key = parsed.get("optionSetKey") or parsed.get("option_set_key")
                if isinstance(key, str) and key != "" and key not in keys:
                    keys.add(key)
        snapshots: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for key in keys:
            if not self._option_sets.is_registered(key):
                continue
            snapshots.add(ConcurrentStableDict({"optionSetKey": key, "items": self._option_sets.resolve_items(key)}))
        return ConcurrentStableFrozenList(snapshots)

    async def delete_layout_by_id(
        self,
        layout_id: int,
        *,
        require_platform_admin_check: bool = False,
        user_id: int | None = None,
    ) -> tuple[SysFormLayout, bool] | None:
        """按主键删除布局行（整段事务内完成：取行 → 判权 → 删除 → 发事件）。

        Args:
            layout_id: 布局主键。
            require_platform_admin_check: 是否按行层级判平台超管。
            user_id: 当前用户主键。

        Returns:
            tuple[SysFormLayout, bool] | None: （被删行, 是否删到）；行不存在返回 None。
        """
        async with self._uow.begin():
            row = await self._layouts.get(layout_id)
            if row is None:
                return None
            if require_platform_admin_check and row.scope == "platform":
                await self._assert_platform_admin(user_id)
            removed = await self._layouts.purge_by_level(row.form_code, row.scope, row.role_id)
            await self._publish(form_code=row.form_code, form_id=0, changed_type="layout")
        await self._invalidate(row.form_code)
        return row, removed

    async def delete_attrs_by_id(
        self,
        attr_id: int,
        *,
        require_platform_admin_check: bool = False,
        user_id: int | None = None,
    ) -> tuple[SysFormFieldAttr, bool] | None:
        """按主键删除某层级全部属性（整段事务内完成）。

        Args:
            attr_id: 属性主键。
            require_platform_admin_check: 是否按行层级判平台超管。
            user_id: 当前用户主键。

        Returns:
            tuple[SysFormFieldAttr, bool] | None: （代表行, 是否删到）；行不存在返回 None。
        """
        async with self._uow.begin():
            row = await self._attrs.get(attr_id)
            if row is None:
                return None
            if require_platform_admin_check and row.scope == "platform":
                await self._assert_platform_admin(user_id)
            removed = await self._attrs.purge_level(row.form_code, row.scope, row.role_id)
            await self._publish(form_code=row.form_code, form_id=0, changed_type="attr")
        await self._invalidate(row.form_code)
        return row, removed

    async def get_layout(self, layout_id: int) -> SysFormLayout | None:
        """按主键取布局行（删除端点取层级信息用）。

        Args:
            layout_id: 布局主键。

        Returns:
            SysFormLayout | None: 布局行；不存在返回 None。
        """
        return await self._layouts.get(layout_id)

    async def get_attr(self, attr_id: int) -> SysFormFieldAttr | None:
        """按主键取属性行（删除端点取层级信息用）。

        Args:
            attr_id: 属性主键。

        Returns:
            SysFormFieldAttr | None: 属性行；不存在返回 None。
        """
        return await self._attrs.get(attr_id)

    def layout_config_of(self, row: SysFormLayout) -> ConcurrentStableFrozenDict[str, object]:
        """把库里存的布局 JSON 转归一后的配置字典（列表响应用）。

        Args:
            row: 布局行。

        Returns:
            ConcurrentStableFrozenDict[str, object]: 归一后的布局配置。
        """
        return layout_to_config(parse_layout_config(row.layout_config))

    def attrs_of(self, row: SysFormFieldAttr) -> ConcurrentStableFrozenDict[str, object]:
        """把库里存的属性 JSON 转归一后的字典（列表响应用）。

        Args:
            row: 属性行。

        Returns:
            ConcurrentStableFrozenDict[str, object]: 归一后的字段属性。
        """
        return dump_attrs(parse_attrs_config(row.attrs))

    async def _assert_platform_admin(self, user_id: int | None) -> None:
        r"""校验当前用户为平台超管（平台默认层级的写操作要求）。

        **必须在 \`uow.begin()\` 内调用**：读租户库（\`sys_user_role\`）会开启隐式事务，
        若在事务外先读，随后的 \`uow.begin()\` 会因「事务已开始」而失败。

        Args:
            user_id: 当前用户主键（None 表示无登录上下文）。

        Raises:
            PermissionError: 非平台超管（30001 / 403）。
        """
        from bms_core.core.exceptions import PermissionError as BizPermissionError

        roles = await self.role_types(user_id)
        if not any(role_type == "platform_admin" for role_type, _role_id in roles):
            raise BizPermissionError("平台默认布局仅平台超管可维护")

    # ------------------------------------------------------------------ 写入

    async def save_layout(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        layout_config: object,
        require_platform_admin: bool = False,
        user_id: int | None = None,
    ) -> SysFormLayout:
        """保存某层级布局（整份覆盖；校验字段引用后告警不阻断）。

        Args:
            form_code: 表单标识（业务码）。
            scope: 层级。
            role_id: 角色 ID（非角色层级传 0）。
            layout_config: 布局配置（字典；归一后写入）。
            require_platform_admin: 是否要求平台超管（`scope=platform` 写操作传 True）。
            user_id: 当前用户主键（判定平台超管用；None 表示不判）。

        Returns:
            SysFormLayout: 写入后的行。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
            FormLayoutInvalidError: 布局结构非法（40403）。
        """
        self._assert_scope(scope, role_id)
        snapshot = await self._metadata.load(form_code)
        if snapshot is None:
            raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
        if not isinstance(layout_config, dict | ConcurrentStableDict):
            raise FormLayoutInvalidError("布局配置须为对象")
        layout = normalize_layout(layout_config)
        issues = validate_layout_refs(
            layout,
            known_keys=ConcurrentStableFrozenList(field.field_key for field in snapshot.fields),
            disabled_keys=ConcurrentStableFrozenList(()),
        )
        blocking = [issue for issue in issues if issue.kind == "columns"]
        if blocking:
            raise FormLayoutInvalidError("；".join(issue.message for issue in blocking))
        actor = get_current_user_id()
        async with self._uow.begin():
            if require_platform_admin:
                await self._assert_platform_admin(user_id)
            row = await self._layouts.upsert(
                form_code=form_code,
                scope=scope,
                role_id=role_id,
                layout_config=dump_layout_config(layout),
                now=_utc_now(),
                actor=actor,
            )
            await self._publish(form_code=form_code, form_id=snapshot.form_id, changed_type="layout")
            reference = row.id
        await self._invalidate(form_code)
        _LOGGER.info("布局保存", form_code=form_code, scope=scope, role_id=role_id, layout_id=reference)
        return row

    async def delete_layout(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        require_platform_admin: bool = False,
        user_id: int | None = None,
    ) -> bool:
        """删除某层级布局（恢复默认回退下一级）。

        Args:
            form_code: 表单标识（业务码）。
            scope: 层级。
            role_id: 角色 ID。
            require_platform_admin: 是否要求平台超管。
            user_id: 当前用户主键（判定平台超管用）。

        Returns:
            bool: 删到为 True。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
        """
        self._assert_scope(scope, role_id)
        async with self._uow.begin():
            snapshot = await self._metadata.load(form_code)
            if snapshot is None:
                raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
            if require_platform_admin:
                await self._assert_platform_admin(user_id)
            removed = await self._layouts.purge_by_level(form_code, scope, role_id)
            await self._publish(form_code=form_code, form_id=snapshot.form_id, changed_type="layout")
        await self._invalidate(form_code)
        return removed

    async def save_attrs(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        items: ConcurrentStableList[tuple[str, object, str]],
        require_platform_admin: bool = False,
        user_id: int | None = None,
    ) -> ConcurrentStableList[SysFormFieldAttr]:
        """保存某层级字段属性（整份覆盖；逐字段校验）。

        Args:
            form_code: 表单标识（业务码）。
            scope: 层级。
            role_id: 角色 ID。
            items: 待写入项（`(field_key, attrs, field_type)` 插入序）。
            require_platform_admin: 是否要求平台超管。
            user_id: 当前用户主键（判定平台超管用）。

        Returns:
            ConcurrentStableList[SysFormFieldAttr]: 写入后的行。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
            FormAttrInvalidError: 属性非法（40408）。
        """
        self._assert_scope(scope, role_id)
        snapshot = await self._metadata.load(form_code)
        if snapshot is None:
            raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
        prepared: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        for field_key, raw_attrs, field_type in items:
            option_key = None
            if isinstance(raw_attrs, dict | ConcurrentStableDict):
                candidate = raw_attrs.get("optionSetKey") or raw_attrs.get("option_set_key")
                option_key = candidate if isinstance(candidate, str) else None
            option_values: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(())
            registered = option_key is not None and self._option_sets.is_registered(option_key)
            if registered and option_key is not None:
                option_values = ConcurrentStableFrozenList(
                    str(item.get("value")) for item in self._option_sets.resolve_items(option_key)
                )
            attrs: FieldAttrs = validate_attrs(
                raw_attrs,
                field_type=field_type,
                is_option_registered=registered,
                option_values=option_values,
            )
            prepared.add((field_key, dump_attrs_config(attrs)))
        async with self._uow.begin():
            if require_platform_admin:
                await self._assert_platform_admin(user_id)
            rows = await self._attrs.replace_level(
                form_code=form_code,
                scope=scope,
                role_id=role_id,
                items=prepared,
            )
            await self._publish(form_code=form_code, form_id=snapshot.form_id, changed_type="attr")
        await self._invalidate(form_code)
        return rows

    async def delete_attrs(
        self,
        *,
        form_code: str,
        scope: str,
        role_id: int,
        require_platform_admin: bool = False,
        user_id: int | None = None,
    ) -> bool:
        """删除某层级全部属性（恢复默认）。

        Args:
            form_code: 表单标识（业务码）。
            scope: 层级。
            role_id: 角色 ID。

        Returns:
            bool: 删到为 True。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
        """
        self._assert_scope(scope, role_id)
        async with self._uow.begin():
            snapshot = await self._metadata.load(form_code)
            if snapshot is None:
                raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
            if require_platform_admin:
                await self._assert_platform_admin(user_id)
            removed = await self._attrs.purge_level(form_code, scope, role_id)
            await self._publish(form_code=form_code, form_id=snapshot.form_id, changed_type="attr")
        await self._invalidate(form_code)
        return removed

    # ------------------------------------------------------------------ 公共助手

    def _assert_scope(self, scope: str, role_id: int) -> None:
        """校验层级与角色 ID 组合（角色层级必须带角色、非角色层级不得带）。

        Args:
            scope: 层级。
            role_id: 角色 ID。

        Raises:
            FormLayoutInvalidError: 层级非法或角色 ID 与层级不匹配（40403）。
        """
        if scope not in LAYOUT_SCOPES:
            raise FormLayoutInvalidError(f"层级非法：{scope}")
        if scope == "role" and role_id == NO_ROLE_ID:
            raise FormLayoutInvalidError("角色视图层级必须指定 role_id")
        if scope != "role" and role_id != NO_ROLE_ID:
            raise FormLayoutInvalidError(f"非角色层级不得指定 role_id：{scope}")

    async def _publish(self, *, form_code: str, form_id: int, changed_type: str) -> None:
        """写事务内发布 `sys.form.updated`（载荷字段与既有契约一致）。

        Args:
            form_code: 表单标识（聚合键用）。
            form_id: 表单主键。
            changed_type: 变更类别（`layout` / `attr` / `ext_field`）。
        """
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=FORM_UPDATED_EVENT,
                payload=ConcurrentStableDict(
                    {
                        "form_id": str(form_id),
                        "menu_id": "",
                        "business_id": "",
                        "changed_type": changed_type,
                    }
                ),
                aggregate_key=f"form:{form_code}",
            ),
        )

    async def _invalidate(self, form_code: str) -> None:
        """失效该表单的布局与字段缓存（先写库后删缓存；失败只告警）。

        Args:
            form_code: 表单标识。
        """
        layout_key = self._cache.build_key(f"layout:{form_code}", tenant=self._tenant)
        fields_key = self._cache.build_key(f"fields:{form_code}", tenant=self._tenant)
        version_key = self._cache.build_key("version", tenant=self._tenant)
        for key in (layout_key, fields_key):
            try:
                await self._cache.adelete(key)
            except Exception:  # pragma: no cover - 缓存实现自身的降级路径
                _LOGGER.warning("表单缓存失效失败（不阻断写）", cache_key=key)
        try:
            await self._cache.aincrease(version_key)
        except Exception:  # pragma: no cover - 同上
            _LOGGER.warning("表单版本键递增失败（不阻断写）", cache_key=version_key)

    def cache_keys(self, form_code: str) -> ConcurrentStableDict[str, str]:
        """取该表单的三把缓存 key（用例与排障用）。

        Args:
            form_code: 表单标识。

        Returns:
            ConcurrentStableDict[str, str]: `layout` / `fields` / `version` 三键。
        """
        return ConcurrentStableDict(
            {
                "layout": self._cache.build_key(f"layout:{form_code}", tenant=self._tenant),
                "fields": self._cache.build_key(f"fields:{form_code}", tenant=self._tenant),
                "version": self._cache.build_key("version", tenant=self._tenant),
            }
        )
