"""07C 产品与服务划分收口断言（文档与门禁自洽）：门禁结论、报告归档、计划自洽、表文件口径。

与 `test_collab_closure.py` / `test_m7_closure.py` 同族：只做**文档与登记的结构断言**，不重复业务用例
（业务证据由各任务用例承担，本模块只校验「结论写了、证据指得着、行数对得上、口径没回潮」）。
依 07C `05_01` 决策：本任务不新增 Kiwi 用例（验收与报告类交付，结论以门禁证据为准）。
"""

import re
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

_ROOT = Path(__file__).resolve().parents[5]
_STAGE = _ROOT / "bms文档" / "项目" / "07C_产品与服务划分"
_REPORT = _STAGE / "01_测试报告_产品与服务划分.md"
_PLAN = _STAGE / "计划" / "01_计划_产品与服务划分.md"
_TASK = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收_01_专项验收与测试报告" / "05_阶段验收_01_专项验收与测试报告.md"
_DOMAIN = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收.md"
_TABLE_DIR = _ROOT / "bms文档" / "设计" / "数据库设计" / "数据表设计"
_HANDOVER = _STAGE / "02_部署窗口待办_产品与服务划分.md"

_GATE_ROWS = 7
"""门禁行数（单一事实源为计划 §5）。"""

_DONE_TASKS = 12
"""已完成任务数（§2 已完成任务表行数）。"""

_EVIDENCE_FILES = (
    "backend/libs/bms_core/tests/collaboration/test_topology_mode.py",
    "backend/libs/bms_core/tests/collaboration/test_capability_resolution.py",
    "backend/libs/bms_core/tests/collaboration/test_domain_scope.py",
    "backend/libs/bms_core/tests/services/test_gateway_catalog.py",
    "backend/libs/bms_core/tests/ops/test_topology_migration.py",
    "backend/libs/bms_core/tests/ops/test_migrate_topology.py",
    "backend/libs/bms_core/tests/ops/test_release_cli.py",
    "backend/libs/bms_core/tests/api/test_require_capability.py",
    "backend/libs/bms_core/tests/api/test_request_domain_labels.py",
    "backend/services/platform/tests/api/test_tenant_topologies.py",
    "backend/services/platform/tests/registry/test_tenant_topology_bootstrap.py",
    "backend/services/platform/tests/release",
)
"""报告 §5 与计划 §5 引用的证据文件 / 目录（存在性即「证据可解析」）。"""


def _table_rows(section: str, skip_prefix: str = "") -> ConcurrentStableList[str]:
    """取 Markdown 表格数据行（去表头与分隔行）。

    Args:
        section: 片段文本。
        skip_prefix: 需排除的表头行首列名；空串表示不排除。

    Returns:
        ConcurrentStableList[str]: 数据行列表。
    """
    rows: ConcurrentStableList[str] = ConcurrentStableList()
    for line in section.splitlines():
        if not line.startswith("| ") or "---" in line:
            continue
        if skip_prefix and line.startswith(f"| {skip_prefix} "):
            continue
        rows.append(line)
    return rows


def _cells(row: str) -> ConcurrentStableList[str]:
    """拆分表格行单元格。

    Args:
        row: 表格行文本。

    Returns:
        ConcurrentStableList[str]: 去首尾空白的单元格。
    """
    return ConcurrentStableList(cell.strip() for cell in row.strip().strip("|").split("|"))


def _plan_text() -> str:
    """读专项计划文本。

    Returns:
        str: 计划全文。
    """
    return _PLAN.read_text(encoding="utf-8")


def _gate_section(text: str) -> str:
    """取计划 §5 门禁表片段（截到「门禁对照」之前）。

    Args:
        text: 计划全文。

    Returns:
        str: 门禁表片段。
    """
    section = text.split("## 5. 专项验收门禁", 1)[1].split("## 6.", 1)[0]
    return section.split("**门禁对照**", 1)[0]


def _followup_numbers(text: str) -> ConcurrentStableList[int]:
    """取计划 §7 台账编号（`#` 列）。

    Args:
        text: 计划全文。

    Returns:
        ConcurrentStableList[int]: 编号列表。
    """
    section = text.split("## 7. 后续阶段待办", 1)[1]
    numbers: ConcurrentStableList[int] = ConcurrentStableList()
    for row in _table_rows(section, "#"):
        head = _cells(row)[0]
        if head.isdigit():
            numbers.append(int(head))
    return numbers


def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁 7 行均有结论与证据；限定项恰 1 行且归口指向存在的 §7 条目。"""
    text = _plan_text()
    rows = _table_rows(_gate_section(text), "验收点")
    assert len(rows) == _GATE_ROWS, f"计划 §5 门禁表应恰 {_GATE_ROWS} 行（现 {len(rows)}）"
    numbers = _followup_numbers(text)
    assert numbers, "计划 §7 台账不应为空"
    limited = 0
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 3, f"门禁行应为 3 列：{row[:40]}"
        assert cells[0] and cells[1], "验收点与对应任务不得为空"
        evidence = cells[2]
        assert "达标" in evidence, f"门禁「{cells[0]}」缺结论字样（达标 / 限定达标）"
        assert len(evidence) > 60, f"门禁「{cells[0]}」证据过短，须含手段 / 标准 / 索引"
        if "限定达标" in evidence:
            limited += 1
            assert "归口 §7 第" in evidence, f"门禁「{cells[0]}」限定项必须写归口"
            target = re.search(r"归口 §7 第 (\d+) 项", evidence)
            assert target is not None
            assert int(target.group(1)) in numbers, f"门禁「{cells[0]}」归口指向不存在的 §7 条目"
    assert limited == 1, "限定项应恰为 1 行（迁移 S1/S3 未端到端 + 真库未验证）"
    assert "**门禁对照**" in text


def test_plan_closure_state() -> None:
    """计划收口自洽：头部计数 = 两表行数、§3 清空、工时三项自洽、报告已挂接。"""
    text = _plan_text()
    match = re.search(r"已完成\s*(\d+)\s*项，剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section, "编号")
    assert int(match.group(1)) == len(done_rows) == _DONE_TASKS, (
        f"头部已完成项数应与已完成任务表行数一致（{_DONE_TASKS} 项）"
    )
    todo_section = text.split("## 3. 剩余任务排期", 1)[1].split("## 4.", 1)[0]
    assert not _table_rows(todo_section, "编号"), "收口后剩余任务表不得有数据行"
    assert int(match.group(2)) == 0
    hours = re.search(
        r"已完成\s*\*{0,2}(\d+)h\*{0,2}；剩余\s*\*{0,2}(\d+)h\*{0,2}.*?阶段合计\s*\*{0,2}(\d+)h\*{0,2}",
        text,
    )
    assert hours, "计划工时行应为 check_status S1 可校验形态"
    assert int(hours.group(1)) + int(hours.group(2)) == int(hours.group(3))
    assert int(hours.group(2)) == 0
    assert "01_测试报告_产品与服务划分.md" in text, "计划头部或 §2 须挂接专项测试报告"
    assert "05_01" in done_section


def test_stage_report_archived_with_sections() -> None:
    """专项测试报告归档：七节 + 两附录齐备，§5 行数与门禁一致。"""
    assert _REPORT.is_file(), "专项测试报告须归档在专项根"
    text = _REPORT.read_text(encoding="utf-8")
    for heading in (
        "## 1. 结论",
        "## 2. 用例执行统计",
        "## 3. 缺陷统计",
        "## 4. 覆盖率",
        "## 5. 门禁逐条核对",
        "## 6. 风险与遗留",
        "## 7. 复盘与经验教训",
        "## 附录 A",
        "## 附录 B",
    ):
        assert heading in text, f"报告缺节：{heading}"
    gate_section = text.split("## 5. 门禁逐条核对", 1)[1].split("## 6.", 1)[0]
    assert len(_table_rows(gate_section, "#")) == _GATE_ROWS, "报告 §5 行数须等于门禁行数"
    assert "计划 §5" in gate_section, "报告 §5 须声明结论同构引用计划 §5（单一事实源）"
    assert "无「无归口」条目" in text, "报告须显式声明遗留无「无归口」条目"
    assert "100%" in text and "覆盖率" in text


def test_followup_items_all_owned() -> None:
    """遗留台账逐条归口：每行「来源 + 归口」齐备，无空归口 / 「无归口」条目。"""
    text = _plan_text()
    section = text.split("## 7. 后续阶段待办", 1)[1]
    rows = _table_rows(section, "#")
    assert len(rows) >= 11, "台账行数不应少于收口后的 11 行"
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 4, f"台账行应为 4 列：{row[:40]}"
        assert cells[0].isdigit(), f"台账首列应为编号：{row[:40]}"
        assert cells[1] and cells[2], f"台账第 {cells[0]} 行事项 / 来源不得为空"
        owner = cells[3]
        assert owner and owner != "—", f"台账第 {cells[0]} 行缺归口"
        assert "无归口" not in owner
    assert "无归口" not in section


def test_table_docs_use_deployment_unit_wording() -> None:
    """表文件「归属库」行统一写「归属部署单元」（`03_02` 遗留 3 由 `05_01` 闭环，防回潮）。"""
    assert _TABLE_DIR.is_dir()
    stale: ConcurrentStableList[str] = ConcurrentStableList()
    updated = 0
    for path in sorted(_TABLE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "| 归属库 |" in text, f"表文件缺「归属库」行：{path.name}"
        if "（归属服务 `" in text:
            stale.append(path.name)
        if "（归属部署单元 `" in text:
            updated += 1
    assert not stale, f"仍有表文件写「归属服务」：{', '.join(stale)}"
    assert updated >= 45, f"写「归属部署单元」的表文件过少（现 {updated}），批改可能未落地"


def test_evidence_paths_exist() -> None:
    """报告 / 计划引用的证据文件均可解析（防「证据指向不存在的用例」）。"""
    for rel in _EVIDENCE_FILES:
        assert (_ROOT / rel).exists(), f"证据不存在：{rel}"
    report = _REPORT.read_text(encoding="utf-8")
    for rel in _EVIDENCE_FILES:
        assert Path(rel).name in report, f"报告未索引证据：{rel}"


def test_followup_covers_design_open_items() -> None:
    """台账覆盖实质开放项（2026-10-31 补登）：只写在各设计 §9 的待办必须在 §7 查得到。

    背景：收口时 §7 只有 11 项，而 `04_02` / `04_03` / `03_04` 的实质开放项（真实双写、迁移进度落库、
    按租户路由、域级条件装配、跨仓 `domains` 升级、强档护栏）只散在设计 §9 与 §2 括号里，
    翻 §7 会以为什么都不欠。本断言盯住这六项的**关键词**，防止回退。
    """
    text = _plan_text()
    section = text.split("## 7. 后续阶段待办", 1)[1]
    numbers = _followup_numbers(text)
    assert numbers == ConcurrentStableList(range(1, len(numbers) + 1)), "台账编号须从 1 连续"
    for keyword in (
        "真实双写",
        "落库",
        "按租户路由",
        "域级条件装配",
        "domains` claim",
        "强档护栏",
    ):
        assert keyword in section, f"台账缺实质开放项关键词：{keyword}"
    assert "台账边界" in section, "§7 须声明「评估型开放项以各设计 §9 为准」的边界"
    assert "02_部署窗口待办_产品与服务划分.md" in section, "窗口类待办须指向移交清单"


def test_handover_checklist_registered() -> None:
    """移交清单归档并登记索引：W1~W4 四节齐备、回写落点成表、README 与首页均有入口。"""
    assert _HANDOVER.is_file(), "收口移交清单须归档在专项根"
    text = _HANDOVER.read_text(encoding="utf-8")
    for heading in (
        "## 1. 适用与边界",
        "## 2. W1 真库与真部署演练（S1 合并 / S3 换库）",
        "## 3. W2 切换后数据补偿",
        "## 4. W3 跨仓调用方升级（`domains` claim）",
        "## 5. W4 Kiwi 用例编号补登记（平台窗口）",
        "## 6. 完成后回写",
    ):
        assert heading in text, f"移交清单缺节：{heading}"
    for command in ("ops.migrate_topology", "--dry-run", "--verify-only", "--skip-release", "--backup-ref"):
        assert command in text, f"移交清单缺可执行要素：{command}"
    readme = (_STAGE / "README.md").read_text(encoding="utf-8")
    assert "02_部署窗口待办_产品与服务划分.md" in readme, "专项 README 未登记移交清单"
    homepage = (_ROOT / "bms文档" / "文档首页.md").read_text(encoding="utf-8")
    assert "02_部署窗口待办_产品与服务划分.md" in homepage, "文档首页未登记移交清单"


def test_task_doc_has_no_progress_fields() -> None:
    """进度口径：任务文档与域总览不承载状态 / 完成日期（唯一落点为计划表）。"""
    task_text = _TASK.read_text(encoding="utf-8")
    assert not re.search(r"^\| 状态 \|", task_text, re.M), "任务文档不得承载状态字段"
    assert not re.search(r"^\| 完成日期 \|", task_text, re.M), "任务文档不得承载完成日期"
    domain_text = _DOMAIN.read_text(encoding="utf-8")
    assert "| 状态 |" not in domain_text, "域总览子任务表不得承载状态列"
    plan_text = _plan_text()
    assert re.search(r"^\| 05_01 \|[^|]*\|[^|]*\| 2026-10-30 \|", plan_text, re.M), "计划表须登记 05_01 完成日期"
