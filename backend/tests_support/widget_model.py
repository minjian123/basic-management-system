"""测试专用 ORM 模型（ORM 基类用例用）。

为什么单列：`Widget` 只存在于测试库，不进生产模型元数据；表由**初始化阶段**建好
（`tests_support.shared_db.prepare_platform` 调用本模块的 `ensure_widget_table`），
用例不再自己建库 / 建表。
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import String, Table, UniqueConstraint, create_engine
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class Widget(BaseModel):
    """测试模型：带 `(name, deleted_at)` 复合唯一，用于验证基类软删与乐观锁。"""

    __tablename__ = "widget"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_widget_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(16))


def ensure_widget_table(url: str) -> None:
    """在给定库建 `widget` 表（幂等；同步，供初始化阶段调用）。

    Args:
        url: 数据库连接串（可为 `sqlite+aiosqlite:///…`）。
    """
    engine = create_engine(url.replace("+aiosqlite", ""))
    try:
        cast("Table", Widget.__table__).create(engine, checkfirst=True)
    finally:
        engine.dispose()
