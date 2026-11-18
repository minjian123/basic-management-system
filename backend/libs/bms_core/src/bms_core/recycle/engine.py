"""回收站通用引擎（13_01）：模块计数 / 单表分页 / 详情 / 恢复 / 逐表清理。

设计口径：

- **只认登记表**：未登记或隐藏子表不进列表、不可单独恢复；隐藏子表只随主表级联恢复，
  但同样参与超期清理（避免永久孤儿）。
- **恢复同事务**：主行 + 级联子行 + 字段级审计（ORM 事件）一次 `flush`；唯一冲突预检
  覆盖常见场景，数据库 `IntegrityError` 兜底。
- **冲突判定**：含 `form_key` 的复合唯一不作为冲突依据（页面标识，不是行唯一键）；
  含空值的唯一约束按标准 SQL 语义跳过。
- **清理分批提交**：单表单轮最多 `max_batch_rows`，每批 `SELECT id → DELETE`，避免长事务。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Table, UniqueConstraint, delete, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import RecycleSettings
from bms_core.core.exceptions import (
    ParamError,
    RecycleAlreadyRestoredError,
    RecycleRecordNotFoundError,
    RecycleRestoreConflictError,
    RecycleTableNotSupportedError,
)
from bms_core.core.logging import mask_sensitive
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.base import Base, BaseModel
from bms_core.recycle.registry import recycle_spec_of, visible_recycle_specs
from bms_core.recycle.spec import (
    RecycleCascade,
    RecycleDetail,
    RecycleModule,
    RecyclePageRow,
    RecyclePurgeOutcome,
    RecycleRestoreOutcome,
    RecycleTableInfo,
    RecycleTableSpec,
)

__all__ = ["RecycleEngine", "model_for_table"]

_MAX_CATEGORY_DEPTH = 5
"""自引用级联展开的最大层数（与帮助分类深度上限一致）。"""

_MODEL_CACHE: ConcurrentStableDict[str, type[BaseModel]] = ConcurrentStableDict()
"""表名 → ORM 类缓存（进程内一次；元数据静态）。"""


def model_for_table(table_name: str) -> type[BaseModel] | None:
    """按逻辑表名取 ORM 模型类。

    Args:
        table_name: 逻辑表名。

    Returns:
        type[BaseModel] | None: ORM 类；未找到返回 None。
    """
    cached = _MODEL_CACHE.get(table_name)
    if cached is not None:
        return cached
    for mapper in Base.registry.mappers:
        local_table = cast("Table", mapper.local_table)
        if local_table.name != table_name:
            continue
        model = cast("type[BaseModel]", mapper.class_)
        _MODEL_CACHE[table_name] = model
        return model
    return None


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _format_value(value: object) -> str:
    """把列值格式化为展示字符串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _text(value: object) -> str:
    """把列值转为标题字符串（空值空串）。"""
    return "" if value is None else str(value)


def _optional_int(value: object) -> int | None:
    """把列值转为 int（空值为 None）。"""
    return None if value is None else int(str(value))


def _mapping(row: object) -> ConcurrentStableDict[str, object]:
    """取 SQLAlchemy Row 的列映射。"""
    return ConcurrentStableDict(cast("Any", row)._mapping)


class RecycleEngine(BaseFrameworkObject):
    """回收站通用引擎（请求会话或作业会话均可）。"""

    def __init__(
        self,
        session: DbSession,
        settings: RecycleSettings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话（请求 / 作业）。
            settings: 回收站运行参数。
            clock: 当前时钟（测试可注入）。
        """
        self._session = session
        self._settings = settings
        self._clock = clock or _utc_now

    # ------------------------------ 查询 ------------------------------

    async def modules(self) -> ConcurrentStableFrozenList[RecycleModule]:
        """按模块聚合可见表的删除条数。

        Returns:
            ConcurrentStableFrozenList[RecycleModule]: 模块分组（登记顺序）。
        """
        grouped: ConcurrentStableDict[str, ConcurrentStableList[RecycleTableInfo]] = ConcurrentStableDict()
        labels: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for spec in visible_recycle_specs():
            count = await self._count(spec.table)
            labels.set(spec.module_key, spec.module_label)
            bucket = grouped.get(spec.module_key)
            if bucket is None:
                bucket = ConcurrentStableList[RecycleTableInfo]()
                grouped.set(spec.module_key, bucket)
            bucket.add(RecycleTableInfo(table=spec.table, label=spec.label, deleted_count=count))
        modules: ConcurrentStableList[RecycleModule] = ConcurrentStableList()
        for module_key, tables in grouped.items():
            modules.add(
                RecycleModule(
                    module_key=module_key,
                    module_label=labels[module_key],
                    deleted_count=sum(item.deleted_count for item in tables),
                    tables=ConcurrentStableFrozenList(tables),
                )
            )
        return ConcurrentStableFrozenList(modules)

    async def page(
        self,
        table_name: str,
        *,
        keyword: str | None = None,
        deleted_from: datetime | None = None,
        deleted_to: datetime | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[ConcurrentStableFrozenList[RecyclePageRow], int]:
        """单表分页查询软删除数据。

        Args:
            table_name: 逻辑表名（必须可见）。
            keyword: 关键字（按表规格关键字列模糊匹配）。
            deleted_from: 删除时间下界（含）。
            deleted_to: 删除时间上界（含）。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableFrozenList[RecyclePageRow], int]: 行与总数。

        Raises:
            ParamError: 时间范围起止颠倒（10001）。
            RecycleTableNotSupportedError: 表未纳管 / 隐藏子表（95004）。
        """
        spec = self._visible_spec(table_name)
        table = self._table(spec.table)
        conditions = self._page_conditions(spec, keyword=keyword, deleted_from=deleted_from, deleted_to=deleted_to)
        id_column = table.c["id"]
        deleted_at = table.c["deleted_at"]
        updated_by = table.c["updated_by"]
        columns: ConcurrentStableList[Any] = ConcurrentStableList(
            [id_column, table.c[spec.title_field], deleted_at, updated_by]
        )
        count_statement = select(func.count()).select_from(table).where(*conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        statement = (
            select(*columns)
            .where(*conditions)
            .order_by(deleted_at.desc(), id_column.desc())
            .limit(size)
            .offset((page - 1) * size)
        )
        rows: ConcurrentStableList[RecyclePageRow] = ConcurrentStableList()
        for row in (await self._session.execute(statement)).all():
            values = _mapping(row)
            rows.add(
                RecyclePageRow(
                    table=spec.table,
                    id=int(str(values["id"])),
                    title=_text(values[spec.title_field]),
                    deleted_at=cast("datetime", values["deleted_at"]),
                    deleted_by=_optional_int(values.get(updated_by.name)),
                )
            )
        return ConcurrentStableFrozenList(rows), total

    async def detail(self, table_name: str, row_id: int) -> RecycleDetail:
        """取单行详情（展示列快照）。

        Args:
            table_name: 逻辑表名（必须可见）。
            row_id: 主键。

        Returns:
            RecycleDetail: 详情。

        Raises:
            RecycleRecordNotFoundError: 记录不存在 / 未删除（95001）。
            RecycleTableNotSupportedError: 表未纳管 / 隐藏子表（95004）。
        """
        spec = self._visible_spec(table_name)
        table = self._table(spec.table)
        id_column = table.c["id"]
        statement = select(table).where(id_column == row_id)
        row = (await self._session.execute(statement)).mappings().first()
        if row is None or row["deleted_at"] is None:
            raise RecycleRecordNotFoundError(f"回收站记录不存在或未删除：{spec.table}/{row_id}")
        fields: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for field in spec.visible_fields:
            masked = mask_sensitive(ConcurrentStableDict({field.column: row[field.column]}))
            fields.set(field.label, _format_value(cast("ConcurrentStableDict[str, object]", masked)[field.column]))
        return RecycleDetail(
            table=spec.table,
            id=int(str(row["id"])),
            title=_text(row[spec.title_field]),
            deleted_at=cast("datetime", row["deleted_at"]),
            deleted_by=_optional_int(row["updated_by"]),
            created_at=cast("datetime", row["created_at"]),
            updated_at=cast("datetime", row["updated_at"]),
            fields=ConcurrentStableFrozenDict(fields),
        )

    # ------------------------------ 恢复 ------------------------------

    async def restore(self, table_name: str, row_id: int) -> RecycleRestoreOutcome:
        """恢复单行（主行 + 登记级联子行，同事务）。

        Args:
            table_name: 逻辑表名（必须可见且可恢复）。
            row_id: 主键。

        Returns:
            RecycleRestoreOutcome: 主行标题 / 旧删除时间 / 级联计数。

        Raises:
            RecycleTableNotSupportedError: 表未纳管 / 隐藏子表（95004）。
            RecycleRecordNotFoundError: 记录不存在（95001）。
            RecycleAlreadyRestoredError: 已恢复（95003）。
            RecycleRestoreConflictError: 唯一冲突（95002，含冲突清单）。
        """
        spec = recycle_spec_of(table_name)
        if spec is None or not spec.visible or not spec.restorable:
            raise RecycleTableNotSupportedError(f"该表不在回收站纳管范围：{table_name}")
        model = model_for_table(spec.table)
        if model is None:  # pragma: no cover - 规格校验已在护栏用例覆盖
            raise RecycleTableNotSupportedError(f"该表缺少 ORM 模型：{table_name}")
        entity = await self._session.get(model, row_id)
        if entity is None:
            raise RecycleRecordNotFoundError(f"回收站记录不存在：{spec.table}/{row_id}")
        if entity.deleted_at is None:
            raise RecycleAlreadyRestoredError(f"数据已被其他操作恢复：{spec.table}/{row_id}")
        old_deleted_at = entity.deleted_at
        rows = await self._collect_restore_rows(spec, entity)
        conflicts = await self._unique_conflicts(rows)
        if conflicts:
            first = conflicts[0]
            raise RecycleRestoreConflictError(
                "恢复失败：唯一键已被占用",
                data=ConcurrentStableDict(
                    {
                        "table": first["table"],
                        "fields": first["fields"],
                        "conflict_id": first["conflict_id"],
                        "conflicts": conflicts,
                    }
                ),
            )
        cascaded: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for index, (item_spec, item) in enumerate(rows):
            item.restore()
            if index:
                cascaded.set(item_spec.table, cascaded.get(item_spec.table, 0) + 1)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise RecycleRestoreConflictError("恢复失败：唯一键已被占用（数据库约束拦截）") from exc
        return RecycleRestoreOutcome(
            table=spec.table,
            id=int(str(entity.id)),
            title=_text(getattr(entity, spec.title_field, "")),
            old_deleted_at=old_deleted_at,
            cascaded=ConcurrentStableFrozenDict(cascaded),
        )

    async def _collect_restore_rows(
        self, spec: RecycleTableSpec, entity: BaseModel
    ) -> ConcurrentStableList[tuple[RecycleTableSpec, BaseModel]]:
        """收集主行与级联子行（仍为软删的行）。"""
        rows: ConcurrentStableList[tuple[RecycleTableSpec, BaseModel]] = ConcurrentStableList(((spec, entity),))
        seen: ConcurrentStableSet[str] = ConcurrentStableSet((f"{spec.table}:{int(entity.id)}",))
        for cascade in spec.cascades:
            child_spec = recycle_spec_of(cascade.table)
            if child_spec is None:  # pragma: no cover - 规格校验已在护栏用例覆盖
                continue
            children = await self._cascade_rows(cascade, parent_ids=ConcurrentStableList((int(entity.id),)))
            for child in children:
                key = f"{child_spec.table}:{int(child.id)}"
                if key in seen:
                    continue
                seen.add(key)
                rows.add((child_spec, child))
        return rows

    async def _cascade_rows(
        self, cascade: RecycleCascade, *, parent_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[BaseModel]:
        """按级联关系取仍为软删的子行（递归时逐层展开）。"""
        model = model_for_table(cascade.table)
        table = self._table(cascade.table)
        if model is None:  # pragma: no cover - 规格校验已在护栏用例覆盖
            return ConcurrentStableList()
        frontier = ConcurrentStableList(parent_ids)
        result: ConcurrentStableList[BaseModel] = ConcurrentStableList()
        depth = 0
        while frontier and depth < _MAX_CATEGORY_DEPTH:
            statement = select(model).where(
                table.c[cascade.column].in_([int(item) for item in frontier]),
                table.c["deleted_at"].is_not(None),
            )
            children = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
            if not children:
                break
            result.extend(children)
            if not cascade.recursive:
                break
            frontier = ConcurrentStableList(int(child.id) for child in children)
            depth += 1
        return result

    async def _unique_conflicts(
        self, rows: ConcurrentStableList[tuple[RecycleTableSpec, BaseModel]]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """恢复前唯一冲突预检（含级联子行）。"""
        conflicts: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for spec, entity in rows:
            table = self._table(spec.table)
            for columns in self._unique_columns(table):
                values: ConcurrentStableList[object] = ConcurrentStableList()
                for name in columns:
                    value = self._column_value(entity, table, name)
                    if value is None:
                        values = ConcurrentStableList()
                        break
                    values.add(value)
                if not values:
                    continue
                conditions = [table.c[name] == value for name, value in zip(columns, values, strict=True)]
                statement = (
                    select(table.c["id"])
                    .where(*conditions, table.c["deleted_at"].is_(None), table.c["id"] != entity.id)
                    .limit(1)
                )
                existing = (await self._session.execute(statement)).scalar_one_or_none()
                if existing is None:
                    continue
                conflicts.add(
                    ConcurrentStableDict(
                        {
                            "table": spec.table,
                            "fields": tuple(columns),
                            "conflict_id": str(existing),
                        }
                    )
                )
        return conflicts

    @staticmethod
    def _column_value(entity: BaseModel, table: Table, column_name: str) -> object:
        """取实体在指定物理列上的值（列名与属性名可能不同，如 `code` → `username`）。"""
        mapper = inspect(entity).mapper
        prop = mapper.get_property_by_column(table.c[column_name])
        return getattr(entity, prop.key)

    @staticmethod
    def _unique_columns(table: Table) -> ConcurrentStableSet[ConcurrentStableFrozenList[str]]:
        """取参与恢复冲突判定的唯一列组合（排除 form_key 与 deleted_at）。"""
        result: ConcurrentStableSet[ConcurrentStableFrozenList[str]] = ConcurrentStableSet()
        for constraint in table.constraints:
            if not isinstance(constraint, UniqueConstraint):
                continue
            columns = ConcurrentStableFrozenList(
                column.name for column in constraint.columns if column.name != "deleted_at"
            )
            if columns and "form_key" not in columns:
                result.add(columns)
        for index in table.indexes:
            if not index.unique:
                continue
            columns = ConcurrentStableFrozenList(column.name for column in index.columns if column.name != "deleted_at")
            if columns and "form_key" not in columns:
                result.add(columns)
        return result

    # ------------------------------ 清理 ------------------------------

    async def purge_table(
        self,
        table_name: str,
        *,
        cutoff: datetime | None = None,
        batch_size: int | None = None,
        max_rows: int | None = None,
    ) -> RecyclePurgeOutcome:
        """分批物理删除单表超期软删除数据。

        Args:
            table_name: 逻辑表名（含隐藏子表）。
            cutoff: 截止时刻（默认当前时刻 − 保留天数）。
            batch_size: 单批条数（默认 `[recycle].batch_size`）。
            max_rows: 单轮上限（默认 `[recycle].max_batch_rows`）。

        Returns:
            RecyclePurgeOutcome: 删除条数与批次数。
        """
        spec = recycle_spec_of(table_name)
        if spec is None:
            raise RecycleTableNotSupportedError(f"该表不在回收站纳管范围：{table_name}")
        table = self._table(spec.table)
        id_column = table.c["id"]
        threshold = cutoff if cutoff is not None else self._clock() - timedelta(days=self._settings.retention_days)
        limit = batch_size if batch_size is not None else self._settings.batch_size
        cap = max_rows if max_rows is not None else self._settings.max_batch_rows
        total = 0
        batches = 0
        while total < cap:
            statement = (
                select(id_column)
                .where(table.c["deleted_at"].is_not(None), table.c["deleted_at"] < threshold)
                .order_by(id_column)
                .limit(limit)
            )
            ids = ConcurrentStableList(int(str(row[0])) for row in (await self._session.execute(statement)).all())
            if not ids:
                break
            await self._session.execute(delete(table).where(id_column.in_(list(ids))))
            await self._session.commit()
            total += len(ids)
            batches += 1
            if len(ids) < limit:
                break
        return RecyclePurgeOutcome(table=spec.table, deleted_count=total, batches=batches)

    # ------------------------------ 内部 ------------------------------

    async def _count(self, table_name: str) -> int:
        """统计单表软删除条数。"""
        table = self._table(table_name)
        statement = select(func.count()).select_from(table).where(table.c["deleted_at"].is_not(None))
        return int((await self._session.execute(statement)).scalar_one())

    def _page_conditions(
        self,
        spec: RecycleTableSpec,
        *,
        keyword: str | None,
        deleted_from: datetime | None,
        deleted_to: datetime | None,
    ) -> ConcurrentStableList[Any]:
        """构造分页过滤条件。"""
        if deleted_from is not None and deleted_to is not None and deleted_from > deleted_to:
            raise ParamError("删除时间范围起止颠倒")
        table = self._table(spec.table)
        conditions: ConcurrentStableList[Any] = ConcurrentStableList((table.c["deleted_at"].is_not(None),))
        if deleted_from is not None:
            conditions.add(table.c["deleted_at"] >= deleted_from)
        if deleted_to is not None:
            conditions.add(table.c["deleted_at"] <= deleted_to)
        if keyword and spec.keyword_fields:
            pattern = f"%{_escape_like(keyword)}%"
            matches = [table.c[column].ilike(pattern, escape="\\") for column in spec.keyword_fields]
            conditions.add(or_(*matches))
        return conditions

    def _visible_spec(self, table_name: str) -> RecycleTableSpec:
        """取可见表规格（否则 95004）。"""
        spec = recycle_spec_of(table_name)
        if spec is None or not spec.visible:
            raise RecycleTableNotSupportedError(f"该表不在回收站纳管范围：{table_name}")
        return spec

    @staticmethod
    def _table(table_name: str) -> Table:
        """取 ORM 表对象（规格校验保证存在）。"""
        return Base.metadata.tables[table_name]


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符（`%` / `_` / `\\`）。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
