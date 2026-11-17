"""自建字段跨四库类型映射（表单定制专用，唯一来源）。

**为什么与 `fieldtype/local.py` 的内建映射分开**（任务 10_01 决策 3）：内建 `SimpleFieldType` 服务
`dict` / `dict_multi` 与既有契约快照（`number` → `int`、`file` → `text`），改动会波及既有断言与
全部消费方；租户自建字段按《概要设计 · 表单定制》§4 的落点（`number` → `DECIMAL(18,4)`、
`file` → `VARCHAR(255)`），因此单列本表、互不牵连。

**为什么返回类型对象而非类型字符串**：DDL 由 SQLAlchemy 按方言编译（`AddColumn`），达梦的
`VARCHAR2(n CHAR)`、PostgreSQL 的 `TIMESTAMP WITHOUT TIME ZONE` 等差异自然落地；返回字符串就必须
按方言分支拼 SQL——那正是「不走字符串拼接」要禁掉的做法。

**长文本四库统一 `TEXT`**（决策 4）：达梦 `TEXT` 与 `CLOB` 属同一类大文本（官方社区「同一类、功能上
无明显区别」；`LONG` / `LONGVARCHAR` 为 `TEXT` 同义类型），本项目《方言特性 · 达梦》已有 `TEXT → TEXT`
实测行与 02_14 探针实测。业务层只暴露 `longtext`，方言差异全部收在本文件。

实测（`tmp/ddl_probe2.py`，四库 `AddColumn.compile`）：

| 类型 | SQLite | MySQL 8 | PostgreSQL 16 | 达梦 DM8 |
| --- | --- | --- | --- | --- |
| `text` | `VARCHAR(255)` | `VARCHAR(255)` | `VARCHAR(255)` | `VARCHAR2(255 CHAR)` |
| `longtext` | `TEXT` | `TEXT` | `TEXT` | `TEXT` |
| `number` | `NUMERIC(18, 4)` | `NUMERIC(18, 4)` | `NUMERIC(18, 4)` | `NUMERIC(18, 4)` |
| `datetime` | `DATETIME` | `DATETIME` | `TIMESTAMP WITHOUT TIME ZONE` | `DATETIME` |
| `option` | `VARCHAR(64)` | `VARCHAR(64)` | `VARCHAR(64)` | `VARCHAR2(64 CHAR)` |
| `option_multi` | `TEXT` | `TEXT` | `TEXT` | `TEXT` |
| `switch` | `SMALLINT` | `SMALLINT` | `SMALLINT` | `SMALLINT` |
| `file` | `VARCHAR(255)` | `VARCHAR(255)` | `VARCHAR(255)` | `VARCHAR2(255 CHAR)` |
"""

from sqlalchemy import DateTime, Numeric, SmallInteger, String, Text
from sqlalchemy.types import TypeEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import NotFoundError

__all__ = [
    "EXT_FIELD_TYPE_KEYS",
    "EXT_FIELD_TYPE_LABELS",
    "ext_column_type",
    "ext_column_type_name",
    "is_ext_field_type",
]

EXT_FIELD_TYPE_KEYS: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "text",
        "longtext",
        "number",
        "datetime",
        "option",
        "option_multi",
        "switch",
        "file",
    )
)
"""自建字段类型白名单（与 `models/platform/form_design.py::EXT_FIELD_TYPES` 同序同值）。"""

EXT_FIELD_TYPE_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "text": "单行文本",
        "longtext": "长文本",
        "number": "数字",
        "datetime": "日期时间",
        "option": "选项集单选",
        "option_multi": "选项集多选",
        "switch": "开关",
        "file": "文件",
    }
)
"""类型中文名（设计器 / 错误提示用；不进契约）。"""

_LOGICAL_TYPE_NAMES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "text": "VARCHAR(255)",
        "longtext": "TEXT",
        "number": "DECIMAL(18,4)",
        "datetime": "TIMESTAMP",
        "option": "VARCHAR(64)",
        "option_multi": "TEXT",
        "switch": "SMALLINT",
        "file": "VARCHAR(255)",
    }
)
"""逻辑类型名（文档登记与错误提示用；不参与 DDL 编译）。"""


def _type_factories() -> ConcurrentStableDict[str, TypeEngine[object]]:
    """构造类型实例表（每次新建实例：SQLAlchemy 类型对象不宜跨列共享）。

    Returns:
        ConcurrentStableDict[str, TypeEngine[object]]: 类型标识 → SQLAlchemy 类型实例。
    """
    return ConcurrentStableDict[str, TypeEngine[object]](
        {
            "text": String(255),
            "longtext": Text(),
            "number": Numeric(18, 4),
            "datetime": DateTime(),
            "option": String(64),
            "option_multi": Text(),
            "switch": SmallInteger(),
            "file": String(255),
        }
    )


def is_ext_field_type(field_type: str) -> bool:
    """是否自建字段白名单类型。

    Args:
        field_type: 字段类型标识。

    Returns:
        bool: 在白名单内为 True。
    """
    return field_type in EXT_FIELD_TYPE_KEYS


def ext_column_type(field_type: str) -> TypeEngine[object]:
    """取自建字段类型的 SQLAlchemy 类型实例（DDL 编译用）。

    Args:
        field_type: 字段类型标识。

    Returns:
        TypeEngine[object]: 类型实例（新实例，可安全挂到列上）。

    Raises:
        NotFoundError: 类型不在白名单（10002；调用方应先以 `is_ext_field_type` 判 `40404`）。
    """
    built = _type_factories().get(field_type)
    if built is None:
        raise NotFoundError(f"自建字段类型不在白名单：{field_type}")
    return built


def ext_column_type_name(field_type: str) -> str:
    """取逻辑类型名（文档 / 错误提示用，不参与 DDL）。

    Args:
        field_type: 字段类型标识。

    Returns:
        str: 逻辑类型名（如 `DECIMAL(18,4)`）。

    Raises:
        NotFoundError: 类型不在白名单（10002）。
    """
    name = _LOGICAL_TYPE_NAMES.get(field_type)
    if name is None:
        raise NotFoundError(f"自建字段类型不在白名单：{field_type}")
    return name
