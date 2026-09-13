"""demo 示例模块：ORM 模型（继承 BaseModel）。"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Demo(BaseModel):
    """demo 示例实体（ORM 模型；示例模块，表前缀按注册制登记）。"""

    __tablename__ = "demo"

    name: Mapped[str] = mapped_column(String(64), comment="demo 名称")
