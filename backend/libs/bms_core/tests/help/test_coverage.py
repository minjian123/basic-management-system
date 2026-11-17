"""帮助覆盖率台账引擎（08_04；Kiwi 2523）。

被测对象：`bms_core/help/coverage.py`（纯函数引擎）。锁死：基准口径、分组回退、限期豁免、
双覆盖率、锚点对账、确定性输出、基线对比与过滤。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.help.anchors import HelpAnchorKind
from bms_core.help.coverage import (
    COVERAGE_KIND_ACTION,
    COVERAGE_KIND_MENU,
    HelpCoverageAction,
    HelpCoverageAnchor,
    HelpCoverageBaselineDiff,
    HelpCoverageBaselineError,
    HelpCoverageExemption,
    HelpCoverageExemptionError,
    HelpCoverageExemptionSet,
    HelpCoverageFallback,
    HelpCoverageLedger,
    HelpCoverageMenu,
    HelpCoverageModule,
    HelpCoverageReferenceRow,
    HelpCoverageScope,
    HelpCoverageSnapshot,
    build_baseline_diff,
    build_help_coverage_ledger,
    ledger_is_blocked,
    ledger_payload,
    load_help_coverage_exemptions,
    render_json,
    render_markdown,
    render_text,
)

AS_OF = date(2026, 11, 17)
"""固定判定日期（豁免过期与可复现输出用）。"""


def _lst[ItemT](*items: ItemT) -> ConcurrentStableFrozenList[ItemT]:
    """构造不可变插入序列表（测试辅助，避免裸 tuple 声明）。

    Args:
        items: 元素。

    Returns:
        ConcurrentStableFrozenList[ItemT]: 列表。
    """
    return ConcurrentStableFrozenList(items)


def _module(code: str, *, product: str = "platform", module: str = "", registered: bool = True) -> HelpCoverageModule:
    """构造模块映射。

    Args:
        code: 业务码。
        product: 产品键。
        module: 模块键（空取业务码）。
        registered: 是否来自登记表。

    Returns:
        HelpCoverageModule: 映射项。
    """
    return HelpCoverageModule(
        business_code=code,
        product_key=product,
        module_key=module or code,
        registered=registered,
    )


def _action(
    model_id: int,
    business: str,
    action: str,
    *,
    help_key: str | None = None,
    menus: ConcurrentStableList[str] | None = None,
    fallback: str | None = None,
) -> HelpCoverageAction:
    """构造动作快照。

    Args:
        model_id: 按钮主键。
        business: 业务码。
        action: 动作码。
        help_key: 按钮锚点。
        menus: 菜单路径。
        fallback: 动作码兜底锚点。

    Returns:
        HelpCoverageAction: 动作快照。
    """
    return HelpCoverageAction(
        model_id=model_id,
        business_code=business,
        action_code=action,
        button_name=f"{business}-{action}",
        menu_paths=ConcurrentStableFrozenList(menus if menus is not None else _lst("/sys/probe")),
        help_key=help_key,
        fallback_help_key=fallback,
    )


def _menu(
    model_id: int,
    path: str,
    *,
    businesses: ConcurrentStableList[str] | None = None,
    help_key: str | None = None,
) -> HelpCoverageMenu:
    """构造菜单快照。

    Args:
        model_id: 菜单主键。
        path: 菜单路径。
        businesses: 挂接表单业务码。
        help_key: 菜单锚点。

    Returns:
        HelpCoverageMenu: 菜单快照。
    """
    return HelpCoverageMenu(
        model_id=model_id,
        path=path,
        business_codes=ConcurrentStableFrozenList(businesses if businesses is not None else _lst("user")),
        help_key=help_key,
    )


def _anchor(kind: HelpAnchorKind, model_id: int, key: str, *, table: str = "") -> HelpCoverageAnchor:
    """构造锚点快照。

    Args:
        kind: 节点类型。
        model_id: 记录主键。
        key: 锚点值。
        table: 逻辑表名（空取默认）。

    Returns:
        HelpCoverageAnchor: 锚点。
    """
    table_name = table or f"sys_{kind.value}"
    return HelpCoverageAnchor(kind=kind, table=table_name, model_id=model_id, help_key=key)


def _snapshot(
    *,
    actions: ConcurrentStableList[HelpCoverageAction] | None = None,
    menus: ConcurrentStableList[HelpCoverageMenu] | None = None,
    modules: ConcurrentStableList[HelpCoverageModule] | None = None,
    reference_rows: ConcurrentStableList[HelpCoverageReferenceRow] | None = None,
    fallbacks: ConcurrentStableList[HelpCoverageFallback] | None = None,
    anchors: ConcurrentStableList[HelpCoverageAnchor] | None = None,
    permission_businesses: ConcurrentStableList[str] | None = None,
) -> HelpCoverageSnapshot:
    """构造快照。

    Args:
        actions: 动作点。
        menus: 菜单点。
        modules: 模块映射。
        reference_rows: 参考行。
        fallbacks: 动作码兜底。
        anchors: 锚点。
        permission_businesses: 有权限码的业务码。

    Returns:
        HelpCoverageSnapshot: 快照。
    """
    return HelpCoverageSnapshot(
        actions=ConcurrentStableFrozenList(
            actions if actions is not None else ConcurrentStableFrozenList[HelpCoverageAction]()
        ),
        menus=ConcurrentStableFrozenList(
            menus if menus is not None else ConcurrentStableFrozenList[HelpCoverageMenu]()
        ),
        modules=ConcurrentStableFrozenList(
            modules if modules is not None else ConcurrentStableFrozenList[HelpCoverageModule]()
        ),
        reference_rows=ConcurrentStableFrozenList(
            reference_rows if reference_rows is not None else ConcurrentStableFrozenList[HelpCoverageReferenceRow]()
        ),
        action_fallbacks=ConcurrentStableFrozenList(
            fallbacks if fallbacks is not None else ConcurrentStableFrozenList[HelpCoverageFallback]()
        ),
        anchors=ConcurrentStableFrozenList(
            anchors if anchors is not None else ConcurrentStableFrozenList[HelpCoverageAnchor]()
        ),
        business_codes_with_permission=ConcurrentStableFrozenList(
            permission_businesses if permission_businesses is not None else _lst("user")
        ),
    )


def _exemptions(*entries: HelpCoverageExemption) -> HelpCoverageExemptionSet:
    """构造豁免集合。

    Args:
        entries: 豁免条目。

    Returns:
        HelpCoverageExemptionSet: 集合。
    """
    return HelpCoverageExemptionSet(
        entries=_lst(*entries),
        paths=_lst("inline"),
    )


def _exemption(
    kind: str,
    key: str,
    *,
    expires_at: date = AS_OF + timedelta(days=30),
    product: str | None = None,
) -> HelpCoverageExemption:
    """构造豁免条目。

    Args:
        kind: 类别。
        key: 单元键。
        expires_at: 失效日期。
        product: 产品段。

    Returns:
        HelpCoverageExemption: 条目。
    """
    return HelpCoverageExemption(
        kind=kind,
        key=key,
        owner="08_04",
        reason="测试用的豁免理由不少于十个字",
        expires_at=expires_at,
        product_key=product,
    )


@pytest.mark.kiwi_id(2523)
def test_ledger_is_deterministic() -> None:
    """同一快照 + 同一 as_of 两次输出逐字节一致。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create"),
            _action(2, "user", "update", help_key="platform:user:user::update"),
        ),
        menus=_lst(_menu(3, "/sys/users")),
        modules=_lst(_module("user")),
        reference_rows=_lst(HelpCoverageReferenceRow(business_code="user", kind="form", help_key=None)),
    )
    first = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    second = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    assert render_json(first) == render_json(second)
    assert render_text(first) == render_text(second)
    assert render_markdown(first) == render_markdown(second)


@pytest.mark.kiwi_id(2523)
def test_action_baseline_and_covered_rule() -> None:
    """按钮为单元；仅按钮锚点算覆盖，动作码兜底不影响。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create", help_key="platform:user:user::create", fallback=None),
            _action(2, "user", "update", fallback="platform::::update"),
        ),
        modules=_lst(_module("user")),
        fallbacks=_lst(HelpCoverageFallback(action_code="update", help_key="platform::::update")),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    assert ledger.actions.total == 2
    assert ledger.actions.covered == 1
    assert ledger.actions.gap == 1
    assert ledger.reference.action_fallback_declared == 1
    assert ledger.units[0].key == "user:update"
    assert ledger.units[0].fallback_help_key == "platform::::update"
    assert ledger.units[0].covered is False


@pytest.mark.kiwi_id(2523)
def test_menu_baseline_rules() -> None:
    """目录 / 无表单 / 业务无权限码的菜单不计；有组件挂表单的计入。"""
    snapshot = _snapshot(
        menus=_lst(
            _menu(1, "/sys/dir", businesses=_lst()),
            _menu(2, "/sys/no-permission", businesses=_lst("other")),
            _menu(3, "/sys/users", businesses=_lst("user"), help_key="platform:user:::"),
        ),
        modules=_lst(_module("user")),
        permission_businesses=_lst("user"),
    )
    ledger = build_help_coverage_ledger(
        snapshot,
        as_of=AS_OF,
        scope=HelpCoverageScope(
            product_keys=_lst(),
            module_keys=_lst(),
            kinds=_lst(),
            include_covered=True,
        ),
    )
    assert ledger.menus.total == 1
    assert ledger.menus.covered == 1
    assert ledger.units[0].key == "/sys/users"


@pytest.mark.kiwi_id(2523)
def test_gap_pinpoints_action_code() -> None:
    """缺口键为 `业务码:动作码`，带菜单路径与归属模块。"""
    snapshot = _snapshot(
        actions=_lst(_action(7, "user", "unlock", menus=_lst("/sys/account-locks", "/sys/users"))),
        modules=_lst(_module("user")),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    unit = ledger.units[0]
    assert unit.kind == COVERAGE_KIND_ACTION
    assert unit.key == "user:unlock"
    assert list(unit.menu_paths) == ["/sys/account-locks", "/sys/users"]
    assert (unit.product_key, unit.module_key) == ("platform", "user")
    assert "user:unlock" in render_text(ledger)


@pytest.mark.kiwi_id(2523)
def test_grouping_prefers_registry_then_business_code() -> None:
    """登记表优先、未登记业务码兼作模块名；同名模块按产品分列。"""
    snapshot = _snapshot(
        actions=_lst(_action(1, "user", "create"), _action(2, "pur", "create")),
        modules=_lst(
            _module("pur", product="biz", module="pur"),
            _module("pur", product="cw", module="pur"),
            _module("pur", product="biz", module="pur"),
        ),
        permission_businesses=_lst("user", "pur"),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    keys = [(group.product_key, group.module_key) for group in ledger.groups]
    assert ("platform", "user") in keys
    assert ("biz", "pur") in keys
    assert ("cw", "pur") not in keys
    assert ledger.actions.total == 2


@pytest.mark.kiwi_id(2523)
def test_multi_business_menu_is_deterministic() -> None:
    """菜单挂多业务时取字典序最小业务，标 multi_business，只计一次。"""
    snapshot = _snapshot(
        menus=_lst(_menu(1, "/sys/mixed", businesses=_lst("wh", "pur"))),
        modules=_lst(_module("pur", product="biz"), _module("wh", product="biz")),
        permission_businesses=_lst("wh", "pur"),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    assert ledger.menus.total == 1
    unit = ledger.units[0]
    assert unit.business_code == "pur"
    assert unit.multi_business is True
    assert (unit.product_key, unit.module_key) == ("biz", "pur")


@pytest.mark.kiwi_id(2523)
def test_reference_stats_do_not_affect_gates() -> None:
    """表单 / 字段 / 兜底只作参考，不影响分母与阻断。"""
    snapshot = _snapshot(
        actions=_lst(_action(1, "user", "create", help_key="platform:user:user::create")),
        modules=_lst(_module("user")),
        reference_rows=_lst(
            HelpCoverageReferenceRow(business_code="user", kind="form", help_key=None),
            HelpCoverageReferenceRow(business_code="user", kind="field", help_key=None),
            HelpCoverageReferenceRow(business_code="user", kind="field", help_key="platform:user:user:name:"),
        ),
        anchors=_lst(_anchor(HelpAnchorKind.BUTTON, 1, "platform:user:user::create")),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    assert ledger.actions.total == 1
    assert ledger.actions.gap == 0
    assert ledger.reference.form.total == 1
    assert ledger.reference.field.covered == 1
    assert ledger_is_blocked(ledger) is False


@pytest.mark.kiwi_id(2523)
def test_exemption_applied_expired_stale() -> None:
    """生效降缺口；过期计缺口；陈旧只告警。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create"),
            _action(2, "user", "update"),
            _action(3, "user", "delete"),
        ),
        modules=_lst(_module("user")),
    )
    exemptions = _exemptions(
        _exemption(COVERAGE_KIND_ACTION, "user:create", product="platform"),
        _exemption(COVERAGE_KIND_ACTION, "user:update", expires_at=AS_OF - timedelta(days=1)),
        _exemption(COVERAGE_KIND_ACTION, "user:gone"),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF, exemptions=exemptions)
    assert ledger.actions.exempt == 1
    assert ledger.actions.gap == 2
    assert [entry.key for entry in ledger.applied_exemptions] == ["user:create"]
    assert [entry.key for entry in ledger.expired_exemptions] == ["user:update"]
    assert [entry.key for entry in ledger.stale_exemptions] == ["user:gone"]
    payload = ledger_payload(ledger)
    assert isinstance(payload, dict)
    assert payload["exemptions"]["applied"][0]["key"] == "user:create"
    assert payload["exemptions"]["expired"][0]["key"] == "user:update"


@pytest.mark.kiwi_id(2523)
def test_exemption_product_mismatch_is_rejected() -> None:
    """豁免产品段与台账推导值不一致即拒收。"""
    snapshot = _snapshot(actions=_lst(_action(1, "user", "create")), modules=_lst(_module("user")))
    with pytest.raises(HelpCoverageExemptionError, match="product_key"):
        build_help_coverage_ledger(
            snapshot,
            as_of=AS_OF,
            exemptions=_exemptions(_exemption(COVERAGE_KIND_ACTION, "user:create", product="biz")),
        )


@pytest.mark.kiwi_id(2523)
def test_dual_coverage_rates() -> None:
    """原始覆盖率与豁免后有效率分别计算；总数为 0 记 1.0。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create"),
            _action(2, "user", "update", help_key="platform:user:user::update"),
        ),
        modules=_lst(_module("user")),
    )
    ledger = build_help_coverage_ledger(
        snapshot,
        as_of=AS_OF,
        exemptions=_exemptions(_exemption(COVERAGE_KIND_ACTION, "user:create")),
    )
    assert ledger.actions.coverage == 0.5
    assert ledger.actions.effective_coverage == 1.0
    empty = build_help_coverage_ledger(_snapshot(), as_of=AS_OF)
    assert empty.actions.coverage == 1.0
    assert empty.menus.coverage == 1.0


@pytest.mark.kiwi_id(2523)
def test_reconciliation_matches_registered_anchors() -> None:
    """覆盖数 + 孤儿数 = 锚点总数；重复锚点置不一致。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create", help_key="platform:user:user::create"),
            _action(2, "user", "update"),
        ),
        menus=_lst(
            _menu(3, "/sys/users", help_key="platform:user:::"),
            _menu(4, "/sys/dir", businesses=_lst()),
        ),
        modules=_lst(_module("user")),
        anchors=_lst(
            _anchor(HelpAnchorKind.BUTTON, 1, "platform:user:user::create"),
            _anchor(HelpAnchorKind.BUTTON, 9, "platform:user:user::orphan"),
            _anchor(HelpAnchorKind.MENU, 3, "platform:user:::"),
            _anchor(HelpAnchorKind.MENU, 8, "platform:dir::: "),
            _anchor(HelpAnchorKind.FORM, 5, "platform:user:user::"),
        ),
        permission_businesses=_lst("user"),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    reconciliation = ledger.reconciliation
    assert reconciliation.anchors.menu == 2
    assert reconciliation.anchors.button == 2
    assert reconciliation.covered_menus == 1
    assert reconciliation.covered_actions == 1
    assert len(reconciliation.orphans) == 2
    assert reconciliation.reference_anchor_counts.form == 1
    assert reconciliation.consistent is True

    duplicate = _snapshot(
        actions=_lst(_action(1, "user", "create", help_key="platform:user:user::create")),
        modules=_lst(_module("user")),
        anchors=_lst(
            _anchor(HelpAnchorKind.BUTTON, 1, "platform:user:user::create"),
            _anchor(HelpAnchorKind.FORM, 5, "platform:user:user::create"),
        ),
    )
    assert build_help_coverage_ledger(duplicate, as_of=AS_OF).reconciliation.consistent is False


@pytest.mark.kiwi_id(2523)
def test_renderers_are_stable() -> None:
    """text / markdown 行序固定、无隐式时间戳且包含关键字段。"""
    snapshot = _snapshot(
        actions=_lst(_action(1, "user", "create")),
        modules=_lst(_module("user")),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF)
    text = render_text(ledger)
    markdown = render_markdown(ledger)
    assert "as_of 2026-11-17" in text
    assert "user:create" in text
    assert "| 动作（按钮） |" in markdown
    assert "platform/user" in markdown
    assert "（2026-11-17）" in markdown


@pytest.mark.kiwi_id(2523)
def test_baseline_diff() -> None:
    """基线对比给出覆盖增减与缺口新增 / 消除 / 保留。"""
    baseline_snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create", help_key="platform:user:user::create"),
            _action(2, "user", "update"),
        ),
        modules=_lst(_module("user")),
    )
    current_snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create"),
            _action(2, "user", "update", help_key="platform:user:user::update"),
            _action(3, "user", "delete"),
        ),
        modules=_lst(_module("user")),
    )
    full_scope = HelpCoverageScope(
        product_keys=_lst(),
        module_keys=_lst(),
        kinds=_lst(),
        include_covered=True,
    )
    baseline = build_help_coverage_ledger(baseline_snapshot, as_of=AS_OF - timedelta(days=1), scope=full_scope)
    current = build_help_coverage_ledger(current_snapshot, as_of=AS_OF, scope=full_scope)
    diff = build_baseline_diff(current, ledger_payload(baseline))
    assert list(diff.new_gaps) == ["action:user:create", "action:user:delete"]
    assert list(diff.cleared_gaps) == ["action:user:update"]
    assert list(diff.still_gaps) == []
    assert diff.action_coverage_delta == round(1 / 3 - 1 / 2, 4)
    with pytest.raises(HelpCoverageBaselineError):
        build_baseline_diff(current, {"schema_version": 1})


@pytest.mark.kiwi_id(2523)
def test_filters_and_include_covered() -> None:
    """产品 / 模块影响摘要与分组；类别只影响明细；已覆盖行按开关出现。"""
    snapshot = _snapshot(
        actions=_lst(
            _action(1, "user", "create", help_key="platform:user:user::create"),
            _action(2, "user", "update"),
        ),
        menus=_lst(_menu(3, "/sys/users")),
        modules=_lst(_module("user"), _module("pur", product="biz")),
        permission_businesses=_lst("user", "pur"),
    )
    scope = HelpCoverageScope(
        product_keys=_lst("platform"),
        module_keys=_lst(),
        kinds=_lst(COVERAGE_KIND_ACTION),
        include_covered=True,
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF, scope=scope)
    assert ledger.actions.total == 2
    assert ledger.menus.total == 1
    assert {unit.kind for unit in ledger.units} == {COVERAGE_KIND_ACTION}
    assert len(ledger.units) == 2

    menu_scope = HelpCoverageScope(
        product_keys=_lst(),
        module_keys=_lst(),
        kinds=_lst(COVERAGE_KIND_MENU),
        include_covered=False,
    )
    menu_ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF, scope=menu_scope)
    assert [unit.key for unit in menu_ledger.units] == ["/sys/users"]


@pytest.mark.kiwi_id(2523)
def test_load_exemptions_from_files(tmp_path: Path) -> None:
    """豁免文件读取：合法 / 缺省缺失 / 显式缺失 / 非法结构 / 重复。"""
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exemptions": [
                    {
                        "kind": "action",
                        "key": "user:create",
                        "owner": "08_04",
                        "reason": "测试用的豁免理由不少于十个字",
                        "expires_at": "2027-03-31",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = load_help_coverage_exemptions(_lst(str(valid)), strict_paths=True)
    assert [entry.key for entry in loaded.entries] == ["user:create"]
    assert list(loaded.paths) == [str(valid)]

    missing = tmp_path / "missing.json"
    assert len(load_help_coverage_exemptions(_lst(str(missing))).entries) == 0
    with pytest.raises(HelpCoverageExemptionError, match="不存在"):
        load_help_coverage_exemptions(_lst(str(missing)), strict_paths=True)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exemptions": [
                    {
                        "kind": "menu",
                        "key": "/sys/users",
                        "owner": "08_04",
                        "reason": "测试用的豁免理由不少于十个字",
                        "expires_at": "2027-03-31",
                    },
                    {
                        "kind": "menu",
                        "key": "/sys/users",
                        "owner": "08_04",
                        "reason": "测试用的豁免理由不少于十个字",
                        "expires_at": "2027-03-31",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(HelpCoverageExemptionError, match="重复"):
        load_help_coverage_exemptions(_lst(str(duplicate)))

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps({"schema_version": 1, "exemptions": [{"kind": "other", "key": "x"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(HelpCoverageExemptionError):
        load_help_coverage_exemptions(_lst(str(invalid)))


@pytest.mark.kiwi_id(2523)
def test_ledger_is_blocked_and_payload_shape() -> None:
    """强档阻断判据与 JSON 载荷关键字段。"""
    gap_ledger: HelpCoverageLedger = build_help_coverage_ledger(
        _snapshot(actions=_lst(_action(1, "user", "create")), modules=_lst(_module("user"))),
        as_of=AS_OF,
    )
    assert ledger_is_blocked(gap_ledger) is True
    payload = ledger_payload(gap_ledger)
    assert isinstance(payload, dict)
    assert payload["kind"] == "help-coverage"
    assert payload["summary"]["action"]["gap"] == 1
    assert payload["units"][0]["model_id"] == "1"
    assert payload["verdict"]["blocked"] is True

    covered = build_help_coverage_ledger(
        _snapshot(
            actions=_lst(_action(1, "user", "create", help_key="platform:user:user::create")),
            modules=_lst(_module("user")),
            anchors=_lst(_anchor(HelpAnchorKind.BUTTON, 1, "platform:user:user::create")),
        ),
        as_of=AS_OF,
    )
    assert ledger_is_blocked(covered) is False
    assert payload["baseline_diff"] is None


@pytest.mark.kiwi_id(2523)
def test_exemption_validation_error_branches(tmp_path: Path) -> None:
    """豁免文件各类非法结构均整文件拒收（错误定位到条目）。"""
    entry = {
        "kind": "action",
        "key": "user:create",
        "owner": "08_04",
        "reason": "测试用的豁免理由不少于十个字",
        "expires_at": "2027-03-31",
    }
    payloads: ConcurrentStableList[object] = ConcurrentStableList()
    payloads.add([])
    payloads.add({"schema_version": 1, "unknown": True, "exemptions": []})
    payloads.add({"schema_version": 2, "exemptions": []})
    payloads.add({"schema_version": 1, "exemptions": {}})
    payloads.add({"schema_version": 1, "exemptions": [1]})
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "unknown": 1}]})
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "key": " "}]})
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "owner": " "}]})
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "reason": "短"}]})
    payloads.add(
        {"schema_version": 1, "exemptions": [{key: value for key, value in entry.items() if key != "expires_at"}]}
    )
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "expires_at": "2027-13-01"}]})
    payloads.add({"schema_version": 1, "exemptions": [{**entry, "product_key": 1}]})
    for index, payload in enumerate(payloads):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(HelpCoverageExemptionError):
            load_help_coverage_exemptions(_lst(str(path)), strict_paths=True)

    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    with pytest.raises(HelpCoverageExemptionError, match="不可读"):
        load_help_coverage_exemptions(_lst(str(broken)))


@pytest.mark.kiwi_id(2523)
def test_baseline_error_branches() -> None:
    """基线台账结构非法时全部拒收（不产出半套对比）。"""
    current = build_help_coverage_ledger(
        _snapshot(actions=_lst(_action(1, "user", "create")), modules=_lst(_module("user"))),
        as_of=AS_OF,
    )
    payloads: ConcurrentStableList[object] = ConcurrentStableList()
    payloads.add([])
    payloads.add({"schema_version": 1, "kind": "help-coverage"})
    payloads.add(
        {
            "schema_version": 1,
            "kind": "help-coverage",
            "summary": {"menu": {"coverage": 0.0}},
            "units": [],
        }
    )
    payloads.add(
        {
            "schema_version": 1,
            "kind": "help-coverage",
            "summary": {"action": {"coverage": "x"}, "menu": {"coverage": 0.0}},
            "units": [],
        }
    )
    payloads.add(
        {
            "schema_version": 1,
            "kind": "help-coverage",
            "summary": {"action": {"coverage": 0.0}, "menu": {"coverage": 0.0}},
            "units": [1],
        }
    )
    payloads.add(
        {
            "schema_version": 1,
            "kind": "help-coverage",
            "summary": {"action": {"coverage": 0.0}, "menu": {"coverage": 0.0}},
            "units": [{"status": "gap"}],
        }
    )
    for payload in payloads:
        with pytest.raises(HelpCoverageBaselineError):
            build_baseline_diff(current, payload)


@pytest.mark.kiwi_id(2523)
def test_scope_filters_skip_other_products() -> None:
    """产品过滤同时作用于明细、分组参考与全局参考。"""
    snapshot = _snapshot(
        actions=_lst(_action(1, "user", "create"), _action(2, "pur", "create")),
        modules=_lst(_module("user"), _module("pur", product="biz")),
        reference_rows=_lst(
            HelpCoverageReferenceRow(business_code="user", kind="form", help_key=None),
            HelpCoverageReferenceRow(business_code="pur", kind="form", help_key=None),
            HelpCoverageReferenceRow(business_code="pur", kind="field", help_key=None),
        ),
        permission_businesses=_lst("user", "pur"),
    )
    scope = HelpCoverageScope(
        product_keys=_lst("platform"),
        module_keys=_lst(),
        kinds=_lst(),
        include_covered=False,
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF, scope=scope)
    assert ledger.actions.total == 1
    assert ledger.reference.form.total == 1
    assert ledger.reference.field.total == 0
    assert [(group.product_key, group.module_key) for group in ledger.groups] == [("platform", "user")]
    assert ledger.groups[0].reference.form_total == 1


@pytest.mark.kiwi_id(2523)
def test_renderers_cover_gap_exemption_orphan_and_diff_branches() -> None:
    """渲染器覆盖无缺口 / 过期 / 陈旧 / 孤儿 / 重复锚点 / 基线对比分支。"""
    covered = build_help_coverage_ledger(
        _snapshot(
            actions=_lst(_action(1, "user", "create", help_key="platform:user:user::create")),
            modules=_lst(_module("user")),
            anchors=_lst(_anchor(HelpAnchorKind.BUTTON, 1, "platform:user:user::create")),
        ),
        as_of=AS_OF,
    )
    assert "- 无（全部已声明或已登记豁免）" in render_text(covered)
    assert "| — | 无 | — | — | — |" in render_markdown(covered)

    snapshot = _snapshot(
        actions=_lst(_action(2, "user", "update"), _action(3, "user", "delete")),
        menus=_lst(_menu(4, "/sys/dir", businesses=_lst())),
        modules=_lst(_module("user")),
        anchors=_lst(
            _anchor(HelpAnchorKind.MENU, 9, "platform:user:::"),
            _anchor(HelpAnchorKind.FORM, 8, "platform:user:user::"),
        ),
    )
    exemptions = _exemptions(
        _exemption(COVERAGE_KIND_ACTION, "user:update", expires_at=AS_OF - timedelta(days=1)),
        _exemption(COVERAGE_KIND_ACTION, "user:gone"),
    )
    ledger = build_help_coverage_ledger(snapshot, as_of=AS_OF, exemptions=exemptions)
    diff = HelpCoverageBaselineDiff(
        baseline_as_of="2026-11-16",
        action_coverage_delta=0.1,
        menu_coverage_delta=-0.1,
        new_gaps=_lst("action:user:delete"),
        cleared_gaps=_lst("action:user:create"),
        still_gaps=_lst(),
    )
    ledger = replace(ledger, baseline_diff=diff)
    text = render_text(ledger)
    assert "过期：" in text
    assert "陈旧：" in text
    assert "孤儿：" in text
    assert "基线对比（2026-11-16）" in text
    assert "+ action:user:delete" in text
    assert "- action:user:create" in text
    markdown = render_markdown(ledger)
    assert "基线对比（2026-11-16）" in markdown

    duplicate = build_help_coverage_ledger(
        HelpCoverageSnapshot(
            actions=ConcurrentStableFrozenList(),
            menus=ConcurrentStableFrozenList(),
            modules=ConcurrentStableFrozenList(),
            reference_rows=ConcurrentStableFrozenList(),
            action_fallbacks=ConcurrentStableFrozenList(),
            anchors=_lst(
                _anchor(HelpAnchorKind.MENU, 1, "platform:user:::"),
                _anchor(HelpAnchorKind.FORM, 2, "platform:user:::"),
            ),
            business_codes_with_permission=ConcurrentStableFrozenList(),
        ),
        as_of=AS_OF,
    )
    assert "重复锚点" in render_text(duplicate)
