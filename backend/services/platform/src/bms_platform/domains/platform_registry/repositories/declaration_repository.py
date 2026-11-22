"""产品声明注册表仓储（07B `02_06`）：十类声明的读取与落库。

- 归属：读写平台服务库 `bms_platform`（`sys_module` / `sys_product` + 八张声明表）；
- 写入口**唯一**：产品注册通道（`DeclarationRegistryService`）；会话随构造注入，事务边界由调用方负责；
- 退役不删行：本次未声明的记录置 `status = retired`（历史保留，便于回滚与对账）；
- 内容指纹：每次写入按要素重算 `content_hash`，供「内容未变不写」判定。
"""

from typing import Any, cast

from sqlalchemy import ColumnElement, select

from bms_core.boundary.domains import DomainEntry
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import CatalogError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.datasource.registry import DataSourceRecord
from bms_core.models.platform.catalog import SysModule, SysProduct
from bms_core.models.platform.declaration import (
    SysCollaboration,
    SysCollaborationUsage,
    SysDataSource,
    SysDomain,
    SysErrcode,
    SysProductRoute,
    SysScopeResourceType,
    SysSeed,
)
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    DeclarationPlan,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
)
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.resource_scope import ScopeResourceTypeRecord
from bms_core.services.module_registry import (
    CollaborationRecord,
    CollaborationStatus,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
)

__all__ = ["DeclarationRepository"]

_RETIRED = "retired"
"""退役状态值（本次全量未声明）。"""

_NEW_MODELS: ConcurrentStableDict[str, type[Any]] = ConcurrentStableDict(
    {
        "product_routes": SysProductRoute,
        "data_sources": SysDataSource,
        "collaborations": SysCollaboration,
        "usages": SysCollaborationUsage,
        "seeds": SysSeed,
        "errcodes": SysErrcode,
        "domains": SysDomain,
        "resource_types": SysScopeResourceType,
    }
)
"""八张声明表对应的 ORM 模型（服务行 / 产品档案走既有 `sys_module` / `sys_product`）。

07B `04_02` 重开新增 `domains`（第九类：业务域声明）；07D `01_01` 新增 `resource_types`
（第十类：作用域资源类型声明）。
"""


class _FieldRecorder(BaseFrameworkObject):
    """属性写入录制器：把 `_assign` 的逐字段赋值录成「列 → 值」映射。

    为什么需要：落库改走原子语句后，需要的是列值而不是 ORM 对象；若另写一份「每类声明有哪些
    字段」的清单，就会和 `_assign` 各改各的、迟早漂移。录制器让 `_assign` 继续做**唯一事实源**：
    它赋了哪些属性，原子语句就写哪些列（未赋值的列，如运营态 `admin_status`，一律不写）。

    `declaration_version` 只被读取、不被赋值（`_assign` 用它 +1），故初始值给 0 供其计算。
    """

    def __init__(self, initial: ConcurrentStableDict[str, object]) -> None:
        """初始化。

        Args:
            initial: 供 `_assign` 读取的只读初值（不计入录制结果）。
        """
        object.__setattr__(self, "_values", ConcurrentStableDict(initial))
        object.__setattr__(self, "_touched", ConcurrentStableSet())

    def __getattr__(self, name: str) -> object:
        """读取初值（`_assign` 只读 `declaration_version`）。

        Args:
            name: 属性名。

        Returns:
            object: 初值；未给出为 None。
        """
        return object.__getattribute__(self, "_values").get(name)

    def __setattr__(self, name: str, value: object) -> None:
        """记录一次赋值。

        Args:
            name: 属性名。
            value: 属性值。
        """
        object.__getattribute__(self, "_values").set(name, value)
        object.__getattribute__(self, "_touched").add(name)

    @property
    def values(self) -> ConcurrentStableDict[str, object]:
        """录制到的列值（只含 `_assign` 赋过值的列）。

        Returns:
            ConcurrentStableDict[str, object]: 列名 → 值。
        """
        values = object.__getattribute__(self, "_values")
        touched = object.__getattribute__(self, "_touched")
        return ConcurrentStableDict({name: values.get(name) for name in touched})


class DeclarationRepository(BaseDbRepository[Any]):
    """声明注册仓储：现状读取 + 对账结果落库。"""

    model = SysCollaboration

    async def load_snapshot(self) -> RegistrySnapshot:
        """读取注册表现状（八类记录 + 指纹 + 行主键 + 退役标记）。

        Returns:
            RegistrySnapshot: 注册表现状。
        """
        records: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
        hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        ids: ConcurrentStableDict[str, ConcurrentStableDict[str, int]] = ConcurrentStableDict()
        retired: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
        owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for kind in DECLARATION_KINDS:
            kind_records: ConcurrentStableList[Any] = ConcurrentStableList()
            kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            kind_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            kind_retired: ConcurrentStableSet[str] = ConcurrentStableSet()
            kind_owners: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            for row in await self._rows(kind):
                record = self._to_record(kind, row)
                key = declaration_key(kind, record)
                kind_records.add(record)
                kind_hashes.set(key, content_hash_of(kind, record))
                kind_ids.set(key, int(row.id))
                kind_owners.set(key, self._owner_of_row(kind, row))
                if str(row.status) == _RETIRED:
                    kind_retired.add(key)
            records.set(kind, kind_records)
            hashes.set(kind, kind_hashes)
            ids.set(kind, kind_ids)
            owners.set(kind, kind_owners)
            retired.set(kind, kind_retired)
        return RegistrySnapshot(records=records, hashes=hashes, ids=ids, retired=retired, owners=owners)

    @staticmethod
    def _owner_of_row(kind: str, row: Any) -> str:
        """取行归属的声明方（共享表里 `product_key` 为空的平台行归 `platform`）。

        Args:
            kind: 声明类别。
            row: ORM 行。

        Returns:
            str: 声明方产品键（空串表示无法判定）。
        """
        owner = getattr(row, "product_key", None)
        if owner:
            return str(owner)
        return "platform" if kind in ("products", "services") else ""

    async def apply(self, plan: DeclarationPlan, *, product_key: str) -> None:
        """把对账结果落库（新增 / 覆盖 / 退役）。

        全部走**原子语句**：新增是 `INSERT ... WHERE NOT EXISTS`（同键已存在则跳过），覆盖与退役
        是 Core `UPDATE`（不带「读到的版本」谓词）。为什么不用 ORM 写：注册是「读现状 → 对账 →
        落库」跨多次操作，两个进程同时注册时，后写方的 ORM `UPDATE` 会因版本已变而
        `StaleDataError`（0 行匹配），新增则可能各插一行。原子语句让数据库自己判「该不该写」，
        并发注册收敛到同一份注册表。

        Args:
            plan: 对账计划。
            product_key: 声明方产品键（新增行写入归属）。
        """
        for kind in DECLARATION_KINDS:
            target = self._model_of(kind)
            for record in plan.created.get(kind) or ():
                key = declaration_key(kind, record)
                await self.insert_if_absent(
                    self._values_of(kind, record, product_key=product_key, creating=True),
                    match=self._key_match(kind, key),
                    model=target,
                )
            for key in plan.retired.get(kind) or ():
                await self.update_where(
                    self._key_match(kind, key),
                    values=ConcurrentStableDict({"status": _RETIRED}),
                    model=target,
                )
            for record in plan.updated.get(kind) or ():
                key = declaration_key(kind, record)
                values = self._values_of(kind, record, product_key=product_key, creating=False)
                if kind == "resource_types":
                    # 声明版本按内容变更派生：由数据库侧自增，避免并发注册互相覆盖成同一个值
                    values.set("declaration_version", target.declaration_version + 1)
                changed = await self.update_where(self._key_match(kind, key), values=values, model=target)
                if changed == 0:
                    # 计划里是「覆盖」，但目标行已被并发软删 / 从未落库：退回原子新增（语义同原实现）
                    await self.insert_if_absent(
                        self._values_of(kind, record, product_key=product_key, creating=True),
                        match=self._key_match(kind, key),
                        model=target,
                    )
        # 原子语句绕过了 ORM 身份映射：会话里已加载的行会停在旧值。统一过期，后续读按库内真值
        # 重新装载（本方法之后仍持有 ORM 行的调用方，读属性前须先重新查询 / `refresh`）。
        self._session.expire_all()

    def _values_of(
        self, kind: str, record: object, *, product_key: str, creating: bool
    ) -> ConcurrentStableDict[str, object]:
        """把声明记录录成「列 → 值」（复用 `_assign`，避免两份字段清单漂移）。

        Args:
            kind: 声明类别。
            record: 声明记录。
            product_key: 声明方产品键。
            creating: 是否新增（补表单判别列等新建期字段）。

        Returns:
            ConcurrentStableDict[str, object]: 待写入的列值（ORM 属性名）。
        """
        # 覆盖时 `_assign` 会读 `declaration_version` 再 +1；先给 0 让录制器能算，
        # 真正的版本自增由 `apply` 用 SQL 表达式覆盖（并发下不会写成同一个字面值）。
        recorder = _FieldRecorder(ConcurrentStableDict({"declaration_version": 0}))
        self._assign(kind, recorder, record, product_key=product_key, creating=creating)
        return recorder.values

    def _key_match(self, kind: str, key: str) -> ConcurrentStableList[ColumnElement[bool]]:
        """按声明业务键构造原子写定位条件。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 定位条件（未软删过滤由基座方法追加）。
        """
        model = self._model_of(kind)
        column = getattr(model, self._column_name(kind))
        return ConcurrentStableList((column == self._cast_key(kind, key),))

    async def _rows(self, kind: str) -> ConcurrentStableList[Any]:
        """读某类声明的全部未软删行。

        Args:
            kind: 声明类别。

        Returns:
            ConcurrentStableList[Any]: ORM 行（插入序）。
        """
        model = self._model_of(kind)
        # `populate_existing`：本轮写入走 Core 语句，会话身份映射里可能还留着旧值；
        # 投影必须按库内真值重建，否则会「写成功、视图还是旧的」。
        statement = (
            select(model).where(model.deleted_at.is_(None)).order_by(model.id).execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return ConcurrentStableList(result.scalars().all())

    def _model_of(self, kind: str) -> Any:
        """取某类声明的 ORM 模型。

        Args:
            kind: 声明类别。

        Returns:
            Any: 模型类。
        """
        if kind == "products":
            return SysProduct
        if kind == "services":
            return SysModule
        return _NEW_MODELS.get(kind)

    @staticmethod
    def _column_name(kind: str) -> str:
        """取业务键对应的模型属性名。

        Args:
            kind: 声明类别。

        Returns:
            str: 属性名。
        """
        return {
            "products": "product_key",
            "services": "module_key",
            "product_routes": "domain",
            "data_sources": "data_source_key",
            "collaborations": "name",
            "seeds": "name",
            "errcodes": "code",
            "usages": "capability_name",
            "domains": "domain_key",
            "resource_types": "resource_type_key",
        }[kind]

    @staticmethod
    def _cast_key(kind: str, key: str) -> object:
        """业务键类型适配（错误码为整数）。

        Args:
            kind: 声明类别。
            key: 业务键（字符串）。

        Returns:
            object: 查询用键值。
        """
        return int(key) if kind == "errcodes" else key

    def _assign(self, kind: str, row: Any, record: object, *, product_key: str, creating: bool = False) -> None:
        """把声明要素写进模型对象（新增与覆盖共用）。

        Args:
            kind: 声明类别。
            row: 模型对象。
            record: 声明记录。
            product_key: 声明方产品键。
            creating: 是否新建（补表单判别列等新建期字段）。
        """
        data = cast("Any", record)
        if kind == "products":
            if creating:
                row.form_key = "product"
            row.product_key = data.product_key
            row.name = data.name
            row.frontend_package_source = data.frontend_package_source
            row.status = data.status
            return
        if kind == "services":
            if creating:
                row.form_key = "module"
            for name in (
                "module_key",
                "service_key",
                "name",
                "table_prefix",
                "business_code",
                "errcode_segment",
                "event_domain",
                "service_group",
                "build_batch",
                "service_version",
                "contract_version",
                "product_key",
                "status",
                "tenant_base",
            ):
                setattr(row, name, getattr(data, name))
            return
        row.product_key = product_key
        if kind == "product_routes":
            row.domain = data.domain
            row.service_key = data.service_key
            row.description = data.description
            row.status = "enabled"
        elif kind == "data_sources":
            row.data_source_key = data.data_source_key
            row.name = data.name
            row.kind = data.kind
            row.data_source = data.data_source
            row.origin = data.origin
            row.path = data.path
            row.allowlist = _json_list(data.allowlist)
            row.cascade = data.cascade
            row.strategies = _json_list(data.strategies)
            row.quota_dimensions = _json_list(data.quota_dimensions)
            row.quota_unit = data.quota_unit
            row.quota_period = data.quota_period
            row.quota_soft_limit = data.quota_soft_limit
            row.quota_hard_limit = data.quota_hard_limit
            row.status = data.status
        elif kind == "collaborations":
            row.name = data.name
            row.domain = data.domain
            row.kind = data.kind
            row.contract_version = data.contract_version
            row.path = data.path
            row.branch_id = data.branch_id
            row.branch_op = data.branch_op
            row.data_source_key = data.data_source_key
            row.permission_codes = _json_list(data.permission_codes)
            row.frontend_prefix = data.frontend_prefix
            row.default_consumers = _json_list(data.default_consumers)
            row.replacement = data.replacement
            row.status = data.status
        elif kind == "usages":
            row.capability_name = data.name
            row.degrade = data.degrade
            row.reason = data.reason
            row.status = "enabled"
        elif kind == "seeds":
            row.name = data.name
            row.service = data.service
            row.db_key = data.db_key
            row.module = data.module
            row.entry = data.entry
            row.op = data.op or data.name
            row.after = _json_list(data.after)
            row.description = data.description
            row.tables = _json_mapping(data.tables)
            row.status = "enabled"
        elif kind == "errcodes":
            row.code = data.code
            row.segment = data.segment
            row.domain = data.domain
            row.http_status = data.http_status
            row.message_key = data.message_key
            row.severity = data.severity
            row.description = data.description
            row.maps_from = _json_int_list(data.maps_from)
            row.status = "enabled"
        elif kind == "domains":
            row.domain_key = data.domain_key
            row.service_key = data.service_key
            row.status = data.status
            row.paths = _json_list(data.paths)
            row.public_api = _json_list(data.public_api)
        elif kind == "resource_types":
            row.resource_type_key = data.resource_type_key
            row.name = data.name
            row.name_pattern = data.name_pattern
            row.max_length = data.max_length
            row.retention_days = data.retention_days
            row.removal_policy = data.removal_policy
            row.status = data.status
            # 声明版本按内容变更派生（新建 1，覆盖 +1）；运营态列（admin_status / disabled_*）不在此写
            row.declaration_version = 1 if creating else int(row.declaration_version) + 1
        row.content_hash = content_hash_of(kind, record)

    def _to_record(self, kind: str, row: object) -> object:
        """模型对象 → 声明记录（读回视图 / 指纹复算用）。

        Args:
            kind: 声明类别。
            row: ORM 行。

        Returns:
            object: 声明记录（各记录值对象）。
        """
        data = cast("Any", row)
        if kind == "products":
            return ProductRecord(
                product_key=str(data.product_key),
                name=str(data.name),
                frontend_package_source=data.frontend_package_source,
                status=str(data.status),
            )
        if kind == "services":
            return ModuleRecord.from_row(data)
        if kind == "product_routes":
            return ProductRouteRecord(
                product_key=str(data.product_key),
                domain=str(data.domain),
                service_key=str(data.service_key),
                description=str(data.description or ""),
            )
        if kind == "data_sources":
            return DataSourceRecord(
                data_source_key=str(data.data_source_key),
                name=str(data.name),
                data_source=str(data.data_source),
                kind=str(data.kind),
                origin=str(data.origin),
                product_key=str(data.product_key),
                path=data.path,
                allowlist=_frozen_list(data.allowlist),
                cascade=bool(data.cascade),
                strategies=_frozen_list(data.strategies),
                quota_dimensions=_frozen_list(data.quota_dimensions),
                quota_unit=data.quota_unit,
                quota_period=data.quota_period,
                quota_soft_limit=data.quota_soft_limit,
                quota_hard_limit=data.quota_hard_limit,
                status=str(data.status),
            )
        if kind == "collaborations":
            return CollaborationRecord(
                name=str(data.name),
                domain=str(data.domain),
                kind=str(data.kind),
                contract_version=str(data.contract_version),
                path=data.path,
                product_key=str(data.product_key),
                branch_id=data.branch_id,
                branch_op=data.branch_op,
                data_source_key=data.data_source_key,
                permission_codes=_frozen_list(data.permission_codes),
                frontend_prefix=data.frontend_prefix,
                default_consumers=_frozen_list(data.default_consumers),
                status=str(data.status),
                replacement=data.replacement,
            )
        if kind == "usages":
            from bms_core.collaboration.usage import CapabilityUsage

            return CapabilityUsage(
                name=str(data.capability_name),
                degrade=str(data.degrade),
                reason=str(data.reason or ""),
            )
        if kind == "seeds":
            return SeedRecord(
                name=str(data.name),
                module=str(data.module),
                entry=str(data.entry),
                service=str(data.service),
                db_key=str(data.db_key),
                op=str(data.op or ""),
                tables=_frozen_mapping(data.tables),
                after=_frozen_list(data.after),
                description=str(data.description or ""),
                status=_status_of(data.status),
                source=str(data.product_key or ""),
            )
        if kind == "domains":
            return DomainEntry(
                domain_key=str(data.domain_key),
                service_key=str(data.service_key),
                status=_status_of(data.status),
                paths=_frozen_list(data.paths),
                public_api=_frozen_list(data.public_api),
            )
        if kind == "resource_types":
            return ScopeResourceTypeRecord.from_row(data)
        return ErrorCodeRecord(
            code=int(data.code),
            domain=str(data.domain),
            http_status=int(data.http_status),
            message_key=str(data.message_key),
            severity=str(data.severity),
            description=str(data.description or ""),
            product_key=str(data.product_key),
            segment=str(data.segment),
            status=str(data.status),
            maps_from=_frozen_int_list(data.maps_from),
        )


def _status_of(raw: object) -> str:
    """把库内状态读回记录状态（`retired` 不在枚举内，按原值保留）。

    Args:
        raw: 库内状态值。

    Returns:
        str: 状态值（`StrEnum` 与字符串同值比较，不影响指纹与对账）。
    """
    text = str(raw or "enabled")
    try:
        return str(CollaborationStatus(text))
    except ValueError:
        return text


def _json_list(values: object) -> str:
    """把插入序集合写成 JSON 数组文本。

    Args:
        values: 集合值（`ConcurrentStableFrozenList` 等）。

    Returns:
        str: JSON 文本（空集为 `[]`）。
    """
    import json

    return json.dumps([str(item) for item in cast("Any", values)], ensure_ascii=False)


def _json_int_list(values: object) -> str | None:
    """把整数集合写成 JSON 数组文本（空集写 `None`，避免无意义 `[]` 占位）。

    Args:
        values: 整数集合（`ConcurrentStableFrozenList[int]` 等）。

    Returns:
        str | None: JSON 文本；空集为 `None`。
    """
    import json

    items = [int(item) for item in cast("Any", values)]
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)


def _frozen_int_list(raw: object) -> Any:
    """把 JSON 数组文本读回整数冻结集合。

    Args:
        raw: JSON 数组文本（None 视为空）。

    Returns:
        Any: `ConcurrentStableFrozenList[int]`。
    """
    import json

    from bms_core.core.concurrent import ConcurrentStableFrozenList

    if not raw:
        return ConcurrentStableFrozenList()
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"注册表 JSON 字段损坏（应为整数数组）：{raw!r}") from exc
    return ConcurrentStableFrozenList(int(str(item)) for item in cast("list[object]", parsed))


def _json_mapping(values: object) -> str:
    """把映射写成 JSON 对象文本。

    Args:
        values: 映射值。

    Returns:
        str: JSON 文本（空为 `{}`）。
    """
    import json

    return json.dumps({str(key): str(value) for key, value in cast("Any", values).items()}, ensure_ascii=False)


def _frozen_mapping(raw: object) -> Any:
    """把 JSON 对象文本读回插入序冻结映射。

    Args:
        raw: JSON 对象文本（None 视为空）。

    Returns:
        Any: `ConcurrentStableFrozenDict[str, str]`。
    """
    import json

    from bms_core.core.concurrent import ConcurrentStableFrozenDict

    empty: Any = ConcurrentStableFrozenDict[str, str]()
    if not raw:
        return empty
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        # 注册表数据损坏属内部错误：不静默退化为空（否则视图与库不一致却无人知晓）
        raise CatalogError(f"注册表 JSON 字段损坏（应为对象）：{raw!r}") from exc
    return ConcurrentStableFrozenDict(
        {str(key): str(value) for key, value in cast("dict[str, object]", parsed).items()}
    )


def _frozen_list(raw: object) -> Any:
    """把 JSON 文本读回插入序冻结集合。

    Args:
        raw: JSON 数组文本（None 视为空）。

    Returns:
        Any: `ConcurrentStableFrozenList[str]`。
    """
    import json

    from bms_core.core.concurrent import ConcurrentStableFrozenList

    if not raw:
        return ConcurrentStableFrozenList()
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        # 同上：注册表数据损坏即抛，不静默退化为空
        raise CatalogError(f"注册表 JSON 字段损坏（应为数组）：{raw!r}") from exc
    return ConcurrentStableFrozenList(str(item) for item in cast("list[object]", parsed))
