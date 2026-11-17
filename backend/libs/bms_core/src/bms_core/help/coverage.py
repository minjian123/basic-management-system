"""帮助覆盖率台账（08_04）：基准选择、分组、豁免、双覆盖率、锚点对账与三渲染器。

口径（2026-11-17 拍板，见任务 08_04 详细设计）：

- **动作基准** = 启用且权限码有效的 `sys_button`，每按钮一个动作点；仅按钮 `help_key` 非空算覆盖，
  动作码全局兜底只作参考；
- **菜单基准** = 启用、有组件、至少挂一个表单、其业务码至少有一个权限码的 `sys_menu`；
- **分组** = `sys_module`（`product_key + module_key`）优先；平台业务码不在登记表时以业务码兼作模块名、
  产品段 `platform`；
- **覆盖口径** = 声明覆盖率（`help_key` 非空）；表单 / 字段 / 动作码兜底只作参考统计；
- **确定性** = 固定排序、固定浮点格式、`as_of` 显式入参，无隐式时间戳；同一输入两次输出逐字节一致。

本模块是**纯函数引擎**（不连库、不读文件）：快照由
`bms_core.repositories.help_coverage.load_help_coverage_snapshot` 提供，豁免文件由
`load_help_coverage_exemptions` 解析；命令行与接口共用同一引擎，保证数字一致。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.help.anchors import PLATFORM_PRODUCT_KEY, HelpAnchorKind

__all__ = [
    "COVERAGE_KIND_ACTION",
    "COVERAGE_KIND_MENU",
    "HELP_COVERAGE_SCHEMA_VERSION",
    "HelpCoverageAction",
    "HelpCoverageAnchor",
    "HelpCoverageAnchorCounts",
    "HelpCoverageBaselineDiff",
    "HelpCoverageCounts",
    "HelpCoverageExemption",
    "HelpCoverageExemptionError",
    "HelpCoverageExemptionSet",
    "HelpCoverageFallback",
    "HelpCoverageGroup",
    "HelpCoverageGroupReference",
    "HelpCoverageLedger",
    "HelpCoverageMenu",
    "HelpCoverageModule",
    "HelpCoverageOrphan",
    "HelpCoverageReconciliation",
    "HelpCoverageReference",
    "HelpCoverageReferenceRow",
    "HelpCoverageScope",
    "HelpCoverageSnapshot",
    "HelpCoverageUnit",
    "build_baseline_diff",
    "build_help_coverage_ledger",
    "ledger_is_blocked",
    "ledger_payload",
    "load_help_coverage_exemptions",
    "render_json",
    "render_markdown",
    "render_text",
]

_LOGGER = get_logger("bms.help")
"""帮助域日志（模块冲突 / 孤儿锚点等只告警，不阻断台账生成）。"""

HELP_COVERAGE_SCHEMA_VERSION = 1
"""台账 / 豁免 / 基线的结构版本（不兼容变更时递增）。"""

COVERAGE_KIND_ACTION = "action"
"""覆盖单元类别：动作（按钮）。"""

COVERAGE_KIND_MENU = "menu"
"""覆盖单元类别：菜单。"""

_UNIT_STATUS_COVERED = "covered"
_UNIT_STATUS_GAP = "gap"
_UNIT_STATUS_EXEMPT = "exempt"

_KIND_ORDER: ConcurrentStableDict[str, int] = ConcurrentStableDict({COVERAGE_KIND_ACTION: 0, COVERAGE_KIND_MENU: 1})
"""明细排序：动作先于菜单。"""

_EXEMPTION_TOP_KEYS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet({"schema_version", "exemptions"})
"""豁免文件顶层允许键。"""

_EXEMPTION_KEYS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    {"kind", "key", "owner", "reason", "expires_at", "product_key"}
)
"""豁免条目允许键。"""

_EXEMPTION_MIN_REASON_LENGTH = 10
"""豁免理由最小长度（防止「暂时跳过」式空话）。"""


class HelpCoverageExemptionError(ValueError):
    """豁免文件非法（结构 / 字段 / 重复 / 产品不符）。"""


class HelpCoverageBaselineError(ValueError):
    """基线台账结构不可解析。"""


@dataclass(frozen=True)
class HelpCoverageAction(BaseValueObject):
    """一个动作点（按钮快照；已由仓储完成权限码 / 表单 / 菜单关联）。

    Attributes:
        model_id: 按钮主键。
        business_code: 权限码业务段。
        action_code: 权限码动作段。
        button_name: 按钮名（人读定位）。
        menu_paths: 该按钮所属表单挂接的菜单路径（升序）。
        help_key: 按钮行锚点（`None` = 未登记）。
        fallback_help_key: 动作码全局兜底锚点（参考，不计覆盖）。
    """

    model_id: int
    business_code: str
    action_code: str
    button_name: str
    menu_paths: ConcurrentStableFrozenList[str]
    help_key: str | None
    fallback_help_key: str | None


@dataclass(frozen=True)
class HelpCoverageMenu(BaseValueObject):
    """一个菜单点（快照）。

    Attributes:
        model_id: 菜单主键。
        path: 菜单路径（未软删唯一）。
        business_codes: 经挂接表单推导的业务码（升序；空 = 无启用表单）。
        help_key: 菜单行锚点（`None` = 未登记）。
    """

    model_id: int
    path: str
    business_codes: ConcurrentStableFrozenList[str]
    help_key: str | None


@dataclass(frozen=True)
class HelpCoverageModule(BaseValueObject):
    """业务码到产品 / 模块的登记映射。

    Attributes:
        business_code: 业务码。
        product_key: 产品键。
        module_key: 模块键。
        registered: 是否来自 `sys_module`（`False` = 业务码兼作模块名）。
    """

    business_code: str
    product_key: str
    module_key: str
    registered: bool


@dataclass(frozen=True)
class HelpCoverageReferenceRow(BaseValueObject):
    """表单 / 字段参考统计行（不计入覆盖率分母）。

    Attributes:
        business_code: 所属业务码。
        kind: `form` / `field`。
        help_key: 该行锚点。
    """

    business_code: str
    kind: str
    help_key: str | None


@dataclass(frozen=True)
class HelpCoverageFallback(BaseValueObject):
    """动作码兜底锚点（参考）。

    Attributes:
        action_code: 动作码。
        help_key: 全局兜底锚点。
    """

    action_code: str
    help_key: str | None


@dataclass(frozen=True)
class HelpCoverageAnchor(BaseValueObject):
    """一条已登记锚点（与仓储解耦的最小快照）。

    Attributes:
        kind: 节点类型。
        table: 逻辑表名。
        model_id: 记录主键。
        help_key: 锚点值。
    """

    kind: HelpAnchorKind
    table: str
    model_id: int
    help_key: str


@dataclass(frozen=True)
class HelpCoverageSnapshot(BaseValueObject):
    """平台元数据只读快照（覆盖率引擎的唯一输入）。

    Attributes:
        actions: 动作点（按钮）。
        menus: 菜单点。
        modules: 业务码 → 产品 / 模块映射。
        reference_rows: 表单 / 字段参考行。
        action_fallbacks: 动作码兜底锚点。
        anchors: 全部已登记锚点（跨五表）。
        business_codes_with_permission: 至少有一个启用权限码的业务码。
    """

    actions: ConcurrentStableFrozenList[HelpCoverageAction]
    menus: ConcurrentStableFrozenList[HelpCoverageMenu]
    modules: ConcurrentStableFrozenList[HelpCoverageModule]
    reference_rows: ConcurrentStableFrozenList[HelpCoverageReferenceRow]
    action_fallbacks: ConcurrentStableFrozenList[HelpCoverageFallback]
    anchors: ConcurrentStableFrozenList[HelpCoverageAnchor]
    business_codes_with_permission: ConcurrentStableFrozenList[str]


@dataclass(frozen=True)
class HelpCoverageExemption(BaseValueObject):
    """一条缺口登记豁免。

    Attributes:
        kind: `action` / `menu`。
        key: 动作码 `业务码:动作码` 或菜单路径。
        owner: 归口任务 / 责任人。
        reason: 豁免理由。
        expires_at: 失效日期（含当日有效）。
        product_key: 可选产品段；给出时须与台账推导值一致。
    """

    kind: str
    key: str
    owner: str
    reason: str
    expires_at: date
    product_key: str | None = None


@dataclass(frozen=True)
class HelpCoverageExemptionSet(BaseValueObject):
    """一次运行使用的豁免集合。

    Attributes:
        entries: 已解析的豁免条目。
        paths: 实际读取的文件路径（人读留痕）。
    """

    entries: ConcurrentStableFrozenList[HelpCoverageExemption]
    paths: ConcurrentStableFrozenList[str]


@dataclass(frozen=True)
class HelpCoverageScope(BaseValueObject):
    """本次台账的过滤范围。

    Attributes:
        product_keys: 产品过滤（空 = 全部）。
        module_keys: 模块过滤（空 = 全部）。
        kinds: 明细类别过滤（空 = 全部）。
        include_covered: 明细是否包含已覆盖行。
    """

    product_keys: ConcurrentStableFrozenList[str]
    module_keys: ConcurrentStableFrozenList[str]
    kinds: ConcurrentStableFrozenList[str]
    include_covered: bool


@dataclass(frozen=True)
class HelpCoverageCounts(BaseValueObject):
    """一组覆盖计数。

    Attributes:
        total: 分母总数。
        covered: 已声明 `help_key` 数。
        exempt: 有效豁免数。
        gap: 豁免后缺口（未声明且无有效豁免）。
        coverage: 原始覆盖率（已声明 / 总数；总数为 0 记 1.0）。
        effective_coverage: 豁免后有效率（（已声明 + 有效豁免）/ 总数）。
    """

    total: int
    covered: int
    exempt: int
    gap: int
    coverage: float
    effective_coverage: float


@dataclass(frozen=True)
class HelpCoverageGroupReference(BaseValueObject):
    """分组内的表单 / 字段参考计数。

    Attributes:
        form_total: 表单总数。
        form_declared: 表单锚点已登记数。
        field_total: 字段总数。
        field_declared: 字段锚点已登记数。
    """

    form_total: int
    form_declared: int
    field_total: int
    field_declared: int


@dataclass(frozen=True)
class HelpCoverageReference(BaseValueObject):
    """全局参考统计（不计入分母）。

    Attributes:
        form: 表单统计。
        field: 字段统计。
        action_fallback_declared: 动作码兜底已声明数。
        action_fallback_total: 动作码兜底总数。
    """

    form: HelpCoverageCounts
    field: HelpCoverageCounts
    action_fallback_declared: int
    action_fallback_total: int


@dataclass(frozen=True)
class HelpCoverageGroup(BaseValueObject):
    """一个产品 / 模块分组。

    Attributes:
        product_key: 产品键。
        module_key: 模块键。
        actions: 动作计数。
        menus: 菜单计数。
        reference: 表单 / 字段参考计数。
    """

    product_key: str
    module_key: str
    actions: HelpCoverageCounts
    menus: HelpCoverageCounts
    reference: HelpCoverageGroupReference


@dataclass(frozen=True)
class HelpCoverageUnit(BaseValueObject):
    """一条覆盖明细（缺口 / 豁免 / 已覆盖）。

    Attributes:
        kind: `action` / `menu`。
        key: 动作码 `业务码:动作码` 或菜单路径。
        product_key: 产品键。
        module_key: 模块键。
        business_code: 归属业务码。
        action_code: 动作码（菜单为 `None`）。
        menu_paths: 关联菜单路径（动作 = 所属表单挂接菜单；菜单 = 自身路径）。
        model_id: 元数据主键。
        help_key: 该行锚点。
        covered: 是否已声明锚点。
        status: `covered` / `gap` / `exempt`。
        exemption: 命中的有效豁免（`None` = 未豁免）。
        fallback_help_key: 动作码兜底锚点（菜单为 `None`）。
        multi_business: 菜单挂多个业务码。
    """

    kind: str
    key: str
    product_key: str
    module_key: str
    business_code: str
    action_code: str | None
    menu_paths: ConcurrentStableFrozenList[str]
    model_id: int
    help_key: str | None
    covered: bool
    status: str
    exemption: HelpCoverageExemption | None
    fallback_help_key: str | None
    multi_business: bool = False


@dataclass(frozen=True)
class HelpCoverageAnchorCounts(BaseValueObject):
    """按节点类型的锚点计数。

    Attributes:
        menu: 菜单锚点数。
        form: 表单锚点数。
        field: 字段锚点数。
        button: 按钮锚点数。
        action: 动作码锚点数。
    """

    menu: int
    form: int
    field: int
    button: int
    action: int


@dataclass(frozen=True)
class HelpCoverageOrphan(BaseValueObject):
    """不在覆盖基准内、但登记了锚点的行（对账用）。

    Attributes:
        kind: `menu` / `action`（按钮）。
        table: 逻辑表名。
        model_id: 记录主键。
        help_key: 锚点值。
        reason: 未进入基准的原因（人读）。
    """

    kind: str
    table: str
    model_id: int
    help_key: str
    reason: str


@dataclass(frozen=True)
class HelpCoverageReconciliation(BaseValueObject):
    """覆盖数与 08_01 已登记锚点的对账结果。

    Attributes:
        anchors: 五类锚点计数。
        covered_menus: 基准内已声明锚点的菜单数。
        covered_actions: 基准内已声明锚点的动作数。
        orphans: 基准外的菜单 / 按钮锚点。
        reference_anchor_counts: 表单 / 字段 / 动作码参考锚点数（不进等式）。
        duplicate_help_keys: 跨表重复的锚点值（应为空）。
        consistent: 覆盖数 + 孤儿数 = 锚点总数，且无重复锚点。
    """

    anchors: HelpCoverageAnchorCounts
    covered_menus: int
    covered_actions: int
    orphans: ConcurrentStableFrozenList[HelpCoverageOrphan]
    reference_anchor_counts: HelpCoverageAnchorCounts
    duplicate_help_keys: ConcurrentStableFrozenList[str]
    consistent: bool


@dataclass(frozen=True)
class HelpCoverageBaselineDiff(BaseValueObject):
    """与上次台账快照的对比。

    Attributes:
        baseline_as_of: 基线快照日期。
        action_coverage_delta: 动作原始覆盖率变化。
        menu_coverage_delta: 菜单原始覆盖率变化。
        new_gaps: 新增缺口（`kind:key`）。
        cleared_gaps: 已消除缺口。
        still_gaps: 仍存在的缺口。
    """

    baseline_as_of: str
    action_coverage_delta: float
    menu_coverage_delta: float
    new_gaps: ConcurrentStableFrozenList[str]
    cleared_gaps: ConcurrentStableFrozenList[str]
    still_gaps: ConcurrentStableFrozenList[str]


@dataclass(frozen=True)
class HelpCoverageLedger(BaseValueObject):
    """帮助覆盖率台账（引擎输出；命令行 / 接口共用）。

    Attributes:
        as_of: 判定日期。
        scope: 过滤范围。
        actions: 动作摘要。
        menus: 菜单摘要。
        reference: 全局参考统计。
        groups: 分产品 / 模块台账。
        units: 明细（默认缺口与豁免；按范围可含已覆盖）。
        applied_exemptions: 生效豁免。
        expired_exemptions: 过期豁免（仍计缺口）。
        stale_exemptions: 陈旧豁免（基准中不存在）。
        reconciliation: 锚点对账。
        baseline_diff: 基线对比（无基线时为空）。
    """

    as_of: date
    scope: HelpCoverageScope
    actions: HelpCoverageCounts
    menus: HelpCoverageCounts
    reference: HelpCoverageReference
    groups: ConcurrentStableFrozenList[HelpCoverageGroup]
    units: ConcurrentStableFrozenList[HelpCoverageUnit]
    applied_exemptions: ConcurrentStableFrozenList[HelpCoverageExemption]
    expired_exemptions: ConcurrentStableFrozenList[HelpCoverageExemption]
    stale_exemptions: ConcurrentStableFrozenList[HelpCoverageExemption]
    reconciliation: HelpCoverageReconciliation
    baseline_diff: HelpCoverageBaselineDiff | None = None


def load_help_coverage_exemptions(
    paths: ConcurrentStableList[str],
    *,
    strict_paths: bool = False,
) -> HelpCoverageExemptionSet:
    """读取并校验豁免文件（缺省文件不存在视为空；显式路径缺失即报错）。

    Args:
        paths: 豁免文件路径（相对路径按当前工作目录解析）。
        strict_paths: `True` 时任一文件不存在即报错（命令行显式给出时用）。

    Returns:
        HelpCoverageExemptionSet: 已解析条目与实际读取路径。

    Raises:
        HelpCoverageExemptionError: 文件缺失（严格模式）/ 非 JSON / 结构或字段非法 / 重复。
    """
    entries: ConcurrentStableList[HelpCoverageExemption] = ConcurrentStableList()
    loaded: ConcurrentStableList[str] = ConcurrentStableList()
    seen: ConcurrentStableDict[tuple[str, str], str] = ConcurrentStableDict()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            if strict_paths:
                raise HelpCoverageExemptionError(f"豁免文件不存在：{raw_path}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HelpCoverageExemptionError(f"豁免文件不可读或不是合法 JSON：{raw_path}（{exc}）") from exc
        for entry in _parse_exemption_payload(payload, source=raw_path):
            pair = (entry.kind, entry.key)
            existing = seen.get(pair)
            if existing is not None:
                raise HelpCoverageExemptionError(
                    f"豁免条目重复：{entry.kind}:{entry.key}（已出现于 {existing}，又出现于 {raw_path}）"
                )
            seen.set(pair, raw_path)
            entries.add(entry)
        loaded.add(str(path))
    return HelpCoverageExemptionSet(
        entries=ConcurrentStableFrozenList(entries),
        paths=ConcurrentStableFrozenList(loaded),
    )


def _parse_exemption_payload(payload: object, *, source: str) -> ConcurrentStableList[HelpCoverageExemption]:
    """校验单份豁免文件并返回条目。

    Args:
        payload: `json.loads` 结果。
        source: 文件路径（错误信息定位）。

    Returns:
        ConcurrentStableList[HelpCoverageExemption]: 条目（保持文件顺序）。

    Raises:
        HelpCoverageExemptionError: 顶层 / 条目 / 字段 / 日期非法。
    """
    if not isinstance(payload, dict):
        raise HelpCoverageExemptionError(f"豁免文件顶层须为对象：{source}")
    payload_map = cast("dict[str, object]", payload)
    unknown_top = ConcurrentStableFrozenSet(payload_map.keys()) - _EXEMPTION_TOP_KEYS
    if unknown_top:
        raise HelpCoverageExemptionError(f"豁免文件含未知字段：{source} → {sorted(unknown_top)}")
    version = payload_map.get("schema_version")
    if version != HELP_COVERAGE_SCHEMA_VERSION:
        raise HelpCoverageExemptionError(
            f"豁免文件 schema_version 非法：{source} → {version!r}（须为 {HELP_COVERAGE_SCHEMA_VERSION}）"
        )
    raw_entries = payload_map.get("exemptions")
    if not isinstance(raw_entries, list):
        raise HelpCoverageExemptionError(f"豁免文件 exemptions 须为数组：{source}")
    entries: ConcurrentStableList[HelpCoverageExemption] = ConcurrentStableList()
    for index, raw_entry in enumerate(cast("list[object]", raw_entries), start=1):
        entries.add(_parse_exemption_entry(raw_entry, source=source, index=index))
    return entries


def _parse_exemption_entry(raw: object, *, source: str, index: int) -> HelpCoverageExemption:
    """校验单条豁免条目。

    Args:
        raw: 原始条目。
        source: 文件路径。
        index: 条目序号（从 1 起）。

    Returns:
        HelpCoverageExemption: 已校验条目。

    Raises:
        HelpCoverageExemptionError: 字段缺失 / 类型非法 / 日期非法。
    """
    prefix = f"{source} 第 {index} 条"
    if not isinstance(raw, dict):
        raise HelpCoverageExemptionError(f"{prefix}须为对象")
    entry_map = cast("dict[str, object]", raw)
    unknown = ConcurrentStableFrozenSet(entry_map.keys()) - _EXEMPTION_KEYS
    if unknown:
        raise HelpCoverageExemptionError(f"{prefix}含未知字段：{sorted(unknown)}")
    kind = entry_map.get("kind")
    if kind not in (COVERAGE_KIND_ACTION, COVERAGE_KIND_MENU):
        raise HelpCoverageExemptionError(f"{prefix} kind 非法：{kind!r}（须为 action / menu）")
    key = entry_map.get("key")
    if not isinstance(key, str) or not key.strip():
        raise HelpCoverageExemptionError(f"{prefix} key 缺失或为空")
    owner = entry_map.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise HelpCoverageExemptionError(f"{prefix} owner 缺失或为空")
    reason = entry_map.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < _EXEMPTION_MIN_REASON_LENGTH:
        raise HelpCoverageExemptionError(f"{prefix} reason 须为至少 {_EXEMPTION_MIN_REASON_LENGTH} 字的说明")
    raw_expires = entry_map.get("expires_at")
    if not isinstance(raw_expires, str):
        raise HelpCoverageExemptionError(f"{prefix} expires_at 缺失（须为 YYYY-MM-DD）")
    try:
        expires_at = date.fromisoformat(raw_expires)
    except ValueError as exc:
        raise HelpCoverageExemptionError(f"{prefix} expires_at 非法：{raw_expires!r}（须为 YYYY-MM-DD）") from exc
    raw_product = entry_map.get("product_key")
    if raw_product is not None and (not isinstance(raw_product, str) or not raw_product.strip()):
        raise HelpCoverageExemptionError(f"{prefix} product_key 非法：{raw_product!r}")
    return HelpCoverageExemption(
        kind=cast("str", kind),
        key=key.strip(),
        owner=owner.strip(),
        reason=reason.strip(),
        expires_at=expires_at,
        product_key=raw_product.strip() if isinstance(raw_product, str) else None,
    )


def build_help_coverage_ledger(
    snapshot: HelpCoverageSnapshot,
    *,
    as_of: date,
    exemptions: HelpCoverageExemptionSet | None = None,
    scope: HelpCoverageScope | None = None,
    baseline_diff: HelpCoverageBaselineDiff | None = None,
) -> HelpCoverageLedger:
    """构建覆盖率台账（纯函数；同一输入结果确定）。

    Args:
        snapshot: 平台元数据只读快照。
        as_of: 判定日期（豁免过期以它为准）。
        exemptions: 豁免集合（`None` = 无豁免）。
        scope: 过滤范围（`None` = 全部、明细不含已覆盖）。
        baseline_diff: 已算好的基线对比（命令行传入）。

    Returns:
        HelpCoverageLedger: 台账。

    Raises:
        HelpCoverageExemptionError: 豁免 `product_key` 与台账推导值不一致。
    """
    exemption_set = exemptions or HelpCoverageExemptionSet(
        entries=ConcurrentStableFrozenList(), paths=ConcurrentStableFrozenList()
    )
    active_scope = scope or HelpCoverageScope(
        product_keys=ConcurrentStableFrozenList(),
        module_keys=ConcurrentStableFrozenList(),
        kinds=ConcurrentStableFrozenList(),
        include_covered=False,
    )
    module_map = _build_module_map(snapshot)
    permission_businesses = ConcurrentStableFrozenSet(snapshot.business_codes_with_permission)
    all_units: ConcurrentStableList[HelpCoverageUnit] = ConcurrentStableList()
    for action in snapshot.actions:
        all_units.add(_action_unit(action, module_map, exemption_set, as_of))
    for menu in snapshot.menus:
        unit = _menu_unit(menu, module_map, permission_businesses, exemption_set, as_of)
        if unit is not None:
            all_units.add(unit)
    _validate_exemption_products(all_units, exemption_set)
    applied, expired, stale = _classify_exemptions(all_units, exemption_set, as_of)
    filtered_units = _filter_units(all_units, active_scope)
    groups = _build_groups(filtered_units, snapshot.reference_rows, module_map, active_scope)
    summary_actions = _counts(filtered_units, COVERAGE_KIND_ACTION)
    summary_menus = _counts(filtered_units, COVERAGE_KIND_MENU)
    reference = _build_reference(snapshot, module_map, active_scope)
    reconciliation = _build_reconciliation(all_units, snapshot.anchors)
    return HelpCoverageLedger(
        as_of=as_of,
        scope=active_scope,
        actions=summary_actions,
        menus=summary_menus,
        reference=reference,
        groups=ConcurrentStableFrozenList(groups),
        units=ConcurrentStableFrozenList(_visible_units(filtered_units, active_scope)),
        applied_exemptions=applied,
        expired_exemptions=expired,
        stale_exemptions=stale,
        reconciliation=reconciliation,
        baseline_diff=baseline_diff,
    )


def _build_module_map(snapshot: HelpCoverageSnapshot) -> ConcurrentStableDict[str, HelpCoverageModule]:
    """构建业务码 → 模块映射（登记表优先；冲突取字典序最小并告警）。

    Args:
        snapshot: 元数据快照。

    Returns:
        ConcurrentStableDict[str, HelpCoverageModule]: 映射。
    """
    mapping: ConcurrentStableDict[str, HelpCoverageModule] = ConcurrentStableDict()
    ordered = sorted(snapshot.modules, key=lambda row: (row.product_key, row.module_key, row.business_code))
    for module in ordered:
        existing = mapping.get(module.business_code)
        if existing is None:
            mapping.set(module.business_code, module)
            continue
        if (existing.product_key, existing.module_key) != (module.product_key, module.module_key):
            _LOGGER.warning(
                "help_coverage_module_conflict",
                business_code=module.business_code,
                kept=f"{existing.product_key}/{existing.module_key}",
                ignored=f"{module.product_key}/{module.module_key}",
            )
    return mapping


def _resolve_module(
    business_code: str, module_map: ConcurrentStableDict[str, HelpCoverageModule]
) -> HelpCoverageModule:
    """取业务码的模块归属（未登记 = 产品 platform + 模块名业务码）。

    Args:
        business_code: 业务码。
        module_map: 登记映射。

    Returns:
        HelpCoverageModule: 归属。
    """
    registered = module_map.get(business_code)
    if registered is not None:
        return registered
    return HelpCoverageModule(
        business_code=business_code,
        product_key=PLATFORM_PRODUCT_KEY,
        module_key=business_code,
        registered=False,
    )


def _action_unit(
    action: HelpCoverageAction,
    module_map: ConcurrentStableDict[str, HelpCoverageModule],
    exemptions: HelpCoverageExemptionSet,
    as_of: date,
) -> HelpCoverageUnit:
    """把动作快照转成覆盖单元。

    Args:
        action: 动作快照。
        module_map: 模块映射。
        exemptions: 豁免集合。
        as_of: 判定日期。

    Returns:
        HelpCoverageUnit: 覆盖单元。
    """
    module = _resolve_module(action.business_code, module_map)
    key = f"{action.business_code}:{action.action_code}"
    covered = action.help_key is not None
    exemption = _match_exemption(exemptions, COVERAGE_KIND_ACTION, key, as_of)
    status = _UNIT_STATUS_COVERED if covered else (_UNIT_STATUS_EXEMPT if exemption is not None else _UNIT_STATUS_GAP)
    return HelpCoverageUnit(
        kind=COVERAGE_KIND_ACTION,
        key=key,
        product_key=module.product_key,
        module_key=module.module_key,
        business_code=action.business_code,
        action_code=action.action_code,
        menu_paths=action.menu_paths,
        model_id=action.model_id,
        help_key=action.help_key,
        covered=covered,
        status=status,
        exemption=exemption,
        fallback_help_key=action.fallback_help_key,
    )


def _menu_unit(
    menu: HelpCoverageMenu,
    module_map: ConcurrentStableDict[str, HelpCoverageModule],
    permission_businesses: ConcurrentStableFrozenSet[str],
    exemptions: HelpCoverageExemptionSet,
    as_of: date,
) -> HelpCoverageUnit | None:
    """把菜单快照转成覆盖单元（不满足基准条件返回 `None`）。

    Args:
        menu: 菜单快照。
        module_map: 模块映射。
        permission_businesses: 有权限码的业务码集合。
        exemptions: 豁免集合。
        as_of: 判定日期。

    Returns:
        HelpCoverageUnit | None: 覆盖单元；目录 / 未挂表单 / 业务无权限码时为空。
    """
    candidates = ConcurrentStableList(sorted(code for code in menu.business_codes if code in permission_businesses))
    if not candidates:
        return None
    business_code = candidates[0]
    module = _resolve_module(business_code, module_map)
    covered = menu.help_key is not None
    exemption = _match_exemption(exemptions, COVERAGE_KIND_MENU, menu.path, as_of)
    status = _UNIT_STATUS_COVERED if covered else (_UNIT_STATUS_EXEMPT if exemption is not None else _UNIT_STATUS_GAP)
    return HelpCoverageUnit(
        kind=COVERAGE_KIND_MENU,
        key=menu.path,
        product_key=module.product_key,
        module_key=module.module_key,
        business_code=business_code,
        action_code=None,
        menu_paths=ConcurrentStableFrozenList((menu.path,)),
        model_id=menu.model_id,
        help_key=menu.help_key,
        covered=covered,
        status=status,
        exemption=exemption,
        fallback_help_key=None,
        multi_business=len(candidates) > 1,
    )


def _match_exemption(
    exemptions: HelpCoverageExemptionSet, kind: str, key: str, as_of: date
) -> HelpCoverageExemption | None:
    """取命中的有效豁免（过期不返回）。

    Args:
        exemptions: 豁免集合。
        kind: 单元类别。
        key: 单元键。
        as_of: 判定日期。

    Returns:
        HelpCoverageExemption | None: 有效豁免；未命中或已过期返回 `None`。
    """
    for entry in exemptions.entries:
        if entry.kind == kind and entry.key == key and entry.expires_at >= as_of:
            return entry
    return None


def _validate_exemption_products(
    units: ConcurrentStableList[HelpCoverageUnit], exemptions: HelpCoverageExemptionSet
) -> None:
    """校验豁免 `product_key` 与台账推导值一致。

    Args:
        units: 全部覆盖单元。
        exemptions: 豁免集合。

    Raises:
        HelpCoverageExemptionError: 产品段不一致。
    """
    products: ConcurrentStableDict[tuple[str, str], str] = ConcurrentStableDict(
        ((unit.kind, unit.key), unit.product_key) for unit in units
    )
    for entry in exemptions.entries:
        if entry.product_key is None:
            continue
        actual = products.get((entry.kind, entry.key))
        if actual is not None and actual != entry.product_key:
            raise HelpCoverageExemptionError(
                f"豁免 product_key 与台账不一致：{entry.kind}:{entry.key} → 文件 {entry.product_key!r}，台账 {actual!r}"
            )


def _classify_exemptions(
    units: ConcurrentStableList[HelpCoverageUnit],
    exemptions: HelpCoverageExemptionSet,
    as_of: date,
) -> tuple[
    ConcurrentStableFrozenList[HelpCoverageExemption],
    ConcurrentStableFrozenList[HelpCoverageExemption],
    ConcurrentStableFrozenList[HelpCoverageExemption],
]:
    """划分生效 / 过期 / 陈旧豁免。

    Args:
        units: 全部覆盖单元。
        exemptions: 豁免集合。
        as_of: 判定日期。

    Returns:
        tuple: （生效，过期，陈旧）三组豁免。
    """
    keys = ConcurrentStableFrozenSet((unit.kind, unit.key) for unit in units)
    applied: ConcurrentStableList[HelpCoverageExemption] = ConcurrentStableList()
    expired: ConcurrentStableList[HelpCoverageExemption] = ConcurrentStableList()
    stale: ConcurrentStableList[HelpCoverageExemption] = ConcurrentStableList()
    for entry in exemptions.entries:
        if (entry.kind, entry.key) not in keys:
            stale.add(entry)
        elif entry.expires_at < as_of:
            expired.add(entry)
        else:
            applied.add(entry)
    return (
        ConcurrentStableFrozenList(sorted(applied, key=_exemption_sort_key)),
        ConcurrentStableFrozenList(sorted(expired, key=_exemption_sort_key)),
        ConcurrentStableFrozenList(sorted(stale, key=_exemption_sort_key)),
    )


def _exemption_sort_key(entry: HelpCoverageExemption) -> tuple[str, str, str]:
    """豁免排序键（类别 / 键 / 失效日期）。

    Args:
        entry: 豁免条目。

    Returns:
        tuple[str, str, str]: 排序键。
    """
    return (entry.kind, entry.key, entry.expires_at.isoformat())


def _in_scope(unit: HelpCoverageUnit, scope: HelpCoverageScope) -> bool:
    """判断单元是否在过滤范围内。

    Args:
        unit: 覆盖单元。
        scope: 过滤范围。

    Returns:
        bool: 是否命中产品 / 模块过滤。
    """
    if scope.product_keys and unit.product_key not in scope.product_keys:
        return False
    return not (scope.module_keys and unit.module_key not in scope.module_keys)


def _filter_units(
    units: ConcurrentStableList[HelpCoverageUnit], scope: HelpCoverageScope
) -> ConcurrentStableList[HelpCoverageUnit]:
    """按产品 / 模块过滤（不做类别过滤；类别只影响明细）。

    Args:
        units: 全部覆盖单元。
        scope: 过滤范围。

    Returns:
        ConcurrentStableList[HelpCoverageUnit]: 过滤后的单元（保持构建顺序）。
    """
    return ConcurrentStableList(unit for unit in units if _in_scope(unit, scope))


def _visible_units(
    units: ConcurrentStableList[HelpCoverageUnit], scope: HelpCoverageScope
) -> ConcurrentStableList[HelpCoverageUnit]:
    """按类别与「是否含已覆盖」筛选明细。

    Args:
        units: 已按产品 / 模块过滤的单元。
        scope: 过滤范围。

    Returns:
        ConcurrentStableList[HelpCoverageUnit]: 明细（固定排序）。
    """
    visible = ConcurrentStableList(
        unit
        for unit in units
        if (not scope.kinds or unit.kind in scope.kinds)
        and (scope.include_covered or unit.status != _UNIT_STATUS_COVERED)
    )
    return ConcurrentStableList(sorted(visible, key=_unit_sort_key))


def _unit_sort_key(unit: HelpCoverageUnit) -> tuple[int, str, str, str]:
    """明细排序键（类别 / 产品 / 模块 / 键）。

    Args:
        unit: 覆盖单元。

    Returns:
        tuple[int, str, str, str]: 排序键。
    """
    return (_KIND_ORDER.get(unit.kind, 9), unit.product_key, unit.module_key, unit.key)


def _counts(units: ConcurrentStableList[HelpCoverageUnit], kind: str) -> HelpCoverageCounts:
    """统计某一类别的覆盖计数。

    Args:
        units: 单元集合。
        kind: `action` / `menu`。

    Returns:
        HelpCoverageCounts: 计数与双覆盖率。
    """
    total = 0
    covered = 0
    exempt = 0
    gap = 0
    for unit in units:
        if unit.kind != kind:
            continue
        total += 1
        if unit.covered:
            covered += 1
        elif unit.status == _UNIT_STATUS_EXEMPT:
            exempt += 1
        else:
            gap += 1
    return HelpCoverageCounts(
        total=total,
        covered=covered,
        exempt=exempt,
        gap=gap,
        coverage=_rate(covered, total),
        effective_coverage=_rate(covered + exempt, total),
    )


def _rate(numerator: int, denominator: int) -> float:
    """计算覆盖率（分母为 0 记 1.0）。

    Args:
        numerator: 分子。
        denominator: 分母。

    Returns:
        float: 四位小数覆盖率。
    """
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)


def _build_groups(
    units: ConcurrentStableList[HelpCoverageUnit],
    reference_rows: ConcurrentStableFrozenList[HelpCoverageReferenceRow],
    module_map: ConcurrentStableDict[str, HelpCoverageModule],
    scope: HelpCoverageScope,
) -> ConcurrentStableList[HelpCoverageGroup]:
    """按产品 / 模块聚合动作、菜单与参考计数。

    Args:
        units: 已过滤单元。
        reference_rows: 表单 / 字段参考行。
        module_map: 模块映射。
        scope: 过滤范围。

    Returns:
        ConcurrentStableList[HelpCoverageGroup]: 分组（固定排序）。
    """
    grouped: ConcurrentStableDict[tuple[str, str], ConcurrentStableList[HelpCoverageUnit]] = ConcurrentStableDict()
    for unit in units:
        key = (unit.product_key, unit.module_key)
        bucket: ConcurrentStableList[HelpCoverageUnit] | None = grouped.get(key)
        if bucket is None:
            new_units: ConcurrentStableList[HelpCoverageUnit] = ConcurrentStableList()
            grouped.set(key, new_units)
            bucket = new_units
        bucket.add(unit)
    reference_by_group = _reference_by_group(reference_rows, module_map, scope)
    groups: ConcurrentStableList[HelpCoverageGroup] = ConcurrentStableList()
    for (product_key, module_key), group_units in grouped.sorted_items():
        reference = reference_by_group.get((product_key, module_key))
        groups.add(
            HelpCoverageGroup(
                product_key=product_key,
                module_key=module_key,
                actions=_counts(group_units, COVERAGE_KIND_ACTION),
                menus=_counts(group_units, COVERAGE_KIND_MENU),
                reference=reference
                if reference is not None
                else HelpCoverageGroupReference(form_total=0, form_declared=0, field_total=0, field_declared=0),
            )
        )
    return groups


def _reference_by_group(
    reference_rows: ConcurrentStableFrozenList[HelpCoverageReferenceRow],
    module_map: ConcurrentStableDict[str, HelpCoverageModule],
    scope: HelpCoverageScope,
) -> ConcurrentStableDict[tuple[str, str], HelpCoverageGroupReference]:
    """按分组统计表单 / 字段参考计数。

    Args:
        reference_rows: 参考行。
        module_map: 模块映射。
        scope: 过滤范围。

    Returns:
        ConcurrentStableDict[tuple[str, str], HelpCoverageGroupReference]: 分组参考计数。
    """
    buckets: ConcurrentStableDict[tuple[str, str], ConcurrentStableList[int]] = ConcurrentStableDict()
    for row in reference_rows:
        module = _resolve_module(row.business_code, module_map)
        key = (module.product_key, module.module_key)
        if scope.product_keys and module.product_key not in scope.product_keys:
            continue
        if scope.module_keys and module.module_key not in scope.module_keys:
            continue
        bucket: ConcurrentStableList[int] | None = buckets.get(key)
        if bucket is None:
            new_bucket: ConcurrentStableList[int] = ConcurrentStableList((0, 0, 0, 0))
            buckets.set(key, new_bucket)
            bucket = new_bucket
        index = 0 if row.kind == "form" else 2
        bucket[index] = bucket[index] + 1
        if row.help_key is not None:
            bucket[index + 1] = bucket[index + 1] + 1
    result: ConcurrentStableDict[tuple[str, str], HelpCoverageGroupReference] = ConcurrentStableDict()
    for key, bucket in buckets.items():
        result.set(
            key,
            HelpCoverageGroupReference(
                form_total=bucket[0],
                form_declared=bucket[1],
                field_total=bucket[2],
                field_declared=bucket[3],
            ),
        )
    return result


def _build_reference(
    snapshot: HelpCoverageSnapshot,
    module_map: ConcurrentStableDict[str, HelpCoverageModule],
    scope: HelpCoverageScope,
) -> HelpCoverageReference:
    """构建全局参考统计（表单 / 字段 / 动作码兜底）。

    Args:
        snapshot: 元数据快照。
        module_map: 模块映射。
        scope: 过滤范围。

    Returns:
        HelpCoverageReference: 参考统计。
    """
    form_total = 0
    form_declared = 0
    field_total = 0
    field_declared = 0
    for row in snapshot.reference_rows:
        module = _resolve_module(row.business_code, module_map)
        if scope.product_keys and module.product_key not in scope.product_keys:
            continue
        if scope.module_keys and module.module_key not in scope.module_keys:
            continue
        if row.kind == "form":
            form_total += 1
            form_declared += 1 if row.help_key is not None else 0
        else:
            field_total += 1
            field_declared += 1 if row.help_key is not None else 0
    fallback_declared = sum(1 for row in snapshot.action_fallbacks if row.help_key is not None)
    return HelpCoverageReference(
        form=HelpCoverageCounts(
            total=form_total,
            covered=form_declared,
            exempt=0,
            gap=form_total - form_declared,
            coverage=_rate(form_declared, form_total),
            effective_coverage=_rate(form_declared, form_total),
        ),
        field=HelpCoverageCounts(
            total=field_total,
            covered=field_declared,
            exempt=0,
            gap=field_total - field_declared,
            coverage=_rate(field_declared, field_total),
            effective_coverage=_rate(field_declared, field_total),
        ),
        action_fallback_declared=fallback_declared,
        action_fallback_total=len(snapshot.action_fallbacks),
    )


def _build_reconciliation(
    units: ConcurrentStableList[HelpCoverageUnit],
    anchors: ConcurrentStableFrozenList[HelpCoverageAnchor],
) -> HelpCoverageReconciliation:
    """对账覆盖数与已登记锚点（菜单 / 按钮进等式，其余只计数）。

    Args:
        units: 全部覆盖单元（未过滤）。
        anchors: 全部锚点。

    Returns:
        HelpCoverageReconciliation: 对账结果。
    """
    anchor_counts = _anchor_counts(anchors)
    covered_menus = sum(1 for unit in units if unit.kind == COVERAGE_KIND_MENU and unit.covered)
    covered_actions = sum(1 for unit in units if unit.kind == COVERAGE_KIND_ACTION and unit.covered)
    unit_keys = ConcurrentStableFrozenSet((unit.kind, unit.model_id) for unit in units)
    orphans: ConcurrentStableList[HelpCoverageOrphan] = ConcurrentStableList()
    duplicates: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for anchor in anchors:
        duplicates.set(anchor.help_key, duplicates.get(anchor.help_key, 0) + 1)
        if anchor.kind is HelpAnchorKind.MENU and (COVERAGE_KIND_MENU, anchor.model_id) not in unit_keys:
            orphans.add(
                HelpCoverageOrphan(
                    kind=COVERAGE_KIND_MENU,
                    table=anchor.table,
                    model_id=anchor.model_id,
                    help_key=anchor.help_key,
                    reason="菜单不在基准（目录节点 / 未挂表单 / 业务无权限码 / 已停用）",
                )
            )
        elif anchor.kind is HelpAnchorKind.BUTTON and (COVERAGE_KIND_ACTION, anchor.model_id) not in unit_keys:
            orphans.add(
                HelpCoverageOrphan(
                    kind=COVERAGE_KIND_ACTION,
                    table=anchor.table,
                    model_id=anchor.model_id,
                    help_key=anchor.help_key,
                    reason="按钮不在基准（已停用 / 权限码缺失 / 表单或业务缺失）",
                )
            )
    duplicate_keys = ConcurrentStableFrozenList(sorted(key for key, count in duplicates.items() if count > 1))
    orphan_menus = sum(1 for orphan in orphans if orphan.kind == COVERAGE_KIND_MENU)
    orphan_actions = sum(1 for orphan in orphans if orphan.kind == COVERAGE_KIND_ACTION)
    consistent = (
        covered_menus + orphan_menus == anchor_counts.menu
        and covered_actions + orphan_actions == anchor_counts.button
        and not duplicate_keys
    )
    reference_counts = HelpCoverageAnchorCounts(
        menu=0,
        form=anchor_counts.form,
        field=anchor_counts.field,
        button=0,
        action=anchor_counts.action,
    )
    return HelpCoverageReconciliation(
        anchors=anchor_counts,
        covered_menus=covered_menus,
        covered_actions=covered_actions,
        orphans=ConcurrentStableFrozenList(sorted(orphans, key=lambda row: (row.kind, row.model_id))),
        reference_anchor_counts=reference_counts,
        duplicate_help_keys=duplicate_keys,
        consistent=consistent,
    )


def _anchor_counts(anchors: ConcurrentStableFrozenList[HelpCoverageAnchor]) -> HelpCoverageAnchorCounts:
    """按节点类型统计锚点数量。

    Args:
        anchors: 锚点集合。

    Returns:
        HelpCoverageAnchorCounts: 五类计数。
    """
    counts: ConcurrentStableDict[HelpAnchorKind, int] = ConcurrentStableDict()
    for anchor in anchors:
        counts.set(anchor.kind, counts.get(anchor.kind, 0) + 1)
    return HelpCoverageAnchorCounts(
        menu=counts.get(HelpAnchorKind.MENU, 0),
        form=counts.get(HelpAnchorKind.FORM, 0),
        field=counts.get(HelpAnchorKind.FIELD, 0),
        button=counts.get(HelpAnchorKind.BUTTON, 0),
        action=counts.get(HelpAnchorKind.ACTION, 0),
    )


def ledger_is_blocked(ledger: HelpCoverageLedger) -> bool:
    """判断强档是否阻断（豁免后缺口或对账不一致）。

    Args:
        ledger: 台账。

    Returns:
        bool: 是否阻断。
    """
    return ledger.actions.gap > 0 or ledger.menus.gap > 0 or not ledger.reconciliation.consistent


def build_baseline_diff(
    ledger: HelpCoverageLedger,
    baseline: object,
) -> HelpCoverageBaselineDiff:
    """计算当前台账与基线快照的差异。

    Args:
        ledger: 当前台账（应包含全部明细，即 `include_covered=True`）。
        baseline: 基线 JSON（`json.loads` 结果）。

    Returns:
        HelpCoverageBaselineDiff: 覆盖增减与缺口新增 / 消除 / 保留。

    Raises:
        HelpCoverageBaselineError: 基线结构不可解析。
    """
    if not isinstance(baseline, dict):
        raise HelpCoverageBaselineError("基线台账顶层须为对象")
    baseline_map = cast("dict[str, object]", baseline)
    if (
        baseline_map.get("schema_version") != HELP_COVERAGE_SCHEMA_VERSION
        or baseline_map.get("kind") != "help-coverage"
    ):
        raise HelpCoverageBaselineError("基线台账不是本任务输出的帮助覆盖率台账（schema_version / kind 不符）")
    raw_summary = baseline_map.get("summary")
    raw_units = baseline_map.get("units")
    if not isinstance(raw_summary, dict) or not isinstance(raw_units, list):
        raise HelpCoverageBaselineError("基线台账缺少 summary 或 units")
    summary_map = cast("dict[str, object]", raw_summary)
    baseline_actions = _baseline_counts(summary_map.get("action"))
    baseline_menus = _baseline_counts(summary_map.get("menu"))
    baseline_units = cast("list[object]", raw_units)
    baseline_gaps = ConcurrentStableFrozenSet(
        _baseline_gap_key(row) for row in baseline_units if _baseline_status(row) == _UNIT_STATUS_GAP
    )
    current_gaps = ConcurrentStableFrozenSet(
        f"{unit.kind}:{unit.key}" for unit in ledger.units if unit.status == _UNIT_STATUS_GAP
    )
    new_gaps = sorted(current_gaps - baseline_gaps)
    cleared_gaps = sorted(baseline_gaps - current_gaps)
    still_gaps = sorted(current_gaps & baseline_gaps)
    return HelpCoverageBaselineDiff(
        baseline_as_of=str(baseline_map.get("as_of", "")),
        action_coverage_delta=round(ledger.actions.coverage - baseline_actions, 4),
        menu_coverage_delta=round(ledger.menus.coverage - baseline_menus, 4),
        new_gaps=ConcurrentStableFrozenList(new_gaps),
        cleared_gaps=ConcurrentStableFrozenList(cleared_gaps),
        still_gaps=ConcurrentStableFrozenList(still_gaps),
    )


def _baseline_counts(raw: object) -> float:
    """取基线某类别的原始覆盖率。

    Args:
        raw: 基线 summary 中的类别对象。

    Returns:
        float: 原始覆盖率（缺失记 0.0）。

    Raises:
        HelpCoverageBaselineError: 结构非法。
    """
    if not isinstance(raw, dict):
        raise HelpCoverageBaselineError("基线 summary 缺少 action / menu")
    value = cast("dict[str, object]", raw).get("coverage")
    if not isinstance(value, (int, float)):
        raise HelpCoverageBaselineError("基线 summary 的 coverage 非法")
    return float(value)


def _baseline_status(row: object) -> str:
    """取基线明细状态。

    Args:
        row: 基线 units 中的一行。

    Returns:
        str: 状态（缺失 / 非法记空串）。

    Raises:
        HelpCoverageBaselineError: 行不是对象。
    """
    if not isinstance(row, dict):
        raise HelpCoverageBaselineError("基线 units 的条目须为对象")
    status = cast("dict[str, object]", row).get("status")
    return status if isinstance(status, str) else ""


def _baseline_gap_key(row: object) -> str:
    """取基线缺口的 `kind:key`。

    Args:
        row: 基线 units 中的一行。

    Returns:
        str: 缺口键。

    Raises:
        HelpCoverageBaselineError: kind / key 缺失。
    """
    row_map = cast("dict[str, object]", row)
    kind = row_map.get("kind")
    key = row_map.get("key")
    if not isinstance(kind, str) or not isinstance(key, str):
        raise HelpCoverageBaselineError("基线 units 的 kind / key 非法")
    return f"{kind}:{key}"


def ledger_payload(ledger: HelpCoverageLedger) -> object:
    """把台账转换为可 JSON 序列化的普通对象（排序固定）。

    Args:
        ledger: 台账。

    Returns:
        object: 普通 dict / list 结构（API 响应与 JSON 输出共用）。
    """
    return {
        "schema_version": HELP_COVERAGE_SCHEMA_VERSION,
        "kind": "help-coverage",
        "as_of": ledger.as_of.isoformat(),
        "scope": {
            "product_keys": list(ledger.scope.product_keys),
            "module_keys": list(ledger.scope.module_keys),
            "kinds": list(ledger.scope.kinds),
            "include_covered": ledger.scope.include_covered,
        },
        "summary": {
            "action": _counts_payload(ledger.actions),
            "menu": _counts_payload(ledger.menus),
            "reference": {
                "form": _counts_payload(ledger.reference.form),
                "field": _counts_payload(ledger.reference.field),
                "action_fallback": {
                    "declared": ledger.reference.action_fallback_declared,
                    "total": ledger.reference.action_fallback_total,
                    "gap": ledger.reference.action_fallback_total - ledger.reference.action_fallback_declared,
                },
            },
        },
        "groups": [
            {
                "product_key": group.product_key,
                "module_key": group.module_key,
                "action": _counts_payload(group.actions),
                "menu": _counts_payload(group.menus),
                "reference": {
                    "form_total": group.reference.form_total,
                    "form_declared": group.reference.form_declared,
                    "field_total": group.reference.field_total,
                    "field_declared": group.reference.field_declared,
                },
            }
            for group in ledger.groups
        ],
        "units": [_unit_payload(unit) for unit in ledger.units],
        "exemptions": {
            "applied": [_exemption_payload(entry) for entry in ledger.applied_exemptions],
            "expired": [_exemption_payload(entry) for entry in ledger.expired_exemptions],
            "stale": [_exemption_payload(entry) for entry in ledger.stale_exemptions],
        },
        "reconciliation": {
            "anchors": _anchors_payload(ledger.reconciliation.anchors),
            "covered": {
                "menu": ledger.reconciliation.covered_menus,
                "action": ledger.reconciliation.covered_actions,
            },
            "orphans": [
                {
                    "kind": orphan.kind,
                    "table": orphan.table,
                    "model_id": str(orphan.model_id),
                    "help_key": orphan.help_key,
                    "reason": orphan.reason,
                }
                for orphan in ledger.reconciliation.orphans
            ],
            "reference_anchor_counts": _anchors_payload(ledger.reconciliation.reference_anchor_counts),
            "duplicate_help_keys": list(ledger.reconciliation.duplicate_help_keys),
            "consistent": ledger.reconciliation.consistent,
        },
        "verdict": {
            "blocked": ledger_is_blocked(ledger),
            "action_gap": ledger.actions.gap,
            "menu_gap": ledger.menus.gap,
            "consistent": ledger.reconciliation.consistent,
        },
        "baseline_diff": _baseline_payload(ledger.baseline_diff),
    }


def _counts_payload(counts: HelpCoverageCounts) -> object:
    """计数对象转普通 dict。

    Args:
        counts: 计数。

    Returns:
        object: 普通 dict。
    """
    return {
        "total": counts.total,
        "covered": counts.covered,
        "exempt": counts.exempt,
        "gap": counts.gap,
        "coverage": counts.coverage,
        "effective_coverage": counts.effective_coverage,
    }


def _unit_payload(unit: HelpCoverageUnit) -> object:
    """明细单元转普通 dict。

    Args:
        unit: 明细单元。

    Returns:
        object: 普通 dict。
    """
    return {
        "kind": unit.kind,
        "key": unit.key,
        "product_key": unit.product_key,
        "module_key": unit.module_key,
        "business_code": unit.business_code,
        "action_code": unit.action_code,
        "menu_paths": list(unit.menu_paths),
        "model_id": str(unit.model_id),
        "help_key": unit.help_key,
        "covered": unit.covered,
        "status": unit.status,
        "exempt": _exemption_payload(unit.exemption) if unit.exemption is not None else None,
        "fallback_help_key": unit.fallback_help_key,
        "multi_business": unit.multi_business,
    }


def _exemption_payload(entry: HelpCoverageExemption) -> object:
    """豁免条目转普通 dict。

    Args:
        entry: 豁免条目。

    Returns:
        object: 普通 dict。
    """
    return {
        "kind": entry.kind,
        "key": entry.key,
        "owner": entry.owner,
        "reason": entry.reason,
        "expires_at": entry.expires_at.isoformat(),
        "product_key": entry.product_key,
    }


def _anchors_payload(counts: HelpCoverageAnchorCounts) -> object:
    """锚点计数转普通 dict。

    Args:
        counts: 锚点计数。

    Returns:
        object: 普通 dict。
    """
    return {
        "menu": counts.menu,
        "form": counts.form,
        "field": counts.field,
        "button": counts.button,
        "action": counts.action,
    }


def _baseline_payload(diff: HelpCoverageBaselineDiff | None) -> object:
    """基线对比转普通 dict。

    Args:
        diff: 对比结果（可空）。

    Returns:
        object: 普通 dict 或 `None`。
    """
    if diff is None:
        return None
    return {
        "baseline_as_of": diff.baseline_as_of,
        "action_coverage_delta": diff.action_coverage_delta,
        "menu_coverage_delta": diff.menu_coverage_delta,
        "new_gaps": list(diff.new_gaps),
        "cleared_gaps": list(diff.cleared_gaps),
        "still_gaps": list(diff.still_gaps),
    }


def render_json(ledger: HelpCoverageLedger) -> str:
    """渲染 JSON 台账（键排序、无隐式时间戳）。

    Args:
        ledger: 台账。

    Returns:
        str: JSON 文本（结尾换行）。
    """
    return json.dumps(ledger_payload(ledger), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def render_text(ledger: HelpCoverageLedger) -> str:
    """渲染人读文本台账。

    Args:
        ledger: 台账。

    Returns:
        str: 文本（结尾换行）。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add(f"帮助覆盖率台账（as_of {ledger.as_of.isoformat()}）")
    lines.add(_counts_line("动作", ledger.actions, "含按钮级锚点，动作码兜底不计"))
    lines.add(_counts_line("菜单", ledger.menus, "功能菜单，目录节点不计"))
    reference = ledger.reference
    lines.add(
        f"参考：表单 {reference.form.covered}/{reference.form.total}、"
        f"字段 {reference.field.covered}/{reference.field.total}、"
        f"动作码兜底 {reference.action_fallback_declared}/{reference.action_fallback_total}（不计入分母）"
    )
    lines.add("")
    lines.add("分组（覆盖 / 总数）：")
    lines.add(f"{'产品/模块':<28}{'动作':>12}{'菜单':>12}")
    for group in ledger.groups:
        lines.add(
            f"{group.product_key + '/' + group.module_key:<28}"
            f"{str(group.actions.covered) + '/' + str(group.actions.total):>12}"
            f"{str(group.menus.covered) + '/' + str(group.menus.total):>12}"
        )
    lines.add("")
    lines.add("缺口明细：")
    gaps = ConcurrentStableList(unit for unit in ledger.units if unit.status != _UNIT_STATUS_COVERED)
    if not gaps:
        lines.add("- 无（全部已声明或已登记豁免）")
    for unit in gaps:
        suffix = "（已豁免）" if unit.status == _UNIT_STATUS_EXEMPT else ""
        target = " @ " + ", ".join(unit.menu_paths) if unit.kind == COVERAGE_KIND_ACTION and unit.menu_paths else ""
        lines.add(f"- [{unit.kind}] {unit.key}{target}（{unit.product_key}/{unit.module_key}）{suffix}")
    lines.add("")
    lines.add(
        f"豁免：生效 {len(ledger.applied_exemptions)} / 过期 {len(ledger.expired_exemptions)}"
        f" / 陈旧 {len(ledger.stale_exemptions)}"
    )
    for entry in ledger.expired_exemptions:
        lines.add(f"- 过期：{entry.kind}:{entry.key}（{entry.expires_at.isoformat()}，{entry.owner}）")
    for entry in ledger.stale_exemptions:
        lines.add(f"- 陈旧：{entry.kind}:{entry.key}（{entry.owner}）")
    lines.add("")
    reconciliation = ledger.reconciliation
    orphan_menus = _orphan_count(reconciliation, COVERAGE_KIND_MENU)
    orphan_actions = _orphan_count(reconciliation, COVERAGE_KIND_ACTION)
    lines.add(
        "对账："
        f"菜单锚点 {reconciliation.anchors.menu} = 覆盖 {reconciliation.covered_menus} + 孤儿 {orphan_menus}；"
        f"按钮锚点 {reconciliation.anchors.button} = 覆盖 {reconciliation.covered_actions} + 孤儿 {orphan_actions}；"
        f"{'一致' if reconciliation.consistent else '不一致'}"
    )
    for orphan in reconciliation.orphans:
        lines.add(f"- 孤儿：{orphan.table}#{orphan.model_id} {orphan.help_key}（{orphan.reason}）")
    if reconciliation.duplicate_help_keys:
        lines.add(f"- 重复锚点：{', '.join(reconciliation.duplicate_help_keys)}")
    if ledger.baseline_diff is not None:
        diff = ledger.baseline_diff
        lines.add("")
        lines.add(f"基线对比（{diff.baseline_as_of or '未知日期'}）：")
        lines.add(f"- 动作覆盖率变化 {diff.action_coverage_delta:+.4f}；菜单覆盖率变化 {diff.menu_coverage_delta:+.4f}")
        lines.add(f"- 新增缺口 {len(diff.new_gaps)} / 已消除 {len(diff.cleared_gaps)} / 仍存在 {len(diff.still_gaps)}")
        for key in diff.new_gaps:
            lines.add(f"  + {key}")
        for key in diff.cleared_gaps:
            lines.add(f"  - {key}")
    return "\n".join(lines) + "\n"


def _counts_line(label: str, counts: HelpCoverageCounts, note: str) -> str:
    """格式化一行覆盖率摘要。

    Args:
        label: 类别名。
        counts: 计数。
        note: 口径说明。

    Returns:
        str: 摘要行。
    """
    return (
        f"{label}：{counts.total} 项，已声明 {counts.covered}，豁免 {counts.exempt}，缺口 {counts.gap}；"
        f"原始覆盖率 {counts.coverage * 100:.1f}%，豁免后 {counts.effective_coverage * 100:.1f}%（{note}）"
    )


def _orphan_count(reconciliation: HelpCoverageReconciliation, kind: str) -> int:
    """统计某类别的孤儿数。

    Args:
        reconciliation: 对账结果。
        kind: `menu` / `action`。

    Returns:
        int: 孤儿数。
    """
    return sum(1 for orphan in reconciliation.orphans if orphan.kind == kind)


def render_markdown(ledger: HelpCoverageLedger) -> str:
    """渲染 Markdown 台账（供阶段测试报告引用）。

    Args:
        ledger: 台账。

    Returns:
        str: Markdown 文本（结尾换行）。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add(f"### 帮助覆盖率台账（{ledger.as_of.isoformat()}）")
    lines.add("")
    lines.add("| 类别 | 总数 | 已声明 | 有效豁免 | 豁免后缺口 | 原始覆盖率 | 豁免后有效率 |")
    lines.add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, counts in (("动作（按钮）", ledger.actions), ("菜单（功能菜单）", ledger.menus)):
        lines.add(
            f"| {label} | {counts.total} | {counts.covered} | {counts.exempt} | {counts.gap} |"
            f" {counts.coverage * 100:.1f}% | {counts.effective_coverage * 100:.1f}% |"
        )
    lines.add("")
    lines.add(
        f"参考（不计入分母）：表单 {ledger.reference.form.covered}/{ledger.reference.form.total}，"
        f"字段 {ledger.reference.field.covered}/{ledger.reference.field.total}，"
        f"动作码兜底 {ledger.reference.action_fallback_declared}/{ledger.reference.action_fallback_total}。"
    )
    lines.add("")
    lines.add("| 产品 / 模块 | 动作（覆盖 / 总数） | 菜单（覆盖 / 总数） | 表单（声明 / 总数） | 字段（声明 / 总数） |")
    lines.add("| --- | ---: | ---: | ---: | ---: |")
    for group in ledger.groups:
        lines.add(
            f"| {group.product_key}/{group.module_key} | {group.actions.covered}/{group.actions.total} |"
            f" {group.menus.covered}/{group.menus.total} |"
            f" {group.reference.form_declared}/{group.reference.form_total} |"
            f" {group.reference.field_declared}/{group.reference.field_total} |"
        )
    lines.add("")
    lines.add("| 类别 | 缺口键 | 菜单路径 | 归属 | 状态 |")
    lines.add("| --- | --- | --- | --- | --- |")
    rows = ConcurrentStableList(unit for unit in ledger.units if unit.status != _UNIT_STATUS_COVERED)
    if not rows:
        lines.add("| — | 无 | — | — | — |")
    for unit in rows:
        paths = ", ".join(unit.menu_paths) if unit.menu_paths else "—"
        status = "已豁免" if unit.status == _UNIT_STATUS_EXEMPT else "缺口"
        lines.add(f"| {unit.kind} | `{unit.key}` | {paths} | {unit.product_key}/{unit.module_key} | {status} |")
    lines.add("")
    lines.add(
        f"豁免：生效 {len(ledger.applied_exemptions)} / 过期 {len(ledger.expired_exemptions)}"
        f" / 陈旧 {len(ledger.stale_exemptions)}。"
    )
    reconciliation = ledger.reconciliation
    lines.add(
        f"对账：菜单锚点 {reconciliation.anchors.menu} = 覆盖 {reconciliation.covered_menus}"
        f" + 孤儿 {_orphan_count(reconciliation, COVERAGE_KIND_MENU)}；按钮锚点 {reconciliation.anchors.button} ="
        f" 覆盖 {reconciliation.covered_actions} + 孤儿 {_orphan_count(reconciliation, COVERAGE_KIND_ACTION)}；"
        f"结论 {'一致' if reconciliation.consistent else '不一致'}。"
    )
    if ledger.baseline_diff is not None:
        diff = ledger.baseline_diff
        lines.add("")
        lines.add(
            f"基线对比（{diff.baseline_as_of or '未知日期'}）：动作覆盖率 {diff.action_coverage_delta:+.4f}，"
            f"菜单覆盖率 {diff.menu_coverage_delta:+.4f}；"
            f"新增缺口 {len(diff.new_gaps)}，已消除 {len(diff.cleared_gaps)}，仍存在 {len(diff.still_gaps)}。"
        )
    return "\n".join(lines) + "\n"
