"""帮助覆盖率台账契约（`GET /api/v1/help/coverage`，08_04）。

结构与 `bms_core.help.coverage.ledger_payload` 一一对应：命令行的 `--format json` 与接口返回同构，
便于阶段报告、CI 产物与后台页面共用一份口径。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, SnowflakeIdStr

__all__ = [
    "HelpCoverageActionFallbackItem",
    "HelpCoverageAnchorCountsItem",
    "HelpCoverageBaselineDiffItem",
    "HelpCoverageCountsItem",
    "HelpCoverageCoveredItem",
    "HelpCoverageExemptionItem",
    "HelpCoverageExemptionsItem",
    "HelpCoverageGroupItem",
    "HelpCoverageGroupReferenceItem",
    "HelpCoverageOrphanItem",
    "HelpCoverageReconciliationItem",
    "HelpCoverageReferenceItem",
    "HelpCoverageResponse",
    "HelpCoverageScopeItem",
    "HelpCoverageSummaryItem",
    "HelpCoverageUnitItem",
    "HelpCoverageVerdictItem",
]


class HelpCoverageCountsItem(BaseSchema):
    """一组覆盖计数（动作 / 菜单 / 参考）。"""

    total: int = Field(description="分母总数")
    covered: int = Field(description="已声明 help_key 数")
    exempt: int = Field(description="有效豁免数")
    gap: int = Field(description="豁免后缺口（未声明且无有效豁免）")
    coverage: float = Field(description="原始覆盖率（已声明 / 总数；总数为 0 记 1.0）")
    effective_coverage: float = Field(description="豁免后有效率（（已声明 + 有效豁免）/ 总数）")


class HelpCoverageActionFallbackItem(BaseSchema):
    """动作码兜底参考（不计入分母）。"""

    declared: int = Field(description="已声明动作码兜底锚点数")
    total: int = Field(description="动作码总数")
    gap: int = Field(description="未声明动作码兜底数")


class HelpCoverageReferenceItem(BaseSchema):
    """全局参考统计（表单 / 字段 / 动作码兜底）。"""

    form: HelpCoverageCountsItem = Field(description="表单参考统计")
    field: HelpCoverageCountsItem = Field(description="字段参考统计")
    action_fallback: HelpCoverageActionFallbackItem = Field(description="动作码兜底参考统计")


class HelpCoverageGroupReferenceItem(BaseSchema):
    """分组内表单 / 字段参考计数。"""

    form_total: int = Field(description="表单总数")
    form_declared: int = Field(description="表单锚点已登记数")
    field_total: int = Field(description="字段总数")
    field_declared: int = Field(description="字段锚点已登记数")


class HelpCoverageGroupItem(BaseSchema):
    """一个产品 / 模块分组。"""

    product_key: str = Field(description="产品键")
    module_key: str = Field(description="模块键（未登记业务码时即业务码）")
    action: HelpCoverageCountsItem = Field(description="动作覆盖计数")
    menu: HelpCoverageCountsItem = Field(description="菜单覆盖计数")
    reference: HelpCoverageGroupReferenceItem = Field(description="表单 / 字段参考计数")


class HelpCoverageExemptionItem(BaseSchema):
    """一条缺口豁免。"""

    kind: str = Field(description="类别（action / menu）")
    key: str = Field(description="动作码（业务码:动作码）或菜单路径")
    owner: str = Field(description="归口任务 / 责任人")
    reason: str = Field(description="豁免理由")
    expires_at: str = Field(description="失效日期（YYYY-MM-DD，含当日有效）")
    product_key: str | None = Field(default=None, description="可选产品段（与台账推导值一致）")


class HelpCoverageExemptionsItem(BaseSchema):
    """豁免判定结果。"""

    applied: Annotated[ConcurrentStableList[HelpCoverageExemptionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="生效豁免"
    )
    expired: Annotated[ConcurrentStableList[HelpCoverageExemptionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="过期豁免（仍计缺口）"
    )
    stale: Annotated[ConcurrentStableList[HelpCoverageExemptionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="陈旧豁免（基准中不存在）"
    )


class HelpCoverageUnitItem(BaseSchema):
    """一条覆盖明细（缺口 / 豁免 / 已覆盖）。"""

    kind: str = Field(description="类别（action / menu）")
    key: str = Field(description="动作码（业务码:动作码）或菜单路径")
    product_key: str = Field(description="产品键")
    module_key: str = Field(description="模块键")
    business_code: str = Field(description="归属业务码")
    action_code: str | None = Field(default=None, description="动作码（菜单为 null）")
    menu_paths: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="关联菜单路径"
    )
    model_id: SnowflakeIdStr = Field(description="元数据主键")
    help_key: str | None = Field(default=None, description="该行锚点（未登记为 null）")
    covered: bool = Field(description="是否已声明锚点")
    status: str = Field(description="状态（covered / gap / exempt）")
    exempt: HelpCoverageExemptionItem | None = Field(default=None, description="命中的有效豁免")
    fallback_help_key: str | None = Field(default=None, description="动作码兜底锚点（参考）")
    multi_business: bool = Field(default=False, description="菜单挂多个业务码")


class HelpCoverageAnchorCountsItem(BaseSchema):
    """按节点类型的锚点计数。"""

    menu: int = Field(description="菜单锚点数")
    form: int = Field(description="表单锚点数")
    field: int = Field(description="字段锚点数")
    button: int = Field(description="按钮锚点数")
    action: int = Field(description="动作码锚点数")


class HelpCoverageOrphanItem(BaseSchema):
    """不在覆盖基准内、但登记了锚点的行。"""

    kind: str = Field(description="类别（menu / action）")
    table: str = Field(description="逻辑表名")
    model_id: SnowflakeIdStr = Field(description="记录主键")
    help_key: str = Field(description="锚点值")
    reason: str = Field(description="未进入基准的原因")


class HelpCoverageCoveredItem(BaseSchema):
    """基准内已覆盖计数。"""

    menu: int = Field(description="已声明锚点的菜单数")
    action: int = Field(description="已声明锚点的动作数")


class HelpCoverageReconciliationItem(BaseSchema):
    """覆盖数与已登记锚点的对账结果。"""

    anchors: HelpCoverageAnchorCountsItem = Field(description="五类锚点计数")
    covered: HelpCoverageCoveredItem = Field(description="基准内已覆盖的菜单 / 动作计数")
    orphans: Annotated[ConcurrentStableList[HelpCoverageOrphanItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="基准外锚点"
    )
    reference_anchor_counts: HelpCoverageAnchorCountsItem = Field(description="表单 / 字段 / 动作码参考锚点数")
    duplicate_help_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="跨表重复锚点（应为空）"
    )
    consistent: bool = Field(description="覆盖数 + 孤儿数 = 锚点总数且无重复锚点")


class HelpCoverageScopeItem(BaseSchema):
    """本次台账的过滤范围。"""

    product_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="产品过滤"
    )
    module_keys: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="模块过滤"
    )
    kinds: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="明细类别过滤"
    )
    include_covered: bool = Field(description="明细是否包含已覆盖行")


class HelpCoverageBaselineDiffItem(BaseSchema):
    """与上次台账快照的对比。"""

    baseline_as_of: str = Field(description="基线快照日期")
    action_coverage_delta: float = Field(description="动作原始覆盖率变化")
    menu_coverage_delta: float = Field(description="菜单原始覆盖率变化")
    new_gaps: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="新增缺口"
    )
    cleared_gaps: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="已消除缺口"
    )
    still_gaps: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="仍存在的缺口"
    )


class HelpCoverageVerdictItem(BaseSchema):
    """阻断判定（接口只读展示，不改变服务行为）。"""

    blocked: bool = Field(description="强档是否阻断")
    action_gap: int = Field(description="动作豁免后缺口")
    menu_gap: int = Field(description="菜单豁免后缺口")
    consistent: bool = Field(description="对账是否一致")


class HelpCoverageSummaryItem(BaseSchema):
    """台账摘要。"""

    action: HelpCoverageCountsItem = Field(description="动作覆盖计数")
    menu: HelpCoverageCountsItem = Field(description="菜单覆盖计数")
    reference: HelpCoverageReferenceItem = Field(description="参考统计")


class HelpCoverageResponse(BaseSchema):
    """帮助覆盖率台账响应。"""

    schema_version: int = Field(description="结构版本")
    kind: str = Field(description="载荷类型（固定 help-coverage）")
    as_of: str = Field(description="判定日期（YYYY-MM-DD）")
    scope: HelpCoverageScopeItem = Field(description="过滤范围")
    summary: HelpCoverageSummaryItem = Field(description="摘要")
    groups: Annotated[ConcurrentStableList[HelpCoverageGroupItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分产品 / 模块台账"
    )
    units: Annotated[ConcurrentStableList[HelpCoverageUnitItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="明细（默认缺口与豁免）"
    )
    exemptions: HelpCoverageExemptionsItem = Field(description="豁免判定结果")
    reconciliation: HelpCoverageReconciliationItem = Field(description="锚点对账")
    verdict: HelpCoverageVerdictItem = Field(description="阻断判定")
    baseline_diff: HelpCoverageBaselineDiffItem | None = Field(default=None, description="基线对比（接口恒为 null）")
