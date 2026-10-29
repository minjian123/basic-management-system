"""07B 跨产品协同收口断言（文档与门禁自洽）：门禁结论、报告归档、登记清单状态、遗留归口。

与 `test_m6_closure.py` / `test_m7_closure.py` 同族：只做**文档与登记的结构断言**，不重复业务用例
（业务证据由各任务用例承担，本模块只校验「结论写了、证据指得着、行数对得上」）。
依 07B `05_01` 决策：本任务不新增 Kiwi 用例（验收与报告类交付，结论以门禁证据为准）。
"""

import json
import re
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

_ROOT = Path(__file__).resolve().parents[5]
_STAGE = _ROOT / "bms文档" / "项目" / "07B_跨产品协同"
_REPORT = _STAGE / "01_测试报告_跨产品协同.md"
_PLAN = _STAGE / "计划" / "01_计划_跨产品协同.md"
_CHECKLIST = _ROOT / "bms文档" / "跨产品协同登记清单.md"
_ARCH = _ROOT / "bms文档" / "设计" / "架构设计" / "38_架构设计_子系统_跨产品协同.md"
_EXT_PLAN = _ROOT / "bms文档" / "规划" / "平台可扩展性规划.md"
_TASK = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收_01_专项验收与测试报告" / "05_阶段验收_01_专项验收与测试报告.md"
_DOMAIN = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收.md"
_BASELINE = _ROOT / "deploy" / "boundaries" / "product_literals_baseline.json"

_GATE_ROWS = 10
"""门禁行数（单一事实源为计划 §5；设计 §3.1 的「9 行」已于 `05_01` 按实际修正为 10 行）。"""

_EVIDENCE_FILES = (
    "backend/libs/bms_core/tests/registry/test_products_manifest.py",
    "backend/libs/bms_core/tests/registry/test_error_codes.py",
    "backend/libs/bms_core/tests/registry/test_registry_boot.py",
    "backend/libs/bms_core/tests/tenant/seed/test_orchestrator.py",
    "backend/libs/bms_core/tests/ops/test_gateway_config.py",
    "backend/libs/bms_core/tests/ops/test_check_modules.py",
    "backend/libs/bms_core/tests/collaboration/test_capability_resolution.py",
    "backend/libs/bms_core/tests/collaboration/test_capability_grant.py",
    "frontend/packages/core/tests/catalog.spec.ts",
    "frontend/packages/ui_ep/tests/field-org-select.spec.ts",
    "scripts/tools/ci/product_repos_setup.sh",
    "backend/ops/export_errcodes.py",
)
"""报告 §5 与计划 §5 引用的证据文件（存在性即「证据可解析」）。"""


def _table_rows(section: str, skip_prefix: str = "") -> ConcurrentStableList[str]:
    """取 Markdown 表格数据行（去表头与分隔行）。

    Args:
        section: 片段文本。
        skip_prefix: 需排除的表头行首列名（如 `验收点`）；空串表示不排除。

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
    """取计划 §7 待办编号（`#` 列）。

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
    """门禁 10 行均有结论与证据；「限定」必须带归口且指向存在的 §7 条目。"""
    text = _plan_text()
    rows = _table_rows(_gate_section(text), "验收点")
    assert len(rows) == _GATE_ROWS
    numbers = _followup_numbers(text)
    assert numbers, "计划 §7 台账不应为空"
    limited = 0
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 3
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
    assert limited == 1, "限定项应恰为 1 行（三库真库 XA）；CI 跨仓校验已有实跑证据，不得标限定"
    assert "**门禁对照**" in text


def test_plan_closure_state() -> None:
    """计划收口自洽：头部计数 = 两表行数、§3 清空、工时三项自洽、报告已挂接。"""
    text = _plan_text()
    match = re.search(r"已完成\s*(\d+)\s*项，剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section, "编号")
    assert int(match.group(1)) == len(done_rows) == 13, "头部已完成项数应与已完成任务表行数一致（13 项）"
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
    assert "01_测试报告_跨产品协同.md" in text
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
        "附录 A",
        "附录 B",
    ):
        assert heading in text, f"报告缺节：{heading}"
    gate_section = text.split("## 5. 门禁逐条核对", 1)[1].split("## 6.", 1)[0]
    assert len(_table_rows(gate_section, "#")) == _GATE_ROWS
    assert "计划 §5" in gate_section, "报告 §5 须声明结论同构引用计划 §5（单一事实源）"
    assert "无「无归口」条目" in text, "报告须显式声明遗留无「无归口」条目"
    assert "100%" in text and "覆盖率" in text


def test_checklist_status_all_adopted() -> None:
    """登记清单：能力清单无「待收编」残留，收编映射 11 行均有目标形态与证据。"""
    text = _CHECKLIST.read_text(encoding="utf-8")
    capabilities = text.split("## 2. 跨产品能力清单", 1)[1].split("## 3.", 1)[0]
    assert "待收编" not in capabilities, "能力清单不得残留「已装载（待收编）」"
    assert "设计已定" not in capabilities
    adoption = capabilities.count("已收编")
    assert adoption >= 13, f"能力清单「已收编」行数不足（现 {adoption}）"
    migration = text.split("## 7. 收编映射", 1)[1].split("## 8.", 1)[0]
    rows = _table_rows(migration, "#")
    assert len(rows) == 11, "收编映射应恰 11 行（立项时的 11 处硬编码）"
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 5, "收编映射须含「目标」与「证据」两列"
        assert cells[2] and cells[3] and cells[4], f"收编映射第 {cells[0]} 行目标形态 / 证据不得为空"


def test_architecture_links_resolvable() -> None:
    """架构 38 节点 ↔ 规划节 ↔ 登记清单互链可解析（防语义层与实现层断链）。"""
    for path in (_ARCH, _EXT_PLAN, _CHECKLIST):
        assert path.is_file(), f"缺文档：{path.name}"
    arch = _ARCH.read_text(encoding="utf-8")
    assert "平台可扩展性规划.md" in arch
    assert "跨产品协同登记清单.md" in arch
    plan = _EXT_PLAN.read_text(encoding="utf-8")
    assert "38_架构设计_子系统_跨产品协同.md" in plan
    checklist = _CHECKLIST.read_text(encoding="utf-8")
    assert "38_架构设计_子系统_跨产品协同.md" in checklist


def test_followup_items_all_owned() -> None:
    """遗留台账逐条归口：每行「来源 + 归口」齐备，无空归口 / 「无归口」条目。"""
    text = _plan_text()
    section = text.split("## 7. 后续阶段待办", 1)[1]
    rows = _table_rows(section, "#")
    assert len(rows) >= 22, "台账行数不应少于既有 22 行"
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 4, f"台账行应为 4 列：{row[:40]}"
        assert cells[0].isdigit(), f"台账首列应为编号：{row[:40]}"
        assert cells[1] and cells[2], f"台账第 {cells[0]} 行事项 / 来源不得为空"
        owner = cells[3]
        assert owner and owner != "—", f"台账第 {cells[0]} 行缺归口"
        assert "无归口" not in owner
    assert "无归口" not in section


def test_product_literals_hard_gate() -> None:
    """零字面量硬门禁：基线已清空（空即硬门禁），门禁第 1 行结论为达标。"""
    assert _BASELINE.is_file()
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert payload.get("entries") == [], "基线须为空（残留存量即无法转零命中硬门禁）"
    rows = _table_rows(_gate_section(_plan_text()), "验收点")
    first = _cells(rows[0])[2]
    assert "达标" in first and "基线清空" in first
    assert "限定达标" not in first


def test_evidence_paths_exist() -> None:
    """报告 / 计划引用的证据文件均可解析（防「证据指向不存在的用例」）。"""
    for rel in _EVIDENCE_FILES:
        assert (_ROOT / rel).is_file(), f"证据文件不存在：{rel}"
    report = _REPORT.read_text(encoding="utf-8")
    for rel in _EVIDENCE_FILES:
        assert Path(rel).name in report or rel in report, f"报告未索引证据：{rel}"


def test_task_doc_has_no_progress_fields() -> None:
    """进度口径：任务文档与域总览不承载状态 / 完成日期（唯一落点为计划表）。"""
    task_text = _TASK.read_text(encoding="utf-8")
    assert not re.search(r"^\| 状态 \|", task_text, re.M), "任务文档不得承载状态字段"
    assert not re.search(r"^\| 完成日期 \|", task_text, re.M), "任务文档不得承载完成日期"
    domain_text = _DOMAIN.read_text(encoding="utf-8")
    assert "| 状态 |" not in domain_text, "域总览子任务表不得承载状态列"
    plan_text = _plan_text()
    assert re.search(r"^\| 05_01 \|[^|]*\|[^|]*\| 2026-10-29 \|", plan_text, re.M), "计划表须登记 05_01 完成日期"
