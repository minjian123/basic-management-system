"""ORM 声明式基类与模型基类：每表必备字段与约定，一次定义。

- `Base`：SQLAlchemy 2.0 声明式基类（元数据 / 注册表）。
- `BaseModel`：L0 模型基类（雪花 ID / 审计 / 软删除 / 乐观锁），模块模型继承之。

四库类型映射（跨方言，禁用方言专用类型）：

| 字段 | SQLite | MySQL | PostgreSQL | 达梦 DM8 |
| --- | --- | --- | --- | --- |
| id | INTEGER | BIGINT | BIGINT | BIGINT |
| *_at | DATETIME | DATETIME | TIMESTAMP | TIMESTAMP |
| version | INTEGER | INT | INTEGER | INT |
| 布尔（通用约定） | INTEGER 0/1 | TINYINT(1) | SMALLINT | SMALLINT |

表级规范：表名单数 snake_case；平台域前缀 `sys_`/`wf_`/`rpt_`/`ai_`、业务模块 `{简称}_`；
索引命名 `idx_字段` / `uq_字段`（每表 ≤ 5）；时间 UTC、金额 NUMERIC(20,4)、字符串 VARCHAR（长度显式）；
每表与字段 COMMENT 必填；逻辑外键（`目标表_id`），不建物理外键。
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Connection, DateTime, Integer, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from app.core.base import BaseObject
from app.core.context import current_user_id
from app.core.id import generate_id


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类（元数据 / 注册表）。"""


class BaseModel(Base, BaseObject):
    """ORM 模型基类（L0）：每表必备字段与约定，模块模型继承之。

    - `id`：雪花 ID（BIGINT，应用侧生成，禁用数据库自增列）
    - 审计：`created_at` / `created_by` / `updated_at` / `updated_by`（ORM 事件自动填充）
    - 软删除：`deleted_at`（NULL=未删）；唯一约束建为 `(唯一字段, deleted_at)` 复合唯一
    - 乐观锁：`version`（`version_id_col` 自动比对 / 自增，冲突抛 `StaleDataError`）
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=generate_id, comment="主键（雪花 ID）")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间（UTC）")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="创建人")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="更新时间（UTC）")
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="更新人")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, comment="软删除时间（NULL=未删）"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="乐观锁版本")

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


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
