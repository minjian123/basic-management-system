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
    """门禁表 8 项均有结论（达标）与证据索引；需求总清单 11 条全部已完成。"""
    text = _OVERVIEW.read_text(encoding="utf-8")
    gate_section = text.split("## 4. M3 验收门禁", 1)[1].split("## 5.", 1)[0]
    gate_rows = _table_rows(gate_section)
    assert len(gate_rows) == 8
    for row in gate_rows:
        assert "达标" in row
        evidence = row.rsplit("|", 2)[1].strip()
        assert len(evidence) > 10
        assert evidence != "—"

    list_section = text.split("## 3. 需求总清单", 1)[1].split("## 4.", 1)[0]
    requirement_rows = _table_rows(list_section)
    assert len(requirement_rows) == 11
    assert all("已完成" in row for row in requirement_rows)


@pytest.mark.kiwi_id(663)
def test_plan_closure_state() -> None:
    """计划收口状态：头部计数 11/11、甘特 M3 里程碑、报告引用齐备。"""
    text = _PLAN.read_text(encoding="utf-8")
    assert re.search(r"已完成\s*11\s*项", text)
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
