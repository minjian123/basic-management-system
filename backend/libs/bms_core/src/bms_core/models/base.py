"""ORM 声明式基类与模型基类：每表必备字段与约定，一次定义。

- `Base`：SQLAlchemy 2.0 声明式基类（元数据 / 注册表）。
- `BaseModel`：L0 模型基类（雪花 ID / 审计 / 软删除 / 乐观锁），模块模型继承之。

四库类型映射（跨方言，禁用方言专用类型；实测值，编译四方言 DDL 断言见 `tests/models/test_type_mapping.py`）：

| 字段 | SQLite | MySQL | PostgreSQL | 达梦 DM8 |
| --- | --- | --- | --- | --- |
| id / 雪花 ID 列（`SnowflakeId`） | TEXT（38 位十进制补零） | DECIMAL(38, 0) | DECIMAL(38, 0) | DECIMAL(38, 0) |
| 计数 / 字节列（`BigInteger`） | BIGINT | BIGINT | BIGINT | BIGINT |
| *_at DateTime | DATETIME | DATETIME | TIMESTAMP WITHOUT TIME ZONE | DATETIME |
| version / Integer | INTEGER | INTEGER | INTEGER | INTEGER |
| SmallInteger | SMALLINT | SMALLINT | SMALLINT | SMALLINT |
| String(n) | VARCHAR(n) | VARCHAR(n) | VARCHAR(n) | VARCHAR2(n CHAR) |
| Text | TEXT | TEXT | TEXT | TEXT |
| 布尔（`Boolean`） | BOOLEAN | BOOL（TINYINT(1)） | BOOLEAN | SMALLINT |
| 多值（`JSON`） | JSON | JSON | JSON | JSON |

雪花 ID 一律用 `SnowflakeId`（126 位，`DECIMAL(38,0)`；SQLite 测试库落 38 位补零 `TEXT`，
避免 `NUMERIC` 把超 64 位整数转 `REAL` 丢精度、同时保住字典序 = 数值序）。**禁止裸 `BigInteger`
承载雪花 ID**（主键 / 逻辑外键 / `tenant_id` / 审计人 / `parent_id` 等）；`BigInteger` 仅用于
计数、字节数等度量列，例外须在静态护栏规则中逐条登记。

布尔字段统用 `Boolean`（四库落为各自布尔 / 小整数等价形式）；多值字段用 `JSON` 存数组，
接口仍按数组传输，标签类简单集合可逗号分隔字符串（见《架构设计 · 数据架构》「数据规范」节）。

表级规范：表名单数 snake_case；平台域前缀 `sys_`/`wf_`/`rpt_`/`ai_`、业务模块 `{简称}_`；
索引命名 `idx_字段` / `uq_字段`（每表 ≤ 5；`index=True` 由元数据命名约定生成 `idx_{表}_{列}`）；
时间 UTC、金额 NUMERIC(20,4)、字符串 VARCHAR（长度显式）；
每表与字段 COMMENT 必填；逻辑外键（`目标表_id`），不建物理外键。
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar, cast

from sqlalchemy import (
    DECIMAL,
    JSON,
    Connection,
    DateTime,
    Integer,
    MetaData,
    Text,
    event,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column
from sqlalchemy.types import TypeDecorator

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_user_id
from bms_core.core.id import id_generator
from bms_core.core.id_bits import MAX_ID
from bms_core.core.objects import BaseDataContract
from bms_core.core.serialization import normalize_collections

StableJsonT = TypeVar("StableJsonT")

SNOWFLAKE_DECIMAL_PRECISION = 38
"""雪花 ID 十进制精度（达梦官方上限 38 位；`2^126-1` 为 38 位十进制）。"""

SQLITE_PADDED_WIDTH = 38
"""SQLite 文本变体的补零宽度（定长保证字典序 = 数值序）。"""


def to_stable_value(value: object) -> object:
    """把 JSON 读回的内置容器**递归**转为插入序集合类（`dict` → `ConcurrentStableDict` 等）。

    Args:
        value: JSON 反序列化结果。

    Returns:
        object: 集合类 / 标量（递归）。
    """
    if isinstance(value, str | bytes | bytearray):
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return ConcurrentStableDict({key: to_stable_value(item) for key, item in mapping.items()})
    if isinstance(value, (list, tuple)):
        items = cast("Iterable[object]", value)
        return ConcurrentStableList(to_stable_value(item) for item in items)
    if isinstance(value, (set, frozenset)):
        members = cast("Iterable[object]", value)
        return ConcurrentStableSet(to_stable_value(item) for item in members)
    return value


class StableJson(TypeDecorator[StableJsonT]):
    """JSON 列类型（插入序）：**写入**内置容器（稳定 JSON）、**读回**插入序集合类（递归）。

    模块多值字段统一用本类型替代裸 `JSON`：声明与运行期形态一致（`Mapped[ConcurrentStable*]`），
    落库前经 `normalize_collections` 规整（免 `json.dumps` 遇非内置容器报错）。
    """

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: object, dialect: Dialect) -> object:
        """落库：集合类前置规整为内置容器。"""
        return None if value is None else normalize_collections(value)

    def process_result_value(self, value: object, dialect: Dialect) -> StableJsonT | None:
        """读回：内置容器递归转为插入序集合类。"""
        return None if value is None else cast("StableJsonT", to_stable_value(value))


def _coerce_snowflake(value: object) -> int | None:
    """把绑定值规整为 126 位雪花 ID（`int` / `Decimal` / 十进制字符串）。

    Args:
        value: 待规整值。

    Returns:
        int | None: 规整后的整数；`None` 原样返回。

    Raises:
        ValueError: 非整数值或超出 `0 ~ 2^126-1`。
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise ValueError(f"雪花 ID 取值类型非法：{type(value).__name__}")
    if isinstance(value, Decimal) and value != value.to_integral_value():
        raise ValueError(f"雪花 ID 必须为整数：{value}")
    number = int(value)
    if not 0 <= number <= MAX_ID:
        raise ValueError(f"雪花 ID 必须在 0 ~ {MAX_ID} 之间：{number}")
    return number


class SnowflakeId(TypeDecorator[int]):
    """雪花 ID 列类型（126 位）：四库 `DECIMAL(38,0)`；SQLite 落 38 位补零 `TEXT`。

    - **精度**：`2^126-1` 为 38 位十进制，落在达梦 `DECIMAL` 官方精度上限内；
    - **SQLite**：`NUMERIC` 会把超过 64 位的整数转 `REAL` 丢精度，故改为定长补零文本
      （字典序 = 数值序，`ORDER BY` / 范围 / 游标语义与生产库一致）；
    - **读回**：`int` / `Decimal` / 补零字符串统一转 `int`，ORM 属性恒为整数；
    - **比较**：`coerce_compared_value` 缺省返回 `self`，比较值走同一绑定（SQLite 同样补零）。
    """

    impl = DECIMAL(SNOWFLAKE_DECIMAL_PRECISION, 0)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """按方言加载底层类型（SQLite → `TEXT`，其余 → `DECIMAL(38,0)`）。

        Args:
            dialect: 目标方言。

        Returns:
            Any: 底层类型实例。
        """
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text())
        return super().load_dialect_impl(dialect)

    def process_bind_param(self, value: object, dialect: Dialect) -> object:
        """落库：规整为整数；SQLite 转 38 位补零文本。

        Args:
            value: 绑定值。
            dialect: 目标方言。

        Returns:
            object: 绑定值（`int` 或补零 `str`）。
        """
        number = _coerce_snowflake(value)
        if number is None:
            return None
        return str(number).zfill(SQLITE_PADDED_WIDTH) if dialect.name == "sqlite" else number

    def process_result_value(self, value: object, dialect: Dialect) -> int | None:
        """读回：`int` / `Decimal` / 补零文本统一转整数。

        Args:
            value: 数据库返回值。
            dialect: 目标方言。

        Returns:
            int | None: 整数 ID。
        """
        del dialect
        return None if value is None else int(cast("int | Decimal | str", value))

    @property
    def python_type(self) -> type[int]:
        """Python 侧类型（`int`）。"""
        return int


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类（元数据 / 注册表）。

    索引命名约定：`index=True` 生成的索引名统一为 `idx_{表}_{列}`（对齐《命名规范》
    「普通 `idx_字段`」；带表名前缀避免 PostgreSQL / 达梦下同名列索引跨表重名）。
    """

    metadata = MetaData(naming_convention={"ix": "idx_%(table_name)s_%(column_0_name)s"})


class BaseModel(Base, BaseDataContract):
    """ORM 模型基类（L0）：每表必备字段与约定，模块模型继承之。

    - `id`：雪花 ID（126 位，`DECIMAL(38,0)`；SQLite 测试库为 38 位补零 `TEXT`，应用侧生成，禁用数据库自增列）
    - 审计：`created_at` / `created_by` / `updated_at` / `updated_by`（ORM 事件自动填充）
    - 软删除：`deleted_at`（NULL=未删）；唯一约束建为 `(唯一字段, deleted_at)` 复合唯一
    - 乐观锁：`version`（`version_id_col` 自动比对 / 自增，冲突抛 `StaleDataError`）
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(
        SnowflakeId,
        primary_key=True,
        autoincrement=False,
        default=id_generator.next_id,
        comment="主键（雪花 ID）",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间（UTC）")
    created_by: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="创建人")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="更新时间（UTC）")
    updated_by: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="更新人")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, comment="软删除时间（NULL=未删）"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="乐观锁版本")

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    def soft_delete(self) -> None:
        """标记软删除（置 `deleted_at`，由 ORM 事件刷新审计）。"""
        self.deleted_at = _utc_now()

    def restore(self) -> None:
        """恢复软删除（清空 `deleted_at`）。"""
        self.deleted_at = None


@event.listens_for(BaseModel, "before_insert", propagate=True)
def _fill_audit_on_insert(mapper: Mapper[Any], connection: Connection, target: BaseModel) -> None:  # pyright: ignore[reportUnusedFunction]
    """插入前自动填充审计字段（业务代码禁止手动赋值）。"""
    now = _utc_now()
    target.created_at = now
    target.updated_at = now
    user = current_user_id.get()
    target.created_by = user
    target.updated_by = user


@event.listens_for(BaseModel, "before_update", propagate=True)
def _fill_audit_on_update(mapper: Mapper[Any], connection: Connection, target: BaseModel) -> None:  # pyright: ignore[reportUnusedFunction]
    """更新前刷新更新时间与更新人。"""
    target.updated_at = _utc_now()
    target.updated_by = current_user_id.get()
