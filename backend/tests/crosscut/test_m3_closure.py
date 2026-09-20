"""M3 阶段收口核对（Kiwi 663 / 664）：门禁结论、报告归档与状态一致性（文档断言）。"""

import re
from pathlib import Path

import pytest

_STAGE = Path(__file__).resolve().parents[3] / "bms文档" / "项目" / "03_后端插件化"
_REPORT = _STAGE / "01_测试报告_后端插件化.md"
_OVERVIEW = _STAGE / "需求" / "00_需求_后端插件化.md"
_PLAN = _STAGE / "计划" / "01_计划_后端插件化.md"


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
    ]


@pytest.mark.kiwi_id(663)
def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁表 8 项均有结论与达成路径（计划 §5）；需求总览标明 11 条全部完成、门禁 8/8 达标。

    门禁表随排期清理迁至计划 §5（需求文档不承载进度与门禁），故本断言读计划核对 8 项结论 / 达成路径；
    需求完成口径由需求总览进度注文承载。
    """
    plan_text = _PLAN.read_text(encoding="utf-8")
    gate_section = plan_text.split("## 5. M3 验收门禁", 1)[1].split("## 6.", 1)[0]
    gate_rows = _table_rows(gate_section)
    assert len(gate_rows) == 8
    for row in gate_rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3
        assert cells[1] != ""  # 对应任务非空
        evidence = cells[2]  # 达成路径（结论与证据）
        assert len(evidence) > 10
        assert evidence != "—"

    overview_text = _OVERVIEW.read_text(encoding="utf-8")
    assert "11 条需求全部完成" in overview_text
    assert "8/8 达标" in overview_text


@pytest.mark.kiwi_id(663)
def test_plan_closure_state() -> None:
    """计划收口状态：头部计数与已完成任务表一致且剩余 0、甘特 M3 里程碑、报告引用齐备。

    头部项数不写死（任务会随收口后遗留处理增减），改为校验结构自洽：
    「已完成 N 项，剩余 0 项」且 N 等于「已完成任务」表数据行数。
    """
    text = _PLAN.read_text(encoding="utf-8")
    match = re.search(r"已完成\s*(\d+)\s*项[，,]\s*剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    assert match.group(2) == "0", "阶段收口后剩余项应为 0"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section)
    assert int(match.group(1)) == len(done_rows), "头部已完成项数应与已完成任务表行数一致"
    assert "M3" in text and "milestone" in text
    assert "01_测试报告_后端插件化.md" in text


@pytest.mark.kiwi_id(664)
def test_stage_report_archived_with_sections() -> None:
    """阶段测试报告归档：六节 + 附录齐备，执行数据可复核。"""
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
    assert "547 passed" in text
    assert "check-links" in text
