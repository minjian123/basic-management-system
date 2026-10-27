"""能力取用单点入口：`resolve_capability(name)`（消费方不得自拼服务键 / 路径 / 动作名）。

- **第一段**：能力名 → 能力记录（读装载视图 `collaboration_catalog_view()`，能力不落库）；
- **第二段**：业务域 → 部署单元与库（`topology.resolve_topology()`，实现可替换）；
- **失败**：能力未声明 / 已禁用 → 抛 `ParamError`（10001，消息含能力名，**不返回空值**）；
  业务域未登记 → 抛 `CatalogError`（配置缺失，拒启级）。

性能口径：视图量级为「产品数 × 域内能力数」（个位数到数十），取用按插入序遍历，不建第二份索引
（视图即唯一事实源，装载 / 复位即时生效）。
"""

from bms_core.collaboration.base import CapabilityEndpoint
from bms_core.collaboration.topology import resolve_topology
from bms_core.core.exceptions import ParamError
from bms_core.services.module_registry import (
    CollaborationRecord,
    CollaborationStatus,
    collaboration_catalog_view,
)

__all__ = ["resolve_capability"]


def resolve_capability(name: str) -> CapabilityEndpoint:
    """按能力名取用访问面与解析目标（单点入口）。

    Args:
        name: 能力名（`{产品}.{业务域}.{能力}`，全局唯一）。

    Returns:
        CapabilityEndpoint: 取用结果（冻结，消费方只读）。

    Raises:
        ParamError: 能力名为空、能力未声明（10001，消息含能力名）或能力已禁用（`status=disabled`）。
        CatalogError: 业务域未在部署拓扑登记（配置缺失）。
    """
    record = _find_record(name)
    target = resolve_topology().resolve(record.domain)
    return CapabilityEndpoint(
        name=record.name,
        domain=record.domain,
        kind=record.kind,
        contract_version=record.contract_version,
        target=target,
        path=record.path,
        branch_op=record.branch_op,
        branch_id=record.branch_id,
        data_source_key=record.data_source_key,
        permission_codes=record.permission_codes,
        product_key=record.product_key,
        frontend_prefix=record.frontend_prefix,
    )


def _find_record(name: str) -> CollaborationRecord:
    """按能力名定位装载的能力记录。

    Args:
        name: 能力名。

    Returns:
        CollaborationRecord: 能力记录（`enabled` / `deprecated` 均可取用）。

    Raises:
        ParamError: 能力名为空、未声明或已禁用（10001）。
    """
    if not name:
        raise ParamError("能力名不得为空（请检查调用方的能力名声明）")
    for record in collaboration_catalog_view():
        if record.name != name:
            continue
        if record.status == CollaborationStatus.DISABLED:
            raise ParamError(f"能力已禁用（status=disabled）：{name}（请检查产品清单 [[collaborations]] 的状态与装载）")
        return record
    raise ParamError(f"能力未声明：{name}（请检查产品清单 [[collaborations]] 与装载）")
