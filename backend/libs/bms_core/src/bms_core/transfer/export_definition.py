"""导入导出能力域 · 列表导出定义契约与注册表（04_02）。

- `ExportQuery`：端点解析后的统一导出查询（筛选 / 排序 / 选中集合 / 未识别参数透传）。
- `BaseExportDefinition`：业务导出定义的最小面——业务标识 / 标题 / 列集 / 脱敏字段 / 统计 / 分批取数。
- `ExportDefinitionRegistry`：进程内 `biz → 定义`（构建期登记、运行期只读；重名 / 非法 / 脱敏键越界即拒）。
- `parse_ids`：`ids` 参数解析（逗号分隔雪花 ID）。

口径：`count` 与 `fetch` 必须复用本域仓储的**同一组过滤条件与排序解析**（不得另写 SQL），这是
「导出条数 = 列表总数」的结构性保证；行形态为 `{列键: 已格式化值}`，业务格式化（状态标签 / 时间）
在定义内完成，导出层不解析业务语义。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.transfer.base import ColumnSpec

__all__ = [
    "EXPORT_ORDERS",
    "BaseExportDefinition",
    "ExportDefinitionRegistry",
    "ExportQuery",
    "parse_ids",
]

_BIZ_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""业务标识格式（路径段；小写字母开头）。"""

EXPORT_ORDERS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("asc", "desc"))
"""排序方向取值（与列表接口同口径）。"""

EXPORT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""导出时间格式（UTC；时区转换归 05_02）。"""


@dataclass(frozen=True)
class ExportQuery(BaseValueObject):
    """统一导出查询（端点解析产物；定义只读消费）。"""

    keyword: str | None = None
    """关键字（与列表接口同名同义）。"""

    status: str | None = None
    """状态筛选。"""

    ids: ConcurrentStableFrozenList[int] = field(default_factory=lambda: ConcurrentStableFrozenList[int]())
    """选中行集合（空 = 按筛选全量）。"""

    order_by: str | None = None
    """排序字段（各定义白名单；非法回落默认）。"""

    order: str = "asc"
    """排序方向（取值 ∈ `EXPORT_ORDERS`）。"""

    params: ConcurrentStableFrozenDict[str, str] = field(default_factory=lambda: ConcurrentStableFrozenDict[str, str]())
    """未识别 query 参数（产品自定义定义消费；首批两定义忽略）。"""


def parse_ids(raw: str | None) -> ConcurrentStableFrozenList[int]:
    """解析 `ids` 参数（逗号分隔雪花 ID）。

    Args:
        raw: 原始字符串（空 / None 表示不限定）。

    Returns:
        ConcurrentStableFrozenList[int]: 主键集合（去重保序）。

    Raises:
        ParamError: 存在非正整数项（`10001`）。
    """
    if raw is None or not raw.strip():
        return ConcurrentStableFrozenList[int]()
    parsed: ConcurrentStableList[int] = ConcurrentStableList()
    seen: ConcurrentStableDict[int, bool] = ConcurrentStableDict()
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        if not text.isdigit():
            raise ParamError(f"ids 含非法主键：{text}")
        value = int(text)
        if value <= 0:
            raise ParamError(f"ids 含非法主键：{text}")
        if value in seen:
            continue
        seen.set(value, True)
        parsed.add(value)
    return ConcurrentStableFrozenList(parsed)


class BaseExportDefinition(BaseFrameworkObject, ABC):
    """业务导出定义：列集 + 脱敏字段 + 统计 + 分批取数。"""

    biz: str = ""
    """业务标识（路径段，如 users / roles）。"""

    title: str = ""
    """业务中文名（文件名前缀 / PDF 标题缺省）。"""

    export_permission: str = "export:download"
    """入口权限码（端点级已校验；定义可按业务加严）。"""

    masked_fields: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    """敏感列声明（列键 → 掩码策略；空 = 无敏感列；**只读**，不得在运行期改写）。"""

    @property
    @abstractmethod
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导出列集（固定列序；只消费 `key` / `title`）。

        Returns:
            ConcurrentStableFrozenList[ColumnSpec]: 列定义。
        """

    @abstractmethod
    async def count(self, session: DbSession, query: ExportQuery) -> int:
        """按筛选条件统计导出条数（与列表 `total` 同源）。

        Args:
            session: 当前会话。
            query: 导出查询。

        Returns:
            int: 条数。
        """

    @abstractmethod
    async def fetch(
        self,
        session: DbSession,
        query: ExportQuery,
        *,
        offset: int,
        limit: int,
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """按筛选条件分批取数（与 `count` 同源）。

        Args:
            session: 当前会话。
            query: 导出查询。
            offset: 起始偏移（自 0 起）。
            limit: 本批上限。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 行集（列键 → 值）。
        """


class ExportDefinitionRegistry(BaseFrameworkObject):
    """导出定义注册表（进程内、构建期登记、运行期只读）。"""

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._definitions: ConcurrentStableDict[str, BaseExportDefinition] = ConcurrentStableDict()

    def register(self, definition: BaseExportDefinition) -> None:
        """登记定义（非法 biz / 重名 / 空标题 / 空列集 / 列键或标题重复 / 脱敏键越界即拒）。

        Args:
            definition: 导出定义。

        Raises:
            ValueError: 定义不合法（构建期 fail-fast）。
        """
        biz = definition.biz.strip()
        if _BIZ_PATTERN.fullmatch(biz) is None:
            raise ValueError(f"导出业务标识非法：{definition.biz!r}")
        if biz in self._definitions:
            raise ValueError(f"导出业务标识重复：{biz}")
        if not definition.title.strip():
            raise ValueError(f"导出业务标题为空：{biz}")
        columns = definition.columns
        if not columns:
            raise ValueError(f"导出业务列集为空：{biz}")
        keys: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
        titles: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
        for column in columns:
            if column.key in keys:
                raise ValueError(f"导出列键重复：{biz}:{column.key}")
            if column.title in titles:
                raise ValueError(f"导出列标题重复：{biz}:{column.title}")
            keys.set(column.key, True)
            titles.set(column.title, True)
        for field_name in definition.masked_fields:
            if field_name not in keys:
                raise ValueError(f"导出脱敏字段不在列集内：{biz}:{field_name}")
        self._definitions.set(biz, definition)

    def get(self, biz: str) -> BaseExportDefinition | None:
        """按业务标识取定义。

        Args:
            biz: 业务标识。

        Returns:
            BaseExportDefinition | None: 定义；未登记返回 None。
        """
        return self._definitions.get(biz)

    def all(self) -> ConcurrentStableFrozenDict[str, BaseExportDefinition]:
        """取全部定义（只读快照）。

        Returns:
            ConcurrentStableFrozenDict[str, BaseExportDefinition]: 业务标识 → 定义。
        """
        return ConcurrentStableFrozenDict[str, BaseExportDefinition](dict(self._definitions))


def format_export_time(value: datetime | None) -> str:
    """把 UTC 时间格式化为导出文本（空值输出空串）。

    时区一律 UTC（跨租户可比、不依赖宿主时区）；用户时区偏好（05_02）落地后只改本函数一处。

    Args:
        value: UTC 时间（naive 或 aware）。

    Returns:
        str: `YYYY-MM-DD HH:mm:ss` 或空串。
    """
    if value is None:
        return ""
    return value.strftime(EXPORT_TIME_FORMAT)
