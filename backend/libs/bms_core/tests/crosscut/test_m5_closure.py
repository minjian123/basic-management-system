"""M5 阶段收口核对（Kiwi 2189）：门禁结论、报告归档与状态一致性（文档断言）。"""

import re
from pathlib import Path

import pytest

_STAGE = Path(__file__).resolve().parents[5] / "bms文档" / "项目" / "05_前端插件化"
_REPORT = _STAGE / "01_测试报告_前端插件化.md"
_PLAN = _STAGE / "计划" / "01_计划_前端插件化.md"
_OVERVIEW = _STAGE / "需求" / "00_需求_前端插件化.md"
_TASK = (
    _STAGE
    / "任务"
    / "05_阶段验收"
    / "05_阶段验收_01_阶段验收门禁核对与测试报告"
    / "05_阶段验收_01_阶段验收门禁核对与测试报告.md"
)
_DOMAIN = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收.md"


def _table_rows(section: str) -> list[str]:
    """取 Markdown 表格数据行（去表头与分隔行）。

    Args:
        section: 片段文本。

    Returns:
        list[str]: 数据行列表。
    """
    return [
        line
        for line in section.splitlines()
        if line.startswith("| ")
        and "---" not in line
        and not line.startswith("| 编号 ")
        and not line.startswith("| 验收点 ")
        and not line.startswith("| 里程碑 ")
        and not line.startswith("| # ")
    ]


@pytest.mark.kiwi_id(2189)
def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁表 7 行均有结论与证据索引（计划 §5）；需求总览不再承载门禁表。

    门禁结论落计划 §5（需求文档不承载进度与验收证据，见《需求文档规范》「进度口径」节）：
    本断言核对 7 行结构完整、结论非空，覆盖里程碑对照，并确认需求总览已无门禁表。
    """
    plan_text = _PLAN.read_text(encoding="utf-8")
    gate_section = plan_text.split("## 5. M5 验收门禁", 1)[1].split("## 6.", 1)[0]
    gate_rows = _table_rows(gate_section.split("**里程碑对照**", 1)[0])
    assert len(gate_rows) == 7
    for row in gate_rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3
        assert cells[1] != ""  # 对应任务非空
        evidence = cells[2]  # 达成路径（结论与证据）
        assert len(evidence) > 10
        assert evidence != "—"
    assert "**里程碑对照**" in gate_section
    assert "2026-09-24 达成" in gate_section

    overview_text = _OVERVIEW.read_text(encoding="utf-8")
    assert "| 验收点 |" not in overview_text, "需求总览不应再承载门禁表"
    assert "05-9" in overview_text


@pytest.mark.kiwi_id(2189)
def test_plan_closure_state() -> None:
    """计划收口状态：头部计数与已完成表一致且剩余 0、剩余表清空、甘特里程碑、工时行可校验。

    头部项数不写死（防后续阶段回写漂移），改为校验结构自洽：
    「已完成 N 项，剩余 0 项」且 N 等于「已完成任务」表数据行数。
    """
    text = _PLAN.read_text(encoding="utf-8")
    match = re.search(r"已完成\s*(\d+)\s*项，剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    assert match.group(2) == "0", "阶段收口后剩余项应为 0"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section)
    assert int(match.group(1)) == len(done_rows), "头部已完成项数应与已完成任务表行数一致"
    todo_section = text.split("## 3. 剩余任务排期", 1)[1].split("## 4.", 1)[0]
    assert _table_rows(todo_section) == [], "阶段收口后剩余排期表应为空"
    assert "M5" in text and "milestone" in text
    assert re.search(
        r"已完成\s*\*{0,2}(\d+)h\*{0,2}；剩余\s*\*{0,2}0h\*{0,2}.*?阶段合计\s*\*{0,2}(\d+)h\*{0,2}",
        text,
    ), "计划工时行应为 check-status S1 可校验形态"
    assert "## 7. 后续阶段待办" in text
    assert "01_测试报告_前端插件化.md" in text


@pytest.mark.kiwi_id(2189)
def test_stage_report_archived_with_sections() -> None:
    """阶段测试报告归档：六节 + 附录齐备，执行数据与文档校验可复核。"""
    assert _REPORT.is_file()
    text = _REPORT.read_text(encoding="utf-8")
    for heading in (
        "用例执行统计",
        "缺陷统计",
        "覆盖率",
        "风险与遗留项",
        "复盘与经验教训",
        "附录 A",
    ):
        assert heading in text
    assert "9 条需求" in text
    assert "check-status" in text


@pytest.mark.kiwi_id(2189)
def test_task_and_domain_status_consistent() -> None:
    """三类文档状态一致：任务 05_01 与域总览子任务表的状态 / 完成日期一致。"""
    task_text = _TASK.read_text(encoding="utf-8")
    assert re.search(r"^\| 状态 \| 已完成 \|$", task_text, re.M)
    assert re.search(r"^\| 完成日期 \| 2026-09-24 \|$", task_text, re.M)
    domain_text = _DOMAIN.read_text(encoding="utf-8")
    assert re.search(r"\|\s*01\s*\|[^|]*\|[^|]*\| 已完成 \| 2026-09-24 \|", domain_text)
