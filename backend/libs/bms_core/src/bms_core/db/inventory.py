"""库数量统计（06_02）：按库类别与服务的库数量观测内核（纯计算，不连库）。

- **预期库数**（配置与登记口径）：平台服务库 = 启用服务数；服务租户库 = 启用服务数 × 租户数；
  归档库 = 1（不服务化，统一收存）；
- **活跃库数**（运行期口径）：`EngineRegistry.db_counts()` 按库类别统计**当前活跃引擎**数，
  反映「活跃租户懒加载与闲置回收」的实际水位；
- 指标口径：`bms_db_count`（gauge，标签 `kind` / `service`），由启动期与引擎新建 / 回收时记录
  （见 `db/registry.py`；Prometheus 暴露端点归阶段八 08_01）。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from bms_core.core.base import BaseObject
from bms_core.db.keys import parse_db_key

__all__ = ["DbCount", "db_count_rows", "db_counts_by_kind", "db_counts_from_keys"]


@dataclass(frozen=True)
class DbCount(BaseObject):
    """库数量统计（按库类别）。"""

    services: int
    """启用服务数（平台服务库数量）。"""

    tenants: int
    """租户数（服务租户库 = 服务数 × 租户数）。"""

    @property
    def platform(self) -> int:
        """平台服务库数量（= 启用服务数）。

        Returns:
            int: 平台服务库数量。
        """
        return self.services

    @property
    def tenant(self) -> int:
        """服务租户库数量（= 服务数 × 租户数）。

        Returns:
            int: 服务租户库数量。
        """
        return self.services * self.tenants

    @property
    def archive(self) -> int:
        """归档库数量（不服务化，恒为 1）。

        Returns:
            int: 归档库数量。
        """
        return 1

    @property
    def total(self) -> int:
        """库总数（平台服务库 + 服务租户库 + 归档库）。

        Returns:
            int: 库总数。
        """
        return self.platform + self.tenant + self.archive

    def describe(self) -> str:
        """展示文案（含分类明细）。

        Returns:
            str: 展示文本。
        """
        return f"共 {self.total} 个库（平台服务库 {self.platform}、服务租户库 {self.tenant}、归档库 {self.archive}）"


def db_count_rows(services: Sequence[str], tenants: Sequence[str]) -> DbCount:
    """按「服务 × 租户」计算预期库数量（纯计算）。

    Args:
        services: 服务标识集合（取服务目录已启用服务）。
        tenants: 租户编码集合。

    Returns:
        DbCount: 库数量统计。
    """
    return DbCount(services=len(tuple(services)), tenants=len(tuple(tenants)))


def db_counts_by_kind(active_keys: Sequence[str]) -> dict[str, int]:
    """按库类别统计活跃引擎数（非法键忽略，不因历史键形态失败）。

    Args:
        active_keys: 活跃数据源键集合（`EngineRegistry.active_keys()`）。

    Returns:
        dict[str, int]: 库类别 → 活跃数（仅含有值的类别）。
    """
    counts: dict[str, int] = {}
    for key in active_keys:
        try:
            kind = parse_db_key(key).kind
        except Exception:  # 记账路径不因历史键形态失败
            continue
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def db_counts_from_keys(active_keys: Sequence[str]) -> DbCount:
    """按活跃库键折算库数量统计（活跃口径；归档恒 1）。

    Args:
        active_keys: 活跃数据源键集合。

    Returns:
        DbCount: 活跃口径库数量统计。
    """
    counts = db_counts_by_kind(active_keys)
    return DbCount(services=counts.get("platform", 0), tenants=counts.get("tenant", 0))
