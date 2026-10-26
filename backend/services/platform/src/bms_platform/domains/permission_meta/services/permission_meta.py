"""权限元数据服务：业务码 / 动作码 / 权限码维护（`permission_meta` 业务域）。

- 组合本域三仓储 + **跨域只读探测**（按钮挂接 / 表单挂接 / 角色授权）：探测面以 Protocol 注入，
  由 `bms_platform.wiring` 装配——本域不 import 他域实现（域边界经公共出口与装配面共同维持）；
- 写路径统一：工作单元内变更 → 递增元数据版本（与菜单表单域共用 `bms_platform.services.metadata_cache`）。
"""

from typing import Any, Protocol

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    MenuCodeConflictError,
    MenuNotFoundError,
    MenuPermissionExistsError,
    MenuReferencedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository,
    BusinessRepository,
    PermissionRepository,
)
from bms_platform.domains.permission_meta.schemas.permission_meta import (
    ActionCreateRequest,
    ActionItem,
    ActionList,
    ActionUpdateRequest,
    BusinessCreateRequest,
    BusinessItem,
    BusinessList,
    BusinessUpdateRequest,
    PermissionCreateRequest,
    PermissionGenerateRequest,
    PermissionGenerateResult,
    PermissionItem,
    PermissionList,
    PermissionUpdateRequest,
)
from bms_platform.services.i18n_text import clean_i18n, derive_default_name, i18n_out, request_locale, require_i18n_name
from bms_platform.services.metadata_cache import bump_metadata_version

__all__ = ["PermissionMetadataService"]


class ButtonProbe(Protocol):
    """按钮挂接只读探测（菜单表单域）：按权限码列示挂接按钮。"""

    async def list_by_permission(self, permission_id: int) -> ConcurrentStableList[Any]: ...


class FormProbe(Protocol):
    """表单挂接只读探测（菜单表单域）：按业务码取唯一表单。"""

    async def get_by_business(self, business_id: int) -> object | None: ...


class RoleReferenceProbe(Protocol):
    """角色授权引用只读探测（角色域）：权限码是否已被角色授权引用。"""

    async def count_permission_refs(self, permission_id: int) -> int: ...


class PermissionMetadataService(BaseFrameworkObject):
    """权限元数据服务（业务码 / 动作码 / 权限码维护 + 停用 / 删除前置校验）。

    跨域只读探测以 Protocol 形态注入（按钮挂接、表单挂接、角色授权），本类不 import 他域实现。
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        businesses: BusinessRepository,
        actions: ActionRepository,
        permissions: PermissionRepository,
        buttons: ButtonProbe,
        forms: FormProbe,
        cache: CacheRegion,
        references: RoleReferenceProbe | None = None,
    ) -> None:
        """初始化。

        Args:
            uow: 请求级工作单元。
            businesses: 业务码字典仓储。
            actions: 动作码字典仓储。
            permissions: 权限码仓储（业务码 × 动作码组合）。
            buttons: 按钮挂接探测（菜单表单域的只读面）。
            forms: 表单挂接探测（菜单表单域的只读面）。
            cache: 缓存 Region（版本号失效）。
            references: 角色授权引用探测（角色域的只读面；缺省不探测）。
        """
        self._uow = uow
        self._businesses = businesses
        self._actions = actions
        self._permissions = permissions
        self._buttons = buttons
        self._forms = forms
        self._cache = cache
        self._references = references

    async def invalidate(self) -> None:
        """递增元数据版本（与菜单表单域共用双版本失效）。"""
        await bump_metadata_version(self._cache)

    async def list_businesses(self) -> BusinessList:
        """业务码清单（纯资源维度；平台维护视图 / 租户只读；出参含完整多语言映射）。

        Returns:
            BusinessList: 业务码清单。
        """
        rows = await self._businesses.list_all()
        locale = request_locale()
        all_i18n = await self._businesses.list_i18n_all(ConcurrentStableList(row.id for row in rows))
        counts = await self._permissions.count_by_businesses()
        return BusinessList(
            items=ConcurrentStableList(
                BusinessItem(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    status=row.status,
                    permission_count=counts.get(row.id, 0),
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
        locale = request_locale()
        business_rows = await self._businesses.list_all()
        action_rows = await self._actions.list_all()
        businesses = ConcurrentStableDict[int, SysBusiness]({row.id: row for row in business_rows})
        actions = ConcurrentStableDict[int, SysAction]({row.id: row for row in action_rows})
        business_i18n = await self._businesses.list_i18n_all(ConcurrentStableList(row.id for row in business_rows))
        action_i18n = await self._actions.list_i18n_all(ConcurrentStableList(row.id for row in action_rows))
        items: ConcurrentStableList[PermissionItem] = ConcurrentStableList()
        for row in rows:
            business = businesses.get(row.business_id)
            action = actions.get(row.action_id)
            if business is None or action is None:
                continue
            business_name = i18n_out(business_i18n.get(business.id), name=business.name, locale=locale).get(
                locale, business.name
            )
            action_name = i18n_out(action_i18n.get(action.id), name=action.name, locale=locale).get(locale, action.name)
            items.add(
                PermissionItem(
                    id=row.id,
                    code=f"{business.code}:{action.code}",
                    name=f"{business_name}·{action_name}",
                    business_id=row.business_id,
                    business_code=business.code,
                    action_id=row.action_id,
                    action_code=action.code,
                    status=row.status,
                )
            )
        return PermissionList(items=items)

    async def create_business(self, req: BusinessCreateRequest) -> SysBusiness:
        """新增业务码（`code` 创建后只读；软删除同码自动恢复）。

        Args:
            req: 新增请求。

        Returns:
            SysBusiness: 新建 / 恢复后的业务码行。

        Raises:
            MenuI18nRequiredError: 缺必填语言文案（40208）。
            MenuCodeConflictError: 业务码已存在（40209）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            if await self._businesses.get_by_code(req.code) is not None:
                raise MenuCodeConflictError(f"业务码已存在：{req.code}")
            deleted = await self._businesses.get_deleted_by_code(req.code)
            if deleted is not None:
                deleted.restore()
                row = await self._businesses.update(deleted.id, name=name, status=req.status)
            else:
                row = await self._businesses.create(code=req.code, name=name, status=req.status)
            if row is None:  # pragma: no cover - 恢复后行必存在
                raise MenuNotFoundError(f"业务码不存在：{req.code}")
            await self._businesses.replace_i18n(row.id, names)
        await self.invalidate()
        return row

    async def update_business(self, business_id: int, req: BusinessUpdateRequest) -> SysBusiness:
        """更新业务码（`code` 不可改；停用时连带停用其权限码）。

        Args:
            business_id: 业务码 ID。
            req: 更新请求（名称与状态）。

        Returns:
            SysBusiness: 更新后业务码行。

        Raises:
            MenuNotFoundError: 业务码不存在（40201）。
            MenuReferencedError: 停用时其权限码被按钮 / 角色授权引用（40206）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            current = await self._businesses.get(business_id)
            if current is None:
                raise MenuNotFoundError(f"业务码不存在：{business_id}")
            if current.status == "enabled" and req.status == "disabled":
                await self._ensure_business_stoppable(business_id)
                for permission in await self._permissions.list_by_business(business_id):
                    await self._permissions.update(permission.id, status="disabled")
            updated = await self._businesses.update(business_id, name=name, status=req.status)
            if updated is None:  # pragma: no cover - 已探测存在
                raise MenuNotFoundError(f"业务码不存在：{business_id}")
            await self._businesses.replace_i18n(business_id, names)
        await self.invalidate()
        return updated

    async def delete_business(self, business_id: int) -> None:
        """删除业务码（有条件删除：其下有权限码或被表单挂接即拒绝）。

        Args:
            business_id: 业务码 ID。

        Raises:
            MenuNotFoundError: 业务码不存在（40201）。
            MenuReferencedError: 存在权限码或表单挂接（40206）。
        """
        async with self._uow.begin():
            if await self._businesses.get(business_id) is None:
                raise MenuNotFoundError(f"业务码不存在：{business_id}")
            if await self._permissions.count_by_business(business_id) > 0:
                raise MenuReferencedError(f"业务码仍有权限码，先删除权限码：{business_id}")
            if await self._forms.get_by_business(business_id) is not None:
                raise MenuReferencedError(f"业务码已被表单挂接，先解除挂接：{business_id}")
            await self._businesses.soft_delete(business_id)
        await self.invalidate()

    async def _ensure_business_stoppable(self, business_id: int) -> None:
        """停用前置校验：其下任一权限码被按钮或角色授权引用即拒绝。

        Args:
            business_id: 业务码 ID。

        Raises:
            MenuReferencedError: 存在引用（40206）。
        """
        for permission in await self._permissions.list_by_business(business_id):
            await self._ensure_permission_stoppable(permission.id)

    async def create_action(self, req: ActionCreateRequest) -> SysAction:
        """新增动作码（`code` 创建后只读；软删除同码自动恢复）。

        Args:
            req: 新增请求。

        Returns:
            SysAction: 新建 / 恢复后的动作码行。

        Raises:
            MenuI18nRequiredError: 缺必填语言文案（40208）。
            MenuCodeConflictError: 动作码已存在（40209）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            if await self._actions.get_by_code(req.code) is not None:
                raise MenuCodeConflictError(f"动作码已存在：{req.code}")
            deleted = await self._actions.get_deleted_by_code(req.code)
            if deleted is not None:
                deleted.restore()
                row = await self._actions.update(deleted.id, name=name, status=req.status)
            else:
                row = await self._actions.create(code=req.code, name=name, status=req.status)
            if row is None:  # pragma: no cover - 恢复后行必存在
                raise MenuNotFoundError(f"动作码不存在：{req.code}")
            await self._actions.replace_i18n(row.id, names)
        await self.invalidate()
        return row

    async def update_action(self, action_id: int, req: ActionUpdateRequest) -> SysAction:
        """更新动作码（`code` 不可改；停用时连带停用其权限码）。

        Args:
            action_id: 动作码 ID。
            req: 更新请求（名称与状态）。

        Returns:
            SysAction: 更新后动作码行。

        Raises:
            MenuNotFoundError: 动作码不存在（40201）。
            MenuReferencedError: 停用时其权限码被引用（40206）。
        """
        locale = request_locale()
        names = clean_i18n(req.i18n)
        require_i18n_name(names, locale=locale)
        name = derive_default_name(names, required_locale=locale)
        async with self._uow.begin():
            current = await self._actions.get(action_id)
            if current is None:
                raise MenuNotFoundError(f"动作码不存在：{action_id}")
            if current.status == "enabled" and req.status == "disabled":
                for permission in await self._permissions.list_by_action(action_id):
                    await self._ensure_permission_stoppable(permission.id)
                for permission in await self._permissions.list_by_action(action_id):
                    await self._permissions.update(permission.id, status="disabled")
            updated = await self._actions.update(action_id, name=name, status=req.status)
            if updated is None:  # pragma: no cover - 已探测存在
                raise MenuNotFoundError(f"动作码不存在：{action_id}")
            await self._actions.replace_i18n(action_id, names)
        await self.invalidate()
        return updated

    async def delete_action(self, action_id: int) -> None:
        """删除动作码（有条件删除：其下有权限码即拒绝）。

        Args:
            action_id: 动作码 ID。

        Raises:
            MenuNotFoundError: 动作码不存在（40201）。
            MenuReferencedError: 存在权限码（40206）。
        """
        async with self._uow.begin():
            if await self._actions.get(action_id) is None:
                raise MenuNotFoundError(f"动作码不存在：{action_id}")
            if await self._permissions.count_by_action(action_id) > 0:
                raise MenuReferencedError(f"动作码仍有权限码，先删除权限码：{action_id}")
            await self._actions.soft_delete(action_id)
        await self.invalidate()

    async def create_permission(self, req: PermissionCreateRequest) -> SysPermission:
        """手工新增权限码组合（组合只读；软删除同组合自动恢复）。

        Args:
            req: 新增请求。

        Returns:
            SysPermission: 新建 / 恢复后的权限码行。

        Raises:
            MenuNotFoundError: 业务码或动作码不存在（40201）。
            MenuPermissionExistsError: 组合已存在（40210）。
        """
        async with self._uow.begin():
            if await self._businesses.get(req.business_id) is None:
                raise MenuNotFoundError(f"业务码不存在：{req.business_id}")
            if await self._actions.get(req.action_id) is None:
                raise MenuNotFoundError(f"动作码不存在：{req.action_id}")
            if await self._permissions.get_by_pair(req.business_id, req.action_id) is not None:
                raise MenuPermissionExistsError(f"权限码组合已存在：{req.business_id}:{req.action_id}")
            deleted = await self._permissions.get_deleted_by_pair(req.business_id, req.action_id)
            if deleted is not None:
                await self._permissions.restore(deleted.id)
                row = await self._permissions.update(deleted.id, status=req.status)
            else:
                row = await self._permissions.create(
                    business_id=req.business_id,
                    action_id=req.action_id,
                    status=req.status,
                )
            if row is None:  # pragma: no cover - 恢复后行必存在
                raise MenuNotFoundError("权限码不存在")
        await self.invalidate()
        return row

    async def generate_permissions(self, req: PermissionGenerateRequest) -> PermissionGenerateResult:
        """批量补生成缺失的权限码组合。

        Args:
            req: 范围（空 = 全部启用业务码 × 全部启用动作码）与是否含停用项。

        Returns:
            PermissionGenerateResult: 新建 / 恢复 / 跳过计数。
        """
        async with self._uow.begin():
            businesses = await self._businesses.list_all()
            actions = await self._actions.list_all()
            if not req.include_disabled:
                businesses = ConcurrentStableList(row for row in businesses if row.status == "enabled")
                actions = ConcurrentStableList(row for row in actions if row.status == "enabled")
            if req.business_ids:
                wanted_business = set(req.business_ids)
                businesses = ConcurrentStableList(row for row in businesses if row.id in wanted_business)
            if req.action_ids:
                wanted_action = set(req.action_ids)
                actions = ConcurrentStableList(row for row in actions if row.id in wanted_action)
            existing = await self._permissions.list_all()
            active_pairs = {(row.business_id, row.action_id) for row in existing}
            deleted_pairs: dict[tuple[int, int], int] = {}  # bare-collections:allow（补生成临时映射，仅本函数内）
            for business in businesses:
                for action in actions:
                    pair = (business.id, action.id)
                    if pair in active_pairs:
                        continue
                    deleted = await self._permissions.get_deleted_by_pair(business.id, action.id)
                    if deleted is not None:
                        deleted_pairs[pair] = deleted.id

            created = 0
            restored = 0
            skipped = 0
            for business in businesses:
                for action in actions:
                    pair = (business.id, action.id)
                    if pair in active_pairs:
                        skipped += 1
                        continue
                    if pair in deleted_pairs:
                        await self._permissions.restore(deleted_pairs[pair])
                        await self._permissions.update(deleted_pairs[pair], status="enabled")
                        restored += 1
                        continue
                    await self._permissions.create(business_id=business.id, action_id=action.id, status="enabled")
                    created += 1
        if created or restored:
            await self.invalidate()
        return PermissionGenerateResult(created=created, restored=restored, skipped=skipped)

    async def update_permission(self, permission_id: int, req: PermissionUpdateRequest) -> SysPermission:
        """更新权限码（组合不可换绑，仅状态；停用前校验引用）。

        Args:
            permission_id: 权限码 ID。
            req: 更新请求（状态）。

        Returns:
            SysPermission: 更新后权限码行。

        Raises:
            MenuNotFoundError: 权限码不存在（40201）。
            MenuReferencedError: 停用时仍被按钮 / 角色授权引用（40206）。
        """
        async with self._uow.begin():
            current = await self._permissions.get(permission_id)
            if current is None:
                raise MenuNotFoundError(f"权限码不存在：{permission_id}")
            if current.status == "enabled" and req.status == "disabled":
                await self._ensure_permission_stoppable(permission_id)
            updated = await self._permissions.update(permission_id, status=req.status)
            if updated is None:  # pragma: no cover - 已探测存在
                raise MenuNotFoundError(f"权限码不存在：{permission_id}")
        await self.invalidate()
        return updated

    async def delete_permission(self, permission_id: int) -> None:
        """删除权限码（有条件删除：被按钮或角色授权引用即拒绝）。

        Args:
            permission_id: 权限码 ID。

        Raises:
            MenuNotFoundError: 权限码不存在（40201）。
            MenuReferencedError: 存在按钮挂接或角色授权（40206）。
        """
        async with self._uow.begin():
            if await self._permissions.get(permission_id) is None:
                raise MenuNotFoundError(f"权限码不存在：{permission_id}")
            await self._ensure_permission_stoppable(permission_id)
            await self._permissions.soft_delete(permission_id)
        await self.invalidate()

    async def _ensure_permission_stoppable(self, permission_id: int) -> None:
        """权限码停用 / 删除前置校验：按钮挂接与角色授权均视为引用。

        Args:
            permission_id: 权限码 ID。

        Raises:
            MenuReferencedError: 存在引用（40206）。
        """
        if await self._buttons.list_by_permission(permission_id):
            raise MenuReferencedError(f"权限码已被按钮挂接，先解除挂接：{permission_id}")
        if self._references is not None and await self._references.count_permission_refs(permission_id) > 0:
            raise MenuReferencedError(f"权限码已被角色授权，先解除授权：{permission_id}")
