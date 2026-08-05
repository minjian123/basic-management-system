"""SQLAlchemy 模型基类与混入。

四类混入 + 统一基类，全部模型必须继承（见《阶段一_项目骨架说明》7.5 节）：
- SnowflakeIdMixin：雪花 ID 主键（yitter/IdGenerator，Python 侧生成，worker_id 来自配置）
- AuditMixin：created_at/created_by/updated_at/updated_by，ORM 事件自动填充，UTC 存储
- SoftDeleteMixin：deleted_at 软删除；查询默认过滤由仓储层统一实现（阶段三）；唯一约束按 (唯一字段, deleted_at) 复合索引
- OptimisticLockMixin：version 乐观锁，更新时自动递增
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from ..core.config import get_settings
from ..core.snowflake import DefaultIdGenerator, IdGeneratorOptions

_id_generator = DefaultIdGenerator()
_generator_initialized = False


def next_id() -> int:
    """生成下一个雪花 ID（worker_id 取自配置，首次调用时初始化）。"""
    global _generator_initialized
    if not _generator_initialized:
        options = IdGeneratorOptions(worker_id=get_settings().snowflake.worker_id)
        _id_generator.set_id_generator(options)
        _generator_initialized = True
    return _id_generator.next_id()


class Base(DeclarativeBase):
    """全部 SQLAlchemy 模型的统一基类。"""


class SnowflakeIdMixin:
    """雪花 ID 主键（Python 侧生成）。"""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False, default=next_id)


class AuditMixin:
    """审计字段：ORM 事件自动填充（created_by/updated_by 阶段二认证接入后填充）。"""

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SoftDeleteMixin:
    """软删除标记：删除写入 deleted_at 时间戳；唯一约束建 (唯一字段, deleted_at) 复合索引。"""

    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class OptimisticLockMixin:
    """乐观锁：version 字段，更新时自动递增（并发比对在业务层完成）。"""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def _audit_before_insert(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    """新增前填充审计字段（created_at/updated_at 初始化，审计字段不允许业务侧设置）。"""
    _ = (mapper, connection)
    if isinstance(target, AuditMixin):
        now = dt.datetime.now(dt.UTC)
        target.created_at = now
        target.updated_at = now


def _audit_before_update(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    """更新前刷新 updated_at 并递增乐观锁 version。"""
    _ = (mapper, connection)
    if isinstance(target, AuditMixin):
        target.updated_at = dt.datetime.now(dt.UTC)
    if isinstance(target, OptimisticLockMixin):
        target.version = (target.version or 0) + 1


event.listen(Mapper, "before_insert", _audit_before_insert)
event.listen(Mapper, "before_update", _audit_before_update)
