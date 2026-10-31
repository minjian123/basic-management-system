"""种子统一编排器用例（07B `02_03`；详设 §5 测试设计 1~12 / 18~24 / 27）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填（与 `02_01` / `02_02` /
`02_04` / `02_05` 同口径）。

**覆盖面**：装载合并视图、预检（重名 / 环 / 依赖缺失 / 字段缺失 / 数据冲突）、拓扑排序、
分支派生、`--only` / `--skip` / `--require` 筛选、dry-run、逐项报告、退出码常量。
**执行链（串行 / 回滚 / 无脏数据）**见 `test_orchestrator_execute.py`。
"""

from pathlib import Path

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import SeedRecord, reset_seed_records, seed_catalog_view
from bms_core.tenant.seed import orchestrator
from bms_core.tenant.seed.contract import ExpectedRow


def _record(
    name: str,
    *,
    service: str = "platform",
    db_key: str = "platform_platform",
    after: ConcurrentStableFrozenList[str] | None = None,
    module: str = "ops.seed_menu",
    entry: str = "seed_menu_entry",
    source: str = "platform",
) -> SeedRecord:
    """构造种子记录（用例夹具）。

    Args:
        name: 种子名。
        service: 执行服务键。
        db_key: 目标库键。
        after: 依赖的种子名。
        module: 入口模块。
        entry: 入口函数名。
        source: 声明来源。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module=module,
        entry=entry,
        service=service,
        db_key=db_key,
        after=after if after is not None else ConcurrentStableFrozenList(),
        source=source,
    )


def _records(*records: SeedRecord) -> ConcurrentStableList[SeedRecord]:
    """把记录包成编排器要求的插入序集合。

    Args:
        *records: 种子记录。

    Returns:
        ConcurrentStableList[SeedRecord]: 记录清单。
    """
    return ConcurrentStableList(records)


# ---- 用例 1~3：装载（平台声明 / 合并视图 / 自动发现）----


def test_platform_declaration_loaded_into_catalog() -> None:
    """用例 1：`platform.toml` 的 10 条种子进入合并视图，字段逐一正确。"""
    reset_seed_records()
    load_product_manifests(ConcurrentStableList())
    view = seed_catalog_view()
    names = [record.name for record in view]
    # 声明序即装载序（platform.toml 的 [[seeds]] 出现序）
    assert names == [
        "seed-module",
        "seed-tables",
        "seed-menu",
        "seed-tenant",
        "seed-config",
        "seed-platform-role",
        "seed-tasks",
        "seed-rbac-role",
        "seed-platform-grant",
        "seed-rbac-grant",
    ]
    first = view[0]
    assert first.service == "platform"
    assert first.db_key == "platform_platform"
    assert first.module == "ops.seed_module"
    assert first.entry == "seed_modules_entry"
    assert first.op == "seed-module"
    assert first.source == "platform"


def test_merged_view_is_platform_first_then_product(tmp_path: Path) -> None:
    """用例 2：平台声明在前、产品声明在后；同一 `SeedRecord` 类型。"""
    manifest = tmp_path / "demo.toml"
    manifest.write_text(
        "\n".join(
            [
                'product_key = "demo"',
                "",
                "[[seeds]]",
                'name = "demo-admin-codes"',
                'service = "demo"',
                'db_key = "platform_platform"',
                'module = "ops.seed_menu"',
                'entry = "seed_menu_entry"',
                "after = []",
            ]
        ),
        encoding="utf-8",
    )
    reset_seed_records()
    load_product_manifests(ConcurrentStableList([str(manifest)]))
    view = seed_catalog_view()
    assert all(isinstance(record, SeedRecord) for record in view)
    assert view[0].source == "platform"
    assert view[-1].name == "demo-admin-codes"
    assert view[-1].source == "demo"


def test_local_registry_auto_discovered() -> None:
    """用例 3：本仓 `deploy/registry/*.toml` 无需配置即被装载。"""
    assert orchestrator.__name__.endswith("orchestrator")
    paths = orchestrator.__dict__.get("_local_manifest_paths")
    assert paths is None  # 自动发现实现在 products.py，编排器不重复实现
    reset_seed_records()
    load_product_manifests(ConcurrentStableList())
    assert len(seed_catalog_view()) >= 9


# ---- 用例 4~10：预检 ----


def test_precheck_rejects_duplicate_name_with_conflicting_declaration() -> None:
    """用例 4：同名且声明不一致 → 前置错误（列出种子名）。"""
    first = _record("seed-x")
    second = _record("seed-x", db_key="tenant_platform_demo")
    result = orchestrator.precheck_seeds(_records(first, second))
    assert any("种子重名且声明不一致：seed-x" in error for error in result.errors)


def test_precheck_allows_duplicate_name_with_identical_declaration() -> None:
    """用例 4 反例：同名同值合并放行（不报重名）。"""
    result = orchestrator.precheck_seeds(_records(_record("seed-x"), _record("seed-x")))
    assert not any("重名" in error for error in result.errors)


def test_precheck_rejects_missing_service_and_db_key() -> None:
    """用例 4 补充：缺 `service` / `db_key` → 两条前置错误。"""
    result = orchestrator.precheck_seeds(_records(_record("seed-x", service="", db_key="")))
    assert any("缺少执行服务声明" in error for error in result.errors)
    assert any("缺少分支目标库声明" in error for error in result.errors)


def test_precheck_rejects_cycle_and_reports_members() -> None:
    """用例 6：`after` 成环 → 前置错误，报出环上种子名。"""
    result = orchestrator.precheck_seeds(
        _records(
            _record("a", after=ConcurrentStableFrozenList(["b"])), _record("b", after=ConcurrentStableFrozenList(["a"]))
        )
    )
    assert any("依赖成环" in error for error in result.errors)
    joined = " ".join(result.errors)
    assert "a" in joined and "b" in joined


def test_precheck_rejects_dangling_after_reference() -> None:
    """用例 9：`after` 引用不存在的种子 → 前置错误。"""
    result = orchestrator.precheck_seeds(_records(_record("seed-x", after=ConcurrentStableFrozenList(["ghost"]))))
    assert any("依赖的种子不存在（after → ghost）" in error for error in result.errors)


def test_detect_cycles_returns_empty_for_acyclic() -> None:
    """用例 6 反例：无环返回空。"""
    cycle = orchestrator.detect_cycles(_records(_record("a"), _record("b", after=ConcurrentStableFrozenList(["a"]))))
    assert list(cycle) == []


def test_detect_cycles_ignores_unknown_dependencies() -> None:
    """环检测只按已知种子建图：指向未知名的依赖不参与（由前置校验单独报）。"""
    cycle = orchestrator.detect_cycles(_records(_record("a", after=ConcurrentStableFrozenList(["ghost"]))))
    assert list(cycle) == []


# ---- 用例 11：拓扑排序 ----


def test_topological_order_respects_after_and_registration_order() -> None:
    """用例 11：执行顺序满足 `after`；同层按登记顺序稳定。"""
    records = _records(
        _record("c", after=ConcurrentStableFrozenList(["a"])),
        _record("a"),
        _record("b"),
    )
    ordered = [record.name for record in orchestrator.topological_order(records)]
    assert ordered.index("a") < ordered.index("c")
    # 同层（a / b 均无依赖）保持登记序
    assert ordered == ["a", "b", "c"]


def test_topological_order_ignores_unknown_dependencies() -> None:
    """排序只看**已知**依赖：`after` 指向未知名时该种子照常排序（缺失由前置校验单独报）。"""
    records = _records(_record("a", after=ConcurrentStableFrozenList(["ghost"])))
    ordered = [record.name for record in orchestrator.topological_order(records)]
    assert ordered == ["a"]


# ---- 用例 12：分支派生 ----


def test_build_plan_derives_one_branch_per_seed() -> None:
    """用例 12：每种子一个分支；`branch_id` ≤ 16 字符且稳定；`service` / `db_key` 与声明一致。"""
    plan = orchestrator.build_plan(_records(_record("seed-x", db_key="tenant_platform_{tenant}")), tenant="demo")
    assert len(plan) == 1
    item = plan[0]
    assert len(item.branch_id) <= 16
    assert item.branch_id == orchestrator.branch_id_of("seed-x")
    assert item.db_key == "tenant_platform_demo"
    specs = orchestrator.build_branch_specs(plan)
    assert specs[0].service == "platform"
    assert specs[0].db_key == "tenant_platform_demo"


def test_branch_id_is_stable_and_length_bounded() -> None:
    """`branch_id` = `sha1(name)[:16]`：稳定、定长、对长名同样合规。"""
    long_name = "seed-" + "x" * 200
    assert orchestrator.branch_id_of(long_name) == orchestrator.branch_id_of(long_name)
    assert len(orchestrator.branch_id_of(long_name)) == 16
    assert orchestrator.branch_id_of("a") != orchestrator.branch_id_of("b")


# ---- 用例 18：幂等（编排层口径：重复执行计划一致）----


def test_build_plan_is_deterministic_across_calls() -> None:
    """用例 18 编排层：同一声明重复派生计划结果一致（幂等前提）。"""
    records = _records(_record("b"), _record("a", after=ConcurrentStableFrozenList(["b"])))
    first = [(item.record.name, item.branch_id, item.db_key) for item in orchestrator.build_plan(records, tenant="t")]
    second = [(item.record.name, item.branch_id, item.db_key) for item in orchestrator.build_plan(records, tenant="t")]
    assert first == second


# ---- 用例 19：dry-run ----


async def test_execute_plan_with_empty_plan_writes_nothing() -> None:
    """用例 19 相关：空计划不开启事务、不写库（dry-run 语义的执行侧保证）。"""
    reports = await orchestrator.execute_plan(
        ConcurrentStableList(),
        tenant="demo",
        caller_service="platform",
        manager=_NoopManager(),  # type: ignore[arg-type]
        branch_runner=_NoopRunner(),  # type: ignore[arg-type]
    )
    assert list(reports) == []


class _NoopManager:
    """事务管理器替身：空计划时不应被调用。"""

    async def begin(self, **_kwargs: object) -> object:
        """被调用即断言失败。"""
        raise AssertionError("空计划不应开启事务")

    async def commit(self, _txn_id: str) -> object:
        """被调用即断言失败。"""
        raise AssertionError("空计划不应提交")

    async def rollback(self, _txn_id: str) -> object:
        """被调用即断言失败。"""
        raise AssertionError("空计划不应回滚")


class _NoopRunner:
    """分支执行器替身：空计划时不应被调用。"""

    async def execute_branch_with_stats(self, **_kwargs: object) -> tuple[str, object]:
        """被调用即断言失败。"""
        raise AssertionError("空计划不应执行分支")


# ---- 用例 20：--only / --skip ----


def test_select_seeds_only_and_skip() -> None:
    """用例 20：`--only` 只执行指定项；`--skip` 排除指定项。"""
    records = _records(_record("a"), _record("b"), _record("c"))
    only = orchestrator.select_seeds(
        records,
        only=ConcurrentStableList(["a", "b"]),
        skip=ConcurrentStableList(),
        require=ConcurrentStableList(),
    )
    assert [record.name for record in only] == ["a", "b"]
    skipped = orchestrator.select_seeds(
        records,
        only=ConcurrentStableList(),
        skip=ConcurrentStableList(["b"]),
        require=ConcurrentStableList(),
    )
    assert [record.name for record in skipped] == ["a", "c"]


def test_select_seeds_rejects_unknown_name() -> None:
    """用例 20 反例：引用不存在的种子 → `ParamError`（CLI 侧退 64）。"""
    records = _records(_record("a"))
    with pytest.raises(ParamError, match="--only 引用了不存在的种子"):
        orchestrator.select_seeds(
            records,
            only=ConcurrentStableList(["ghost"]),
            skip=ConcurrentStableList(),
            require=ConcurrentStableList(),
        )


def test_select_seeds_only_does_not_backfill_dependencies() -> None:
    """用例 20 补充：`--only` **不自动补依赖**（显式优于隐式）。"""
    records = _records(_record("a"), _record("b", after=ConcurrentStableFrozenList(["a"])))
    selected = orchestrator.select_seeds(
        records,
        only=ConcurrentStableList(["b"]),
        skip=ConcurrentStableList(),
        require=ConcurrentStableList(),
    )
    assert [record.name for record in selected] == ["b"]


# ---- 用例 21：--require ----


def test_require_moves_seed_to_front() -> None:
    """用例 21：被 require 的种子排在全部之前（详设 §3.6.5）。"""
    records = _records(_record("a"), _record("b"), _record("c"))
    plan = orchestrator.build_plan(records, tenant="demo", require=ConcurrentStableList(["c"]))
    assert [item.record.name for item in plan] == ["c", "a", "b"]


def test_require_pulls_dependencies_into_front_group() -> None:
    """用例 21：require 项自身的依赖被提升进强制前置组，且依赖仍先于它。"""
    records = _records(_record("a"), _record("b"), _record("c", after=ConcurrentStableFrozenList(["b"])))
    plan = orchestrator.build_plan(records, tenant="demo", require=ConcurrentStableList(["c"]))
    names = [item.record.name for item in plan]
    assert names.index("b") < names.index("c")
    assert names == ["b", "c", "a"]


def test_require_rejects_target_outside_selection() -> None:
    """用例 21 反例：require 目标不在执行集合内 → `ParamError`（退出码 3）。"""
    records = _records(_record("a"))
    with pytest.raises(ParamError, match="--require 的目标不在执行集合内"):
        orchestrator.select_seeds(
            records,
            only=ConcurrentStableList(),
            skip=ConcurrentStableList(["a"]),
            require=ConcurrentStableList(["a"]),
        )


def test_require_rejects_unresolvable_dependency() -> None:
    """用例 21 反例：require 项的依赖被 skip → 强制前置无法兑现，`ParamError`。"""
    records = _records(_record("a"), _record("b", after=ConcurrentStableFrozenList(["a"])))
    with pytest.raises(ParamError, match="依赖的种子不在执行集合内"):
        orchestrator.select_seeds(
            records,
            only=ConcurrentStableList(),
            skip=ConcurrentStableList(["a"]),
            require=ConcurrentStableList(["b"]),
        )


def test_require_closure_includes_transitive_dependencies() -> None:
    """`require_closure` 展开传递依赖（不只直接依赖）。"""
    records = _records(
        _record("a"),
        _record("b", after=ConcurrentStableFrozenList(["a"])),
        _record("c", after=ConcurrentStableFrozenList(["b"])),
    )
    closure = orchestrator.require_closure(records, ConcurrentStableList(["c"]))
    assert set(closure) == {"a", "b", "c"}


# ---- 用例 22：参数错误（退出码 64 常量）----


def test_exit_code_constants() -> None:
    """用例 22 口径：退出码常量取值（64 = `EX_USAGE`，避开 argparse 缺省的 2）。"""
    assert orchestrator.EXIT_OK == 0
    assert orchestrator.EXIT_CONFLICT == 1
    assert orchestrator.EXIT_EXECUTE == 2
    assert orchestrator.EXIT_PRECHECK == 3
    assert orchestrator.EXIT_USAGE == 64


# ---- 用例 23~24：报告口径 ----


def test_seed_report_defaults() -> None:
    """用例 23/24 口径：报告字段齐全（统计由执行器采集，缺省 0）。"""
    report = orchestrator.SeedReport(name="seed-x", source="platform")
    assert (report.status, report.created, report.updated, report.skipped) == ("pending", 0, 0, 0)
    assert (report.conflicts, report.note) == (0, "")


def test_source_of_uses_injected_source() -> None:
    """用例 24：来源取装载期注入的 `source`，不再按名字首段推断（详设 §8 #25）。"""
    assert orchestrator._source_of(_record("seed-module", source="platform")) == "platform"  # pyright: ignore[reportPrivateUsage]
    assert orchestrator._source_of(_record("demo-admin-codes", source="demo")) == "demo"  # pyright: ignore[reportPrivateUsage]
    # 未注入时回退 platform（仅旧清单 / 单测构造会如此）
    assert orchestrator._source_of(_record("seed-module", source="")) == "platform"  # pyright: ignore[reportPrivateUsage]


# ---- 用例 27：单步命令兼容 ----


def test_ops_shell_still_forwards_to_base_module() -> None:
    """用例 27：`ops.seed_menu` 等薄壳仍转发到基座实现（原 `main` 保留）。"""
    import ops.seed_menu as seed_menu

    assert callable(seed_menu.main)
    assert callable(seed_menu.seed_menu_entry)


# ---- 期望行契约（详设 §3.5；支撑用例 5/26）----


def test_expected_rows_of_returns_rows_for_known_seed() -> None:
    """`expected_rows_of` 读实现模块的 `expected_rows()`（纯函数）。"""
    rows = orchestrator.expected_rows_of(_record("seed-menu", module="bms_core.tenant.seed.menu"))
    assert rows
    assert all(isinstance(row, ExpectedRow) for row in rows)
    tables = {row.table for row in rows}
    assert {"sys_business", "sys_action", "sys_menu"} <= tables


def test_expected_rows_of_returns_empty_for_module_without_contract() -> None:
    """未实现 `expected_rows` 的模块返回空（跳过该种子的数据预检，不报错）。"""
    assert list(orchestrator.expected_rows_of(_record("x", module="bms_core.core.concurrent"))) == []


def test_expected_rows_of_returns_empty_for_unimportable_module() -> None:
    """模块不可导入时返回空（不抛错）。"""
    assert list(orchestrator.expected_rows_of(_record("x", module="absent.module.path"))) == []


def test_compare_row_reports_field_diffs() -> None:
    """`_compare_row` 逐字段比对，输出「现有 / 期望」明细。"""

    class _Row:
        """现有行替身。"""

        name = "旧名"

    expected = ExpectedRow(
        table="sys_business",
        key=ConcurrentStableFrozenDict({"code": "mdm"}),
        values=ConcurrentStableFrozenDict({"name": "新名"}),
    )
    diffs = orchestrator._compare_row(_Row(), expected)  # pyright: ignore[reportPrivateUsage]
    assert len(diffs) == 1
    assert "name：现有 '旧名' / 期望 '新名'" in diffs[0]


def test_compare_row_returns_empty_when_all_fields_match() -> None:
    """全等时无差异（该行按「跳过」计）。"""

    class _Row:
        """现有行替身。"""

        name = "同名"

    expected = ExpectedRow(
        table="sys_business",
        key=ConcurrentStableFrozenDict({"code": "mdm"}),
        values=ConcurrentStableFrozenDict({"name": "同名"}),
    )
    assert list(orchestrator._compare_row(_Row(), expected)) == []  # pyright: ignore[reportPrivateUsage]


def test_table_for_resolves_registered_table_only() -> None:
    """`_table_for` 只解析已登记表；未知表名返回 None（该行跳过预检）。"""
    assert orchestrator._table_for("sys_business") is not None  # pyright: ignore[reportPrivateUsage]
    assert orchestrator._table_for("no_such_table") is None  # pyright: ignore[reportPrivateUsage]
