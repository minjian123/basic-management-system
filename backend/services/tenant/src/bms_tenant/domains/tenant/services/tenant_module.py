"""租户模块服务：目录校验 / 开通清单 / 开关 / 状态集（任务 `04_01`）。

- **目录**：经 service_client 调 platform `GET /api/v1/modules/snapshot`（服务身份），按 TTL 缓存；
  不可达时抛 `ServiceUnavailableError`（管理面失败可见；门禁侧另有 fail-open 口径）。
- **可勾选**：`TENANT_OPTIONAL_MODULE_KEYS` 中且目录 `status=enabled`；未注册 / 未启用 → `82007`。
- **状态集**（内部契约）：开通清单 `enabled` / `disabled` 两组；基础模块恒 `enabled`（不在清单也视为开通）。
- **恒开通**：目录行标记 `tenant_base`（平台按恒开通清单下发）**或**基座常量兜底（对端旧版本缺字段）。
- 开关只切状态、不删行；变更后删除共享缓存键（Redis 域跨实例即删）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ParamError, ServiceUnavailableError, TenantModuleUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.models.tenant.tenant_module import TENANT_MODULE_DISABLED, TENANT_MODULE_ENABLED
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest, ServiceResponse
from bms_core.services.module_registry import (
    TENANT_BASE_MODULE_KEYS,
    TENANT_OPTIONAL_MODULE_KEYS,
)
from bms_core.tenant_module.remote import tenant_module_cache_key
from bms_tenant.domains.tenant.repositories.tenant_module import TenantModuleRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import (
    ModuleStatusResponse,
    TenantModuleItem,
    TenantModuleOption,
    TenantModuleStatus,
)

__all__ = ["ModuleCatalog", "TenantModuleService"]

_LOGGER = get_logger("bms.tenant_module")

_PLATFORM_SERVICE = "platform"
_CATALOG_PATH = "/api/v1/modules/snapshot"
_CATALOG_SCOPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("module_catalog",))
_CATALOG_TTL = 60


@dataclass(frozen=True)
class CatalogModule(BaseValueObject):
    """目录模块记录（门禁与管理面共用）。"""

    module_key: str
    name: str
    table_prefix: str
    errcode_segment: str | None
    service_group: str
    status: str
    tenant_base: bool = False
    """恒开通标记（平台按恒开通清单下发的派生标记；旧版本对端不返回时缺省 `False`，由基座常量兜底）。"""


def is_tenant_base_module(item: CatalogModule) -> bool:
    """模块是否「恒开通」（不参与开通勾选、不受模块门禁拦截）。

    判定 = 目录行标记 **或** 基座常量：租户服务不装载产品清单，无法自行知道产品模块的恒开通声明，
    故以平台目录出口下发的 `tenant_base` 为准；对端旧版本不返回该字段时回落常量（平台模块仍恒开通）。

    Args:
        item: 目录模块。

    Returns:
        bool: 恒开通为 True。
    """
    return item.tenant_base or item.module_key in TENANT_BASE_MODULE_KEYS


class ModuleCatalog(BaseFrameworkObject):
    """服务目录快照读取（platform 契约 + 缓存）。"""

    def __init__(self, *, client: BaseServiceClient, cache: CacheRegion | None = None, ttl: int = _CATALOG_TTL) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端。
            cache: 缓存域。
            ttl: 快照缓存 TTL（秒）。
        """
        self._client = client
        self._cache = cache
        self._ttl = ttl

    async def modules(self) -> ConcurrentStableList[CatalogModule]:
        """取目录全量清单（缓存优先）。

        Returns:
            ConcurrentStableList[CatalogModule]: 目录模块。

        Raises:
            ServiceUnavailableError: 目录不可达 / 响应非法（10007 / 503）。
        """
        cache_key = self._cache_key()
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if isinstance(cached, list):
                return ConcurrentStableList(
                    _from_row(ConcurrentStableDict(cast("dict[str, object]", item)))
                    for item in cast("list[object]", cached)
                )
        response = await self._client.call(
            ServiceRequest(
                service=_PLATFORM_SERVICE,
                method="GET",
                path=_CATALOG_PATH,
                policy=ServiceCallPolicy(scopes=_CATALOG_SCOPES),
            )
        )
        rows = _catalog_rows(response)
        if self._cache is not None:
            self._cache.set(cache_key, [_to_row(item) for item in rows], self._ttl)
        return rows

    def _cache_key(self) -> str:
        """目录快照缓存键。

        Returns:
            str: 缓存键。
        """
        if self._cache is None:
            return "module_catalog"
        return self._cache.build_key("module_catalog", tenant="global")


class TenantModuleService(BaseFrameworkObject):
    """租户模块服务（会话绑定；事务边界由调用方负责）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        catalog: ModuleCatalog,
        cache: CacheRegion | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话。
            catalog: 服务目录读取器。
            cache: 缓存域（模块状态缓存键删除用）。
        """
        self._repo = TenantModuleRepository(session)
        self._catalog = catalog
        self._cache = cache

    async def options(self) -> ConcurrentStableList[TenantModuleOption]:
        """开通向导模块选项（目录全量；可勾选标记）。

        Returns:
            ConcurrentStableList[TenantModuleOption]: 选项清单。
        """
        modules = await self._catalog.modules()
        return ConcurrentStableList(
            TenantModuleOption(
                module_key=item.module_key,
                name=item.name,
                table_prefix=item.table_prefix,
                errcode_segment=item.errcode_segment,
                service_group=item.service_group,
                catalog_status=item.status,
                optional=item.module_key in TENANT_OPTIONAL_MODULE_KEYS and item.status == "enabled",
            )
            for item in modules
        )

    async def list_items(self, tenant_id: int) -> ConcurrentStableList[TenantModuleItem]:
        """租户模块清单（可勾选产品模块 × 开通清单，三态）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[TenantModuleItem]: 模块项。
        """
        modules = ConcurrentStableDict({item.module_key: item for item in await self._catalog.modules()})
        rows = ConcurrentStableList[TenantModuleItem]()
        for module_key in sorted(TENANT_OPTIONAL_MODULE_KEYS):
            catalog_item = modules.get(module_key)
            row = await self._repo.get(tenant_id, module_key)
            rows.add(
                TenantModuleItem(
                    module_key=module_key,
                    name=catalog_item.name if catalog_item is not None else module_key,
                    table_prefix=catalog_item.table_prefix if catalog_item is not None else "",
                    errcode_segment=catalog_item.errcode_segment if catalog_item is not None else None,
                    optional=True,
                    status=cast("TenantModuleStatus", row.status if row is not None else "not_opened"),
                    opened_at=row.opened_at if row is not None else None,
                )
            )
        return rows

    async def open_base_modules(self, tenant_id: int, *, opened_by: int | None = None) -> None:
        """开通基础能力模块（目录启用且属恒开通清单）。

        Args:
            tenant_id: 租户主键。
            opened_by: 操作人。
        """
        modules = await self._catalog.modules()
        keys = ConcurrentStableList(
            item.module_key for item in modules if is_tenant_base_module(item) and item.status == "enabled"
        )
        await self._repo.open(tenant_id=tenant_id, module_keys=keys, opened_by=opened_by)

    async def open_modules(
        self, tenant_id: int, module_keys: ConcurrentStableList[str], *, opened_by: int | None = None
    ) -> ConcurrentStableList[str]:
        """开通勾选的产品模块（校验目录后再写）。

        Args:
            tenant_id: 租户主键。
            module_keys: 勾选模块清单。
            opened_by: 操作人。

        Returns:
            ConcurrentStableList[str]: 实际开通的模块标识。

        Raises:
            TenantModuleUnavailableError: 模块未注册 / 未启用（82007 / 400）。
            ParamError: 勾选了基础能力模块（不可勾选；10001）。
        """
        validated = await self.validate_optional(module_keys)
        if validated:
            await self._repo.open(tenant_id=tenant_id, module_keys=validated, opened_by=opened_by)
        return validated

    async def switch(self, tenant_id: int, module_key: str, status: str, *, opened_by: int | None = None) -> None:
        """切换模块状态（未开通即开通）。

        Args:
            tenant_id: 租户主键。
            module_key: 模块标识。
            status: 目标状态（`enabled` / `disabled`）。
            opened_by: 操作人。

        Raises:
            TenantModuleUnavailableError: 模块未注册 / 未启用（82007 / 400）。
        """
        await self.validate_optional(ConcurrentStableList([module_key]))
        row = await self._repo.get(tenant_id, module_key)
        if row is None:
            await self._repo.open(
                tenant_id=tenant_id, module_keys=ConcurrentStableList([module_key]), opened_by=opened_by
            )
            row = await self._repo.get(tenant_id, module_key)
        if row is not None:
            await self._repo.set_status(row, status, opened_by=opened_by)
        self._drop_cache(tenant_id)

    async def status(self, tenant_id: int) -> ModuleStatusResponse:
        """取租户模块状态集（内部契约；只列已开通清单中的模块）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ModuleStatusResponse: 状态集。
        """
        rows = await self._repo.list_by_tenant(tenant_id)
        return ModuleStatusResponse(
            enabled=ConcurrentStableList(row.module_key for row in rows if row.status == TENANT_MODULE_ENABLED),
            disabled=ConcurrentStableList(row.module_key for row in rows if row.status == TENANT_MODULE_DISABLED),
            version=len(rows),
        )

    async def validate_optional(self, module_keys: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
        """校验模块可勾选（产品模块 + 目录启用）。

        Args:
            module_keys: 模块清单。

        Returns:
            ConcurrentStableList[str]: 去重后的合法清单。

        Raises:
            TenantModuleUnavailableError: 未注册 / 未启用（82007）。
            ParamError: 含基础能力模块（10001）。
        """
        modules = ConcurrentStableDict({item.module_key: item for item in await self._catalog.modules()})
        validated = ConcurrentStableList[str]()
        for module_key in dict.fromkeys(module_keys):
            item = modules.get(module_key)
            # 目录缺行时仍按基座常量判定：对端旧版本 / 目录裁剪也须维持「基础模块不参与勾选」语义
            if (item is not None and is_tenant_base_module(item)) or (
                item is None and module_key in TENANT_BASE_MODULE_KEYS
            ):
                raise ParamError(f"基础能力模块恒开通、不参与勾选：{module_key}")
            if item is None or item.status != "enabled":
                raise TenantModuleUnavailableError(f"模块未注册或未启用：{module_key}")
            if not self._repo_optional(module_key):
                raise TenantModuleUnavailableError(f"模块不可开通：{module_key}")
            validated.add(module_key)
        return validated

    @staticmethod
    def _repo_optional(module_key: str) -> bool:
        """是否可勾选产品模块。

        Args:
            module_key: 模块标识。

        Returns:
            bool: 可勾选为 True。
        """
        return module_key in TENANT_OPTIONAL_MODULE_KEYS

    def _drop_cache(self, tenant_id: int) -> None:
        """删除模块状态缓存键（跨实例：Redis 域即删）。

        Args:
            tenant_id: 租户主键。
        """
        if self._cache is not None:
            self._cache.delete(tenant_module_cache_key(tenant_id, self._cache))


def _catalog_rows(response: ServiceResponse) -> ConcurrentStableList[CatalogModule]:
    """解析目录快照响应。

    Args:
        response: 服务间调用响应。

    Returns:
        ConcurrentStableList[CatalogModule]: 目录模块。

    Raises:
        ServiceUnavailableError: 非 2xx / 响应非法（10007 / 503）。
    """
    if response.status_code != 200:
        raise ServiceUnavailableError(f"服务目录不可用（HTTP {response.status_code}）")
    payload = response.payload()
    if not isinstance(payload, dict):
        raise ServiceUnavailableError("服务目录返回非法响应")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError("服务目录返回非法响应")
    data = body.get("data")
    if not isinstance(data, list):
        raise ServiceUnavailableError("服务目录返回非法响应")
    rows = ConcurrentStableList[CatalogModule]()
    for item in cast("list[object]", data):
        if not isinstance(item, Mapping):
            raise ServiceUnavailableError("服务目录返回非法响应")
        rows.add(_from_row(ConcurrentStableDict(cast("dict[str, object]", item))))
    return rows


def _from_row(row: ConcurrentStableDict[str, object]) -> CatalogModule:
    """目录响应行 → 目录模块。

    Args:
        row: 响应行。

    Returns:
        CatalogModule: 目录模块。
    """
    return CatalogModule(
        module_key=str(row.get("module_key", "")),
        name=str(row.get("name", "")),
        table_prefix=str(row.get("table_prefix", "")),
        errcode_segment=cast("str | None", row.get("errcode_segment")),
        service_group=str(row.get("service_group", "")),
        status=str(row.get("status", "")),
        tenant_base=row.get("tenant_base") is True,
    )


def _to_row(item: CatalogModule) -> ConcurrentStableDict[str, object]:
    """目录模块 → 缓存行。

    Args:
        item: 目录模块。

    Returns:
        ConcurrentStableDict[str, object]: 缓存行。
    """
    return ConcurrentStableDict(
        {
            "module_key": item.module_key,
            "name": item.name,
            "table_prefix": item.table_prefix,
            "errcode_segment": item.errcode_segment,
            "service_group": item.service_group,
            "status": item.status,
            "tenant_base": item.tenant_base,
        }
    )
