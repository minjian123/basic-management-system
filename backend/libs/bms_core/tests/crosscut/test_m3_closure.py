"""M3 阶段收口核对（Kiwi 663 / 664）：门禁结论、报告归档与状态一致性（文档断言）。"""

from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet

_STAGE = Path(__file__).resolve().parents[5] / "bms文档" / "项目" / "03_后端插件化"
_REPORT = _STAGE / "01_测试报告_后端插件化.md"
_OVERVIEW = _STAGE / "需求" / "00_需求_后端插件化.md"
_PLAN = _STAGE / "计划" / "01_计划_后端插件化.md"


def _table_rows(section: str) -> ConcurrentStableList[str]:
    """取 Markdown 表格数据行（去表头与分隔行）。

    Args:
        section: 片段文本。

    Returns:
        ConcurrentStableList[str]: 数据行列表。
    """
    return ConcurrentStableList(
        [
            line
            for line in section.splitlines()
            if line.startswith("| ")
            and "---" not in line
            and not line.startswith("| 编号 ")
            and not line.startswith("| 验收点 ")
        ]
    )


@pytest.mark.kiwi_id(663)
def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁表 8 项均有结论与达成路径（计划 §5）；需求总览标明 12 条中 11 条完成（01-4 触发式）、门禁 8/8 达标。

    门禁表随排期清理迁至计划 §5（需求文档不承载进度与门禁），故本断言读计划核对 8 项结论 / 达成路径；
    需求完成口径由需求总览进度注文承载（01-4 为触发式接口占位，未触发前不完成，故完成数为 11）。
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
    assert "共 12 条需求" in overview_text
    assert "11 条需求完成" in overview_text
    assert "01-4" in overview_text and "触发式" in overview_text
    assert "8/8 达标" in overview_text


@pytest.mark.kiwi_id(663)
def test_plan_closure_state() -> None:
    """计划收口状态：已完成 / 剩余两表互斥、剩余项为触发式、甘特 M3 里程碑、报告引用齐备。

    2026-10-24 修订（`302f429e` 精简 8 份阶段计划后）：计划头部不再复述项数，进度只在两张明细表，
    故改为校验两表**任务编号互斥**；阶段已达成时剩余项应为触发式（需求 01-4 / 任务 01-3-1）。
    """
    text = _PLAN.read_text(encoding="utf-8")
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section)
    todo_section = text.split("## 3. 剩余任务排期", 1)[1].split("### 3.1", 1)[0]
    todo_rows = _table_rows(todo_section)
    assert done_rows, "已完成任务表不得为空"
    assert not (_row_ids(done_rows) & _row_ids(todo_rows)), "同一任务不得同时登记在已完成与剩余两表"
    if todo_rows:
        assert "触发式" in todo_rows[0], "阶段已达成后剩余项应为触发式"
    assert "M3" in text and "milestone" in text
    assert "01_测试报告_后端插件化.md" in text


def _row_ids(rows: ConcurrentStableList[str]) -> ConcurrentStableSet[str]:
    """取表格数据行的首列（任务编号）集合。

    Args:
        rows: 表格数据行。

    Returns:
        ConcurrentStableSet[str]: 编号集合。
    """
    return ConcurrentStableSet(row.strip("|").split("|")[0].strip() for row in rows)


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
