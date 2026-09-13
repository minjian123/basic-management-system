"""schemas 层排序契约：排序规格（SortSpec）与排序请求参数（BaseSortQuery）。

- 入参形态沿用《API接口规范》：`order_by` 逗号分隔多值 + `order` 方向数组（位置一一对应，缺省 desc）。
- 白名单外字段忽略该项；方向缺位 / 非法回退 desc；同一字段重复出现保留首次。
- 排序落地（内存排序 / ORDER BY）见 `app/repositories/base_repository.py`。
"""

from collections.abc import Collection, Sequence
from enum import StrEnum

from pydantic import Field

from app.schemas.base import BaseSchema


class SortDirection(StrEnum):
    """排序方向。"""

    ASC = "asc"
    DESC = "desc"


def _to_direction(value: str | None) -> SortDirection:
    """方向解析：`asc`（大小写不敏感）以外一律回退 `desc`。

    Args:
        value: 原始方向值（可能缺位或非法）。

    Returns:
        SortDirection: 归一化后的方向。
    """
    return SortDirection.ASC if value == SortDirection.ASC.value else SortDirection.DESC


class SortSpec(BaseSchema):
    """单条排序规格：字段 + 方向。"""

    field: str = Field(description="排序字段（数据库字段名口径）")
    direction: SortDirection = Field(default=SortDirection.DESC, description="排序方向（缺省降序）")

    @classmethod
    def parse(cls, order_by: str | None, order: Sequence[str] | None = None) -> list[SortSpec]:
        """解析原始排序参数为规格列表。

        Args:
            order_by: 排序字段（逗号分隔多值）；空 / None 表示不排序。
            order: 方向数组，与字段位置一一对应（缺位回退 desc）。

        Returns:
            list[SortSpec]: 排序规格列表（字段去重保留首次）。
        """
        names = [name.strip() for name in (order_by or "").split(",")]
        directions = [str(item).strip().lower() for item in (order or [])]
        specs: list[SortSpec] = []
        seen: set[str] = set()
        for index, name in enumerate(names):
            if not name or name in seen:
                continue
            seen.add(name)
            direction = _to_direction(directions[index] if index < len(directions) else None)
            specs.append(cls(field=name, direction=direction))
        return specs

    @classmethod
    def allowed(cls, specs: Sequence[SortSpec], whitelist: Collection[str]) -> list[SortSpec]:
        """按白名单过滤排序规格（白名单外字段忽略该项，保持原顺序）。

        Args:
            specs: 排序规格列表。
            whitelist: 可排序字段白名单。

        Returns:
            list[SortSpec]: 过滤后的排序规格列表。
        """
        return [spec for spec in specs if spec.field in whitelist]


class BaseSortQuery(BaseSchema):
    """排序请求契约：`order_by`（逗号分隔）+ `order`（方向数组，位置对应、缺省 desc）。"""

    order_by: str | None = Field(default=None, description="排序字段，逗号分隔多值（如 status,created_at）")
    order: list[str] | None = Field(default=None, description="排序方向数组，与 order_by 位置一一对应，缺省 desc")

    def specs(self, whitelist: Collection[str] | None = None) -> list[SortSpec]:
        """解析为校验后的排序规格列表。

        Args:
            whitelist: 可排序字段白名单；None 表示不做白名单过滤（仅限内部可信调用，用户输入禁止走此路径）。

        Returns:
            list[SortSpec]: 排序规格列表（白名单外字段已忽略）。
        """
        specs = SortSpec.parse(self.order_by, self.order)
        if whitelist is None:
            return specs
        return SortSpec.allowed(specs, whitelist)
