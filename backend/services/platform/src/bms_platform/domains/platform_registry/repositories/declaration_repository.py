"""产品声明注册表仓储（07B `02_06`）：八类声明的读取与落库。

- 归属：读写平台服务库 `bms_platform`（`sys_module` / `sys_product` + 六张声明表）；
- 写入口**唯一**：产品注册通道（`DeclarationRegistryService`）；会话随构造注入，事务边界由调用方负责；
- 退役不删行：本次未声明的记录置 `status = retired`（历史保留，便于回滚与对账）；
- 内容指纹：每次写入按要素重算 `content_hash`，供「内容未变不写」判定。
"""

from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.datasource.registry import DataSourceRecord
from bms_core.models.platform.catalog import SysModule, SysProduct
from bms_core.models.platform.declaration import (
    SysCollaboration,
    SysCollaborationUsage,
    SysDataSource,
    SysErrcode,
    SysProductRoute,
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
    }
)
"""六张声明表对应的 ORM 模型（服务行 / 产品档案走既有 `sys_module` / `sys_product`）。"""


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
        for kind in DECLARATION_KINDS:
            kind_records: ConcurrentStableList[Any] = ConcurrentStableList()
            kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            kind_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            kind_retired: ConcurrentStableSet[str] = ConcurrentStableSet()
            for row in await self._rows(kind):
                record = self._to_record(kind, row)
                key = declaration_key(kind, record)
                kind_records.add(record)
                kind_hashes.set(key, content_hash_of(kind, record))
                kind_ids.set(key, int(cast("Any", row).id))
                if str(cast("Any", row).status) == _RETIRED:
                    kind_retired.add(key)
            records.set(kind, kind_records)
            hashes.set(kind, kind_hashes)
            ids.set(kind, kind_ids)
            retired.set(kind, kind_retired)
        return RegistrySnapshot(records=records, hashes=hashes, ids=ids, retired=retired)

    async def apply(self, plan: DeclarationPlan, *, product_key: str) -> None:
        """把对账结果落库（新增 / 覆盖 / 退役）。

        Args:
            plan: 对账计划。
            product_key: 声明方产品键（新增行写入归属）。
        """
        session = self._session
        for kind in DECLARATION_KINDS:
            for record in plan.created.get(kind) or ():
                session.add(self._to_model(kind, record, product_key=product_key))
            for key in plan.retired.get(kind) or ():
                row = await self._row_by_key(kind, key)
                if row is not None:
                    cast("Any", row).status = _RETIRED
            for record in plan.updated.get(kind) or ():
                row = await self._row_by_key(kind, declaration_key(kind, record))
                if row is None:
                    session.add(self._to_model(kind, record, product_key=product_key))
                    continue
                self._assign(kind, cast("Any", row), record, product_key=product_key)
        await session.flush()

    async def _rows(self, kind: str) -> ConcurrentStableList[Any]:
        """读某类声明的全部未软删行。

        Args:
            kind: 声明类别。

        Returns:
            ConcurrentStableList[Any]: ORM 行（插入序）。
        """
        model = self._model_of(kind)
        result = await self._session.execute(select(model).where(model.deleted_at.is_(None)).order_by(model.id))
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

    async def _row_by_key(self, kind: str, key: str) -> Any:
        """按业务键取单行（未软删）。

        Args:
            kind: 声明类别。
            key: 业务键。

        Returns:
            Any: ORM 行；不存在为 None。
        """
        model = self._model_of(kind)
        column = getattr(model, self._column_name(kind))
        statement = select(model).where(column == self._cast_key(kind, key), model.deleted_at.is_(None))
        return (await self._session.execute(statement)).scalars().first()

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

    def _to_model(self, kind: str, record: object, *, product_key: str) -> Any:
        """声明记录 → 待插入模型对象。

        Args:
            kind: 声明类别。
            record: 声明记录。
            product_key: 声明方产品键。

        Returns:
            Any: 模型对象。
        """
        model = self._model_of(kind)
        row = model()
        self._assign(kind, cast("Any", row), record, product_key=product_key, creating=True)
        return row

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
            row.status = "enabled"
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
                status=CollaborationStatus(str(data.status)),
                source=str(data.product_key or ""),
            )
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
        )


def _json_list(values: object) -> str:
    """把插入序集合写成 JSON 数组文本。

    Args:
        values: 集合值（`ConcurrentStableFrozenList` 等）。

    Returns:
        str: JSON 文本（空集为 `[]`）。
    """
    import json

    return json.dumps([str(item) for item in cast("Any", values)], ensure_ascii=False)


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

    if not raw:
        return ConcurrentStableFrozenDict()
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return ConcurrentStableFrozenDict()
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
    except json.JSONDecodeError:
        return ConcurrentStableFrozenList()
    return ConcurrentStableFrozenList(str(item) for item in cast("list[object]", parsed))
