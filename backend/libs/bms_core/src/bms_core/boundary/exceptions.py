"""读侧出口例外登记：白名单契约 + 加载 / 校验 / 匹配（仅标准库；静态校验与运行时守卫同源）。

- `OwnershipException`：一条例外登记（消费方服务 / 目标表名或前缀 / 访问类型 / 出口 / 消费方 /
  理由 / 替代方案评估 / 失效条件 / 登记日期）。
- `load_exceptions`：载入白名单文件（缺文件返回空；结构非法抛 `ValueError`）。
- `validate_exceptions`：语义校验（服务须在服务目录、目标须为已登记表名或已知前缀、
  `access` 只能为 `read`、出口枚举、日期格式）。
- `exception_allows`：命中判定（目标按**表名或表前缀**匹配；仅 `access=read` 且操作 `read`）。

口径：**写侧硬禁无例外**——`access` 只允许 `read`，越界写一律违规；例外须写清替代方案与失效条件。
字段名 `target_prefix` 保留（06_03 起语义扩为「表名或表前缀」），避免白名单格式破坏。
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from bms_core.core.base import BaseObject

__all__ = [
    "DEFAULT_EXCEPTIONS_RELATIVE",
    "EXCEPTION_ACCESS",
    "EXCEPTION_EXITS",
    "OwnershipException",
    "exception_allows",
    "load_exceptions",
    "validate_exceptions",
]

EXCEPTION_EXITS: tuple[str, ...] = ("service_dto", "readonly_projection", "direct_read")
"""出口类型：契约 DTO / 只读投影 / 已评审的跨模块直读例外。"""

EXCEPTION_ACCESS = "read"
"""允许的访问类型（只读；写侧硬禁无例外）。"""

DEFAULT_EXCEPTIONS_RELATIVE = "deploy/boundaries/data_ownership_exceptions.json"
"""白名单默认相对仓库根路径。"""

_EXCEPTION_VERSION = 1
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED_FIELDS: tuple[str, ...] = (
    "service",
    "target_prefix",
    "access",
    "exit",
    "consumer",
    "reason",
    "alternative",
    "expiry",
    "registered_at",
)


@dataclass(frozen=True)
class OwnershipException(BaseObject):
    """一条读侧出口例外登记。"""

    service: str
    """消费方服务标识（`service_key`）。"""

    target_prefix: str
    """目标表前缀。"""

    access: str
    """访问类型（固定 `read`）。"""

    exit: str
    """出口类型（`EXCEPTION_EXITS` 之一）。"""

    consumer: str
    """消费方模块 / 功能。"""

    reason: str
    """例外理由。"""

    alternative: str
    """替代方案评估。"""

    expiry: str
    """失效条件（何时应移除该例外）。"""

    registered_at: str
    """登记日期（`YYYY-MM-DD`）。"""


def _parse_exception(item: object, index: int) -> OwnershipException:
    """解析单条例外（结构非法抛 `ValueError`）。

    Args:
        item: JSON 条目。
        index: 条目序号（错误提示用）。

    Returns:
        OwnershipException: 例外登记。

    Raises:
        ValueError: 条目非对象、字段缺失 / 非字符串 / 为空，或 `access` 非 `read`。
    """
    if not isinstance(item, dict):
        raise ValueError(f"例外登记第 {index} 条须为对象")
    fields = cast("dict[object, object]", item)
    values: dict[str, str] = {}
    for field in _REQUIRED_FIELDS:
        raw = fields.get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"例外登记第 {index} 条字段缺失或为空：{field}")
        values[field] = raw.strip()
    if values["access"] != EXCEPTION_ACCESS:
        raise ValueError(f"例外登记第 {index} 条 access 只允许 {EXCEPTION_ACCESS!r}（写侧硬禁无例外）")
    return OwnershipException(
        service=values["service"],
        target_prefix=values["target_prefix"],
        access=values["access"],
        exit=values["exit"],
        consumer=values["consumer"],
        reason=values["reason"],
        alternative=values["alternative"],
        expiry=values["expiry"],
        registered_at=values["registered_at"],
    )


def load_exceptions(path: Path) -> tuple[OwnershipException, ...]:
    """载入例外白名单（缺文件返回空集）。

    Args:
        path: 白名单文件路径。

    Returns:
        tuple[OwnershipException, ...]: 例外条目（按文件顺序）。

    Raises:
        ValueError: JSON 非法、根结构 / 版本非法、条目结构非法。
    """
    if not path.is_file():
        return ()
    try:
        parsed = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"例外白名单 JSON 非法：{path}（{exc}）") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"例外白名单根须为对象：{path}")
    data = cast("dict[object, object]", parsed)
    if data.get("version") != _EXCEPTION_VERSION:
        raise ValueError(f"例外白名单版本非法（应为 {_EXCEPTION_VERSION}）：{path}")
    raw_exceptions = data.get("exceptions")
    if not isinstance(raw_exceptions, list):
        raise ValueError(f"例外白名单 exceptions 须为数组：{path}")
    items = cast("list[object]", raw_exceptions)
    return tuple(_parse_exception(item, index) for index, item in enumerate(items, start=1))


def validate_exceptions(
    entries: Iterable[OwnershipException],
    *,
    known_tables: frozenset[str],
    known_prefixes: frozenset[str],
    known_services: frozenset[str],
) -> list[str]:
    """语义校验例外登记（服务 / 目标 / 出口 / 日期）。

    Args:
        entries: 例外条目。
        known_tables: 归属登记的表名集合（`target_prefix` 允许写具体表名）。
        known_prefixes: 可作为目标的表前缀集合（服务目录前缀 ∪ 归属登记表前缀）。
        known_services: 服务目录登记标识。

    Returns:
        list[str]: 违规明细（空列表表示通过）。
    """
    problems: list[str] = []
    for entry in entries:
        if entry.service not in known_services:
            problems.append(f"[例外登记] service 未在服务目录：{entry.service}")
        if entry.target_prefix not in known_tables and entry.target_prefix not in known_prefixes:
            problems.append(f"[例外登记] 目标既非已登记表名也非已知前缀：{entry.target_prefix}")
        if entry.exit not in EXCEPTION_EXITS:
            problems.append(f"[例外登记] exit 非法：{entry.exit}（允许 {'、'.join(EXCEPTION_EXITS)}）")
        if not _DATE_RE.fullmatch(entry.registered_at):
            problems.append(f"[例外登记] registered_at 须为 YYYY-MM-DD：{entry.registered_at}")
    return problems


def exception_allows(
    entries: Iterable[OwnershipException],
    *,
    service: str,
    table: str,
    operation: str,
) -> bool:
    """命中判定：服务匹配且目标（表名或表前缀）匹配，访问类型与操作均为只读。

    Args:
        entries: 例外条目。
        service: 消费方服务标识。
        table: 被访问表名。
        operation: 操作归类（只读 `read` 可命中）。

    Returns:
        bool: 命中返回 True。
    """
    if operation != EXCEPTION_ACCESS:
        return False
    prefix = table.split("_", 1)[0] + "_" if "_" in table else table
    return any(
        entry.service == service and entry.access == EXCEPTION_ACCESS and entry.target_prefix in (table, prefix)
        for entry in entries
    )
