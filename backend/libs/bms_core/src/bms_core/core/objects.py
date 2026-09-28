"""core 层体系基类：值对象 / 数据契约 / 框架对象三个体系根（《架构设计 · 后端基础类体系》）。

- `BaseValueObject`：不可变值对象体系根（`@dataclass(frozen=True)`）——frozen / 相等 / 哈希语义由
  dataclass 生成；子类继续以 `@dataclass(frozen=True)` 声明字段。
- `BaseDataContract`：可变数据契约体系根（`@dataclass`）——Pydantic 契约（`BaseSchema`）、ORM 模型
  （`BaseModel`）与普通数据类共用归口。
- `BaseFrameworkObject`：框架对象体系根——**非数据对象**（不参与值语义与序列化输出），统一标识
  `object_kind`，并提供可选生命周期钩子位 `aclose`（默认空操作；`BaseAsyncResource` 覆写为抽象）。

**严禁上帝基类**：`BaseObject` 仅为**唯一根系**；除**体系根**（本模块三类 + 集合 `BaseSorted` + 仓储
`BaseRepository` + 服务 `BaseService` + 事务 `UnitOfWork`，见《后端基类清单》§10「体系根清单」）外，
**禁止直接继承 `BaseObject`**——由 `scripts/tools/base-check/check-backend-base.py` 的「直继承合法性」
检查硬校验；存量尚未归位者以 `deploy/boundaries/direct_base_object_baseline.json` 豁免并递减。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.base import BaseObject

__all__ = [
    "FRAMEWORK_OBJECT_KIND",
    "BaseDataContract",
    "BaseFrameworkObject",
    "BaseValueObject",
]

FRAMEWORK_OBJECT_KIND = "framework"
"""框架对象缺省标识（子层覆写，如 `capability` / `middleware` / `registry`）。"""


@dataclass(frozen=True)
class BaseValueObject(BaseObject):
    """不可变值对象体系根。

    frozen / 相等 / 哈希语义由 dataclass 生成（`@dataclass(frozen=True)`）；子类必须以
    `@dataclass(frozen=True)` 声明字段（frozen 一致性由 dataclass 自身强制）；序列化沿用
    `BaseObject.to_dict` / `to_json`。
    """


@dataclass
class BaseDataContract(BaseObject):
    """可变数据契约体系根。

    Pydantic 契约（`BaseSchema`）、ORM 模型（`BaseModel`）与普通可变数据类共用归口；字段由子类以
    `@dataclass` 声明（或由 Pydantic / SQLAlchemy 元类生成）。**实测**：作为混入父类与
    `pydantic.BaseModel` / `sqlalchemy.DeclarativeBase` 组合无冲突。
    """


class BaseFrameworkObject(BaseObject):
    """框架对象体系根：非数据对象（不参与值语义与序列化输出）。

    框架对象（能力域 / 插件 / 占位 / 中间件 / 注册表 / 服务类 / 接口基类等）不承载业务数据，
    因此不参与值语义与序列化输出；本类提供统一标识 `object_kind` 与可选生命周期钩子位 `aclose`。
    """

    object_kind: ClassVar[str] = FRAMEWORK_OBJECT_KIND
    """框架对象统一标识（子层覆写，如 `capability` / `middleware` / `registry`）。"""

    async def aclose(self) -> None:
        """可选生命周期钩子位（默认空操作）。

        `BaseAsyncResource` 覆写为抽象方法，需要释放异步资源的子类经该入口统一回收。
        """
