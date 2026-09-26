"""M2 阶段收口核对（Kiwi 2188）：门禁结论、报告归档与状态一致性（文档断言）。"""

import re
from pathlib import Path

import pytest

_STAGE = Path(__file__).resolve().parents[5] / "bms文档" / "项目" / "02_后端基座与服务化地基"
_REPORT = _STAGE / "01_测试报告_后端基座与服务化地基.md"
_PLAN = _STAGE / "计划" / "01_计划_后端基座与服务化地基.md"
_TASK = (
    _STAGE
    / "任务"
    / "10_阶段验收"
    / "10_阶段验收_01_阶段验收门禁核对与测试报告"
    / "10_阶段验收_01_阶段验收门禁核对与测试报告.md"
)
_DOMAIN = _STAGE / "任务" / "10_阶段验收" / "10_阶段验收.md"

_GATES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")


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
    ]


@pytest.mark.kiwi_id(2188)
def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁表 14 行均有结论与证据索引（计划 §5），且 S1~S7 与 M2 达成逐条在表。

    门禁结论落计划 §5（需求文档不承载进度与验收证据，见《需求文档规范》「进度口径」节）：
    本断言核对 14 行结构完整、结论非空，并覆盖服务化地基 S1~S7 与里程碑对照。
    """
    plan_text = _PLAN.read_text(encoding="utf-8")
    gate_section = plan_text.split("## 5. M2 验收门禁", 1)[1].split("## 6.", 1)[0]
    gate_rows = _table_rows(gate_section.split("**里程碑对照**", 1)[0])
    assert len(gate_rows) == 14
    for row in gate_rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3
        assert cells[1] != ""  # 对应任务非空
        evidence = cells[2]  # 达成路径（结论与证据）
        assert len(evidence) > 10
        assert evidence != "—"
    for gate in _GATES:
        assert f"**服务化地基 {gate} " in gate_section, f"门禁表缺 {gate} 行"
    assert "**里程碑对照**" in gate_section
    assert "2026-09-24 达成" in gate_section


@pytest.mark.kiwi_id(2188)
def test_plan_closure_state() -> None:
    """计划收口状态：头部计数与已完成 / 剩余表行数一致、工时行自洽、甘特里程碑、报告引用齐备。

    头部项数不写死（防后续阶段回写漂移 / 重开追加子任务），改为校验结构自洽：
    「已完成 N 项，剩余 M 项」且 N / M 分别等于「已完成任务 / 剩余任务排期」表数据行数；
    工时行校验「已完成 + 剩余 = 阶段合计」。
    """
    text = _PLAN.read_text(encoding="utf-8")
    match = re.search(r"已完成\s*(\d+)\s*项，剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section)
    assert int(match.group(1)) == len(done_rows), "头部已完成项数应与已完成任务表行数一致"
    todo_section = text.split("## 3. 剩余任务排期", 1)[1].split("## 4.", 1)[0]
    todo_rows = _table_rows(todo_section)
    assert int(match.group(2)) == len(todo_rows), "头部剩余项数应与剩余任务排期表行数一致"
    assert "M2" in text and "milestone" in text
    hours = re.search(
        r"已完成\s*\*{0,2}(\d+)h\*{0,2}；剩余\s*\*{0,2}(\d+)h\*{0,2}.*?阶段合计\s*\*{0,2}(\d+)h\*{0,2}",
        text,
    )
    assert hours, "计划工时行应为 check-status S1 可校验形态"
    assert int(hours.group(1)) + int(hours.group(2)) == int(hours.group(3)), "工时：已完成 + 剩余 应等于阶段合计"
    assert "01_测试报告_后端基座与服务化地基.md" in text


@pytest.mark.kiwi_id(2188)
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
    assert re.search(r"\d+ passed, \d+ skipped", text)
    assert "check-status" in text
    assert "31 条需求" in text


@pytest.mark.kiwi_id(2188)
def test_task_and_domain_status_consistent() -> None:
    """三类文档状态一致：任务 10_01 与域总览子任务表的状态 / 完成日期一致。"""
    task_text = _TASK.read_text(encoding="utf-8")
    assert re.search(r"^\| 状态 \| 已完成 \|$", task_text, re.M)
    assert re.search(r"^\| 完成日期 \| 2026-09-24 \|$", task_text, re.M)
    domain_text = _DOMAIN.read_text(encoding="utf-8")
    assert re.search(r"\|\s*01\s*\|[^|]*\|[^|]*\| 已完成 \| 2026-09-24 \|", domain_text)
