"""租户自建字段服务：登记 → 动态 DDL → 生效 / 主失败可重试 → 停用不删列（10_01）。

**生命周期**（与《架构设计 · 表单定制》§4「一致性」一致）：

1. 登记：白名单校验（`field_key` / 类型 / 选项集）→ 冲突判定 → 元数据 `ddl_status=pending` **提交**；
2. 建列：DDL 执行器（单租户串行锁 + 参数化编译）→ 成功 `active`、失败 `failed`（**只影响本字段**）；
3. 重试：`retry` 复用同一元数据与列名，重走建列；
4. 停用：`status=disabled`，**不生成 DROP COLUMN**（合规销毁走归档链路 14_01）；
5. 重建复用：同 `form_code` 下同 `column_name` 的停用字段可恢复，不重复加列。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    FormFieldKeyConflictError,
    FormFieldTypeInvalidError,
    FormNotCustomizableError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.fieldtype.mapping import EXT_FIELD_TYPE_KEYS, is_ext_field_type
from bms_core.formdesign.identifier import derive_column_name, validate_field_key, validate_table_name
from bms_core.lock.base import BaseDistributedLock
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    DDL_STATUS_FAILED,
    DDL_STATUS_PENDING,
    EXT_OPTION_TYPES,
    SysFieldExt,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_platform.domains.form_design.ports import FormMetadataPort, OptionSetPort
from bms_platform.domains.form_design.repositories.field_ext_i18n import FieldExtI18nRepository
from bms_platform.domains.form_design.repositories.layout import FieldExtRepository

if TYPE_CHECKING:
    from bms_platform.domains.form_design.services.ddl import FormDdlExecutor

__all__ = ["FIELD_OPTION_REQUIRED", "ExtFieldService"]

_LOGGER = get_logger("bms.form_design.field")

FIELD_OPTION_REQUIRED = EXT_OPTION_TYPES
"""需要选项集的自建字段类型。"""

EXT_FIELD_EVENT = "sys.form.updated"
"""表单变更事件（与布局共用，`changed_type=ext_field`）。"""


class ExtFieldService(BaseFrameworkObject):
    """租户自建字段服务（元数据 + DDL 编排）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        fields: FieldExtRepository,
        i18n: FieldExtI18nRepository,
        metadata: FormMetadataPort,
        option_sets: OptionSetPort,
        outbox: BaseOutboxStore,
        lock: BaseDistributedLock,
        ddl_executor: FormDdlExecutor,
        tenant: str | None,
        invalidate: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 请求级会话。
            uow: 请求级工作单元。
            fields: 自建字段仓储。
            i18n: 自建字段多语言仓储。
            metadata: 平台库表单元数据读面（解析物理表名）。
            option_sets: 选项集读面（标识登记校验）。
            outbox: 事务性发件箱。
            lock: 分布式锁（DDL 单租户串行）。
            ddl_executor: DDL 执行器（`FormDdlExecutor`；类型仅在类型检查期 import，运行期按注入实例使用）。
            tenant: 租户标识。
            invalidate: 缓存失效回调（`Callable[[str], Awaitable[None]]`；None 表示不失效）。
        """
        self._session = session
        self._uow = uow
        self._fields = fields
        self._i18n = i18n
        self._metadata = metadata
        self._option_sets = option_sets
        self._outbox = outbox
        self._lock = lock
        self._ddl = ddl_executor
        self._tenant = tenant
        self._invalidate = invalidate

    # ------------------------------------------------------------------ 读取

    async def list_fields(self, form_code: str) -> ConcurrentStableList[SysFieldExt]:
        """列示该表单的自建字段（含各 `ddl_status`）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            ConcurrentStableList[SysFieldExt]: 自建字段行（`sort` 升序）。

        Raises:
            FormNotCustomizableError: 业务码不存在或不可定制（40401）。
        """
        if await self._metadata.load(form_code) is None:
            raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
        return await self._fields.list_by_form(form_code)

    async def names(
        self,
        rows: ConcurrentStableList[SysFieldExt],
        *,
        locales: ConcurrentStableList[str],
    ) -> ConcurrentStableDict[int, str]:
        """批量取自建字段名（按语言优先级）。

        Args:
            rows: 自建字段行。
            locales: 语言优先级序。

        Returns:
            ConcurrentStableDict[int, str]: 字段主键 → 名称。
        """
        if len(rows) == 0:  # pragma: no cover - 调用方按行逐个取（至少一行），空清单不走本方法
            return ConcurrentStableDict()
        return await self._i18n.load_names(ConcurrentStableList(row.id for row in rows), locales=locales)

    # ------------------------------------------------------------------ 写入

    async def create_field(
        self,
        *,
        form_code: str,
        field_key: str,
        name: str,
        field_type: str,
        option_set_key: str | None,
        sort: int = 0,
    ) -> SysFieldExt:
        """登记自建字段并触发动态 DDL。

        Args:
            form_code: 表单标识（业务码）。
            field_key: 字段键（归一 + 白名单校验）。
            name: 字段名（默认文案）。
            field_type: 字段类型（白名单）。
            option_set_key: 选项集标识（枚举类型必填）。
            sort: 同表单内排序。

        Returns:
            SysFieldExt: 写入并建列后的行（`ddl_status` 为 `active` 或 `failed`）。

        Raises:
            ParamError: 字段键非法（10001）。
            FormNotCustomizableError: 业务码不存在 / 不可定制 / 物理表不可解析（40401）。
            FormFieldKeyConflictError: 字段键冲突（40402）。
            FormFieldTypeInvalidError: 类型不在白名单或选项集缺失 / 未注册（40404）。
        """
        key = validate_field_key(field_key)
        if not is_ext_field_type(field_type):
            allowed = ", ".join(EXT_FIELD_TYPE_KEYS)
            raise FormFieldTypeInvalidError(f"字段类型不在白名单：{field_type}（允许：{allowed}）")
        if field_type in FIELD_OPTION_REQUIRED:
            if option_set_key is None or option_set_key.strip() == "":
                raise FormFieldTypeInvalidError(f"枚举字段必须指定选项集标识：{field_type}")
            if not self._option_sets.is_registered(option_set_key):
                raise FormFieldTypeInvalidError(f"选项集标识未注册：{option_set_key}")
        elif option_set_key is not None:
            raise FormFieldTypeInvalidError(f"非枚举字段不得指定选项集：{field_type}")
        column_name = derive_column_name(key)
        async with self._uow.begin():
            snapshot = await self._metadata.load(form_code)
            if snapshot is None:
                raise FormNotCustomizableError(f"表单不存在或不可定制：{form_code}")
            if snapshot.table_name is None:
                raise FormNotCustomizableError(f"表单物理表不可解析（未登记 form_key → table）：{form_code}")
            table_name = validate_table_name(snapshot.table_name)
            existing = await self._fields.get_by_key(form_code, key)
            if existing is not None and existing.status == "enabled":
                raise FormFieldKeyConflictError(f"字段键已存在：{key}")
            if existing is not None:
                row = await self._fields.update(
                    existing.id,
                    name=name.strip(),
                    type=field_type,
                    option_set_key=option_set_key,
                    table_name=table_name,
                    ddl_status=DDL_STATUS_PENDING,
                    sort=sort,
                    status="enabled",
                )
                if row is None:  # pragma: no cover - 取到即存在
                    raise FormFieldKeyConflictError(f"字段键已存在：{key}")
                field_row = row
            else:
                field_row = await self._fields.create(
                    form_code=form_code,
                    field_key=key,
                    name=name.strip(),
                    type=field_type,
                    option_set_key=option_set_key,
                    column_name=column_name,
                    table_name=table_name,
                    ddl_status=DDL_STATUS_PENDING,
                    sort=sort,
                    status="enabled",
                )
            if name.strip() != "":  # pragma: no cover - 名称入库前已 strip 且非空（请求模型 min_length=1）
                await self._i18n.replace_names(field_row.id, ConcurrentStableDict({"zh-CN": name.strip()}))
        result = await self._run_ddl(field_row)
        await self._commit()
        await self._full_invalidate(form_code)
        return result

    async def update_field(
        self,
        *,
        field_id: int,
        name: str | None,
        status: str | None,
        option_set_key: str | None,
        sort: int | None,
    ) -> SysFieldExt:
        """编辑自建字段（改名 / 停用 / 改选项集 / 改排序；**不删列**）。

        Args:
            field_id: 自建字段主键。
            name: 新名称（None 表示不改）。
            status: 新状态（`enabled` / `disabled`；None 表示不改）。
            option_set_key: 新选项集标识（None 表示不改）。
            sort: 新排序（None 表示不改）。

        Returns:
            SysFieldExt: 更新后的行。

        Raises:
            NotFoundError: 字段不存在（10002）。
            FormFieldTypeInvalidError: 选项集未注册或类型不允许（40404）。
        """
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if name is not None:
            values.set("name", name.strip())
        if status is not None:
            if status not in ("enabled", "disabled"):
                raise FormFieldTypeInvalidError(f"字段状态非法：{status}")
            values.set("status", status)
        if option_set_key is not None:
            if not self._option_sets.is_registered(option_set_key):
                raise FormFieldTypeInvalidError(f"选项集标识未注册：{option_set_key}")
            values.set("option_set_key", option_set_key)
        if sort is not None:
            values.set("sort", sort)
        async with self._uow.begin():
            row = await self._fields.get(field_id)
            if row is None:
                from bms_core.core.exceptions import NotFoundError

                raise NotFoundError(f"自建字段不存在：{field_id}")
            if option_set_key is not None and row.type not in FIELD_OPTION_REQUIRED:
                raise FormFieldTypeInvalidError(f"非枚举字段不得指定选项集：{row.type}")
            updated = await self._fields.update(field_id, **normalize_dict(values))
            if updated is None:  # pragma: no cover - 取到即存在
                from bms_core.core.exceptions import NotFoundError

                raise NotFoundError(f"自建字段不存在：{field_id}")
            if name is not None:
                await self._i18n.replace_names(field_id, ConcurrentStableDict({"zh-CN": name.strip()}))
            await self._publish(row.form_code, changed_type="ext_field")
        await self._commit()
        await self._full_invalidate(row.form_code)
        return updated

    async def retry_field(self, *, field_id: int) -> SysFieldExt:
        """重试建列（复用同一元数据与列名；`failed` → `active`）。

        Args:
            field_id: 自建字段主键。

        Returns:
            SysFieldExt: 更新后的行。

        Raises:
            NotFoundError: 字段不存在（10002）。
        """
        async with self._uow.begin():
            row = await self._fields.get(field_id)
            if row is None:
                from bms_core.core.exceptions import NotFoundError

                raise NotFoundError(f"自建字段不存在：{field_id}")
            await self._fields.update(field_id, ddl_status=DDL_STATUS_PENDING)
        await self._commit()
        result = await self._run_ddl(row)
        await self._full_invalidate(row.form_code)
        return result

    # ------------------------------------------------------------------ DDL 编排

    async def _commit(self) -> None:
        """提交当前事务（DDL 后状态回写需要可见；仓储只 flush、提交归服务层）。

        说明：本域写路径分两段（元数据落库 → DDL 执行 → 状态回写），DDL 在**独立语句**上执行，
        状态回写必须提交后其它请求才看得到；因此这里显式提交一次（与工作单元成对使用）。
        """
        raw = getattr(self._session, "raw", None)
        if raw is not None:  # pragma: no cover - 同步门面（DM8 等同步方言）分支，异步会话下不可达
            await raw.commit()
            return
        commit = getattr(self._session, "commit", None)
        if callable(commit):  # pragma: no cover - 会话契约保证有 commit
            await cast("Awaitable[None]", commit())

    async def _write_status(self, row: SysFieldExt, status: str) -> SysFieldExt | None:
        """回写建列状态并发事件（不新开事务：DDL 与状态回写在同一请求事务内）。

        Args:
            row: 自建字段行。
            status: 目标 `ddl_status`（`active` / `failed`）。

        Returns:
            SysFieldExt | None: 更新后的行。
        """
        updated = await self._fields.update(row.id, ddl_status=status)
        await self._publish(row.form_code, changed_type="ext_field")
        await self._commit()
        return updated

    async def _run_ddl(self, row: SysFieldExt) -> SysFieldExt:
        """执行建列并回写状态（失败置 `failed`，不抛——失败信息随行下发给前端标记）。

        Args:
            row: 自建字段行（`ddl_status=pending`）。

        Returns:
            SysFieldExt: 更新后的行（`active` / `failed`）。
        """
        try:
            outcome = await self._ddl.add_column(row, comment=row.name)
        except Exception as exc:
            _LOGGER.warning(
                "自建字段建列失败（可重试）",
                form_code=row.form_code,
                field_key=row.field_key,
                column=row.column_name,
                error=f"{type(exc).__name__}: {exc}",
                detail=str(exc)[:500],
            )
            updated = await self._write_status(row, DDL_STATUS_FAILED)
            return updated if updated is not None else row
        updated = await self._write_status(row, DDL_STATUS_ACTIVE)
        _LOGGER.info(
            "自建字段建列完成",
            form_code=row.form_code,
            field_key=row.field_key,
            column=outcome.column_name,
            created=outcome.created,
        )
        return updated if updated is not None else row

    async def _publish(self, form_code: str, *, changed_type: str) -> None:
        """发布 `sys.form.updated`（同一写事务内）。

        Args:
            form_code: 表单标识。
            changed_type: 变更类别。
        """
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=EXT_FIELD_EVENT,
                payload=ConcurrentStableDict(
                    {"form_id": "", "menu_id": "", "business_id": "", "changed_type": changed_type}
                ),
                aggregate_key=f"form:{form_code}",
            ),
        )

    async def _full_invalidate(self, form_code: str) -> None:
        """失效字段清单与布局缓存（自建字段变化会影响两者）。

        Args:
            form_code: 表单标识。
        """
        if self._invalidate is None:  # pragma: no cover - 装配面恒注入失效回调
            return
        await self._invalidate(form_code)


def normalize_dict(values: ConcurrentStableDict[str, object]) -> ConcurrentStableDict[str, object]:
    """把待更新字段字典转为普通映射（`update(**)` 需要关键字参数）。

    Args:
        values: 待更新字段。

    Returns:
        ConcurrentStableDict[str, object]: 同内容字典（便于 `**` 展开）。
    """
    return ConcurrentStableDict(values)
