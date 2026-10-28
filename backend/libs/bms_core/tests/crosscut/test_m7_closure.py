"""M7 阶段收口核对（Kiwi 2349）：门禁结论、报告归档、状态一致性与 mdm 口径锁定（文档断言）。"""

import re
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_ROOT = Path(__file__).resolve().parents[5]
_STAGE = _ROOT / "bms文档" / "项目" / "07_RBAC基础模块"
_REPORT = _STAGE / "01_测试报告_RBAC基础模块.md"
_PLAN = _STAGE / "计划" / "01_计划_RBAC基础模块.md"
_OVERVIEW = _STAGE / "需求" / "00_需求_RBAC基础模块.md"
_TASK = (
    _STAGE
    / "任务"
    / "05_阶段验收"
    / "05_阶段验收_01_阶段验收门禁核对与测试报告"
    / "05_阶段验收_01_阶段验收门禁核对与测试报告.md"
)
_DOMAIN = _STAGE / "任务" / "05_阶段验收" / "05_阶段验收.md"

_CLOSURE_DAY = "2026-10-24"
"""收口达成日期（门禁结论与计划登记同源）。"""


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
            and not line.startswith("| 里程碑 ")
            and not line.startswith("| # ")
        ]
    )


@pytest.mark.kiwi_id(2349)
def test_gate_table_has_conclusions_and_evidence() -> None:
    """门禁表 7 行均有结论与证据索引（计划 §5），含门禁对照与里程碑对照。

    门禁结论落计划 §5（需求文档不承载进度与验收证据，见《需求文档规范》「进度口径」节）：
    本断言核对 7 行结构完整、结论非空，覆盖门禁对照 / 里程碑对照，并确认需求总览不含门禁表。
    """
    plan_text = _PLAN.read_text(encoding="utf-8")
    gate_section = plan_text.split("## 5. M7 验收门禁", 1)[1].split("## 6.", 1)[0]
    gate_rows = _table_rows(gate_section.split("**门禁对照**", 1)[0])
    assert len(gate_rows) == 7
    for row in gate_rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3
        assert cells[1] != ""  # 对应任务非空
        evidence = cells[2]  # 达成路径（结论与证据索引）
        assert len(evidence) > 10
        assert evidence != "—"
    assert "**里程碑对照**" in gate_section
    assert "**门禁对照**" in gate_section
    assert f"{_CLOSURE_DAY} 达成" in gate_section

    overview_text = _OVERVIEW.read_text(encoding="utf-8")
    assert "| 验收点 |" not in overview_text, "需求总览不应承载门禁表"
    assert "07-8" in overview_text


@pytest.mark.kiwi_id(2349)
def test_plan_closure_state() -> None:
    """计划收口状态：头部计数与两张明细表一致、进度含达成节点、工时行可校验。

    头部项数不写死（防阶段回写漂移），改为校验结构自洽（口径同 check_status S1）：
    「已完成 N 项，剩余 M 项」中 N / M 分别等于「已完成任务」表与「剩余任务排期」表数据行数。
    """
    text = _PLAN.read_text(encoding="utf-8")
    match = re.search(r"已完成\s*(\d+)\s*项，剩余\s*(\d+)\s*项", text)
    assert match, "计划头部应写明「已完成 N 项，剩余 M 项」"
    done_section = text.split("## 2. 已完成任务", 1)[1].split("## 3.", 1)[0]
    done_rows = _table_rows(done_section)
    assert int(match.group(1)) == len(done_rows), "头部已完成项数应与已完成任务表行数一致"
    todo_section = text.split("## 3. 剩余任务排期", 1)[1].split("## 4.", 1)[0]
    todo_rows = _table_rows(todo_section)
    assert int(match.group(2)) == len(todo_rows), "头部剩余项数应与剩余排期表行数一致（收口后自然为 0）"
    assert "M7" in text and "milestone" in text
    hours = re.search(
        r"已完成\s*\*{0,2}(\d+)h\*{0,2}；剩余\s*\*{0,2}(\d+)h\*{0,2}.*?阶段合计\s*\*{0,2}(\d+)h\*{0,2}",
        text,
    )
    assert hours, "计划工时行应为 check_status S1 可校验形态"
    assert int(hours.group(1)) + int(hours.group(2)) == int(hours.group(3)), "已完成与剩余工时应等于阶段合计"
    assert "## 7. 后续阶段待办" in text
    assert "01_测试报告_RBAC基础模块.md" in text


@pytest.mark.kiwi_id(2349)
def test_stage_report_archived_with_sections() -> None:
    """阶段测试报告归档：六节 + 界面一致性节 + 附录齐备，执行数据与文档校验可复核。"""
    assert _REPORT.is_file()
    text = _REPORT.read_text(encoding="utf-8")
    for heading in (
        "用例执行统计",
        "缺陷统计",
        "覆盖率",
        "风险与遗留项",
        "界面交付 ↔ 原型 / 布局一致性",
        "复盘与经验教训",
        "附录 A",
    ):
        assert heading in text
    assert "17 条需求" in text
    assert "check_status" in text


@pytest.mark.kiwi_id(2349)
def test_task_and_domain_status_consistent() -> None:
    """进度口径：任务文档 / 域总览不承载状态与完成日期，唯一落点为阶段计划表。"""
    task_text = _TASK.read_text(encoding="utf-8")
    assert not re.search(r"^\| 状态 \|", task_text, re.M), "任务文档不得承载状态字段（进度唯一落点为计划表）"
    assert not re.search(r"^\| 完成日期 \|", task_text, re.M), "任务文档不得承载完成日期（进度唯一落点为计划表）"
    domain_text = _DOMAIN.read_text(encoding="utf-8")
    assert not re.search(r"\|\s*01\s*\|[^|]*\|[^|]*\|\s*已完成\s*\|", domain_text), (
        "域总览子任务表不得承载状态列（进度唯一落点为计划表）"
    )
    plan_text = _PLAN.read_text(encoding="utf-8")
    assert re.search(rf"^\| 05_01 \|[^|]*\|[^|]*\| {_CLOSURE_DAY} \|", plan_text, re.M), (
        "阶段计划表须登记 05_01 已完成与完成日期"
    )


@pytest.mark.kiwi_id(2349)
def test_mdm_alignment_lockdown() -> None:
    """mdm 口径锁定：服务标识 `org` → `mdm` 的消费面不再回退。

    2026-10-23 mdm 阶段一 `01_05` 完成服务标识归并；本轮阶段收口把 bms 侧消费方一并
    对齐（服务键 / 出口路径 / 内部写通道 / 分支 `op` / 服务身份白名单 / 前端产品命名空间）。
    本断言按**源码文本**核对，避免基座用例反向依赖服务包。
    """
    platform_src = _ROOT / "backend" / "services" / "platform" / "src" / "bms_platform"
    guards = {
        platform_src / "domains" / "role" / "services" / "permission_subject.py": (
            "CAPABILITY_MDM_USER_ROLES",
            "resolve_capability(",
        ),
        # 两个写通道文件已收编（03_01 第二批）：服务键 / 路径 / 动作名一律取自已解析的能力声明
        platform_src / "domains" / "user" / "services" / "user_assignments.py": (
            "CAPABILITY_MDM_USER_POSTS",
            "resolve_capability(",
            "branch_target(",
        ),
        platform_src / "domains" / "role" / "services" / "role_assignments.py": (
            "CAPABILITY_MDM_ROLE_POSTS",
            "resolve_capability(",
            "branch_target(",
        ),
        platform_src / "domains" / "user" / "api" / "internal_users.py": ("require_capability(",),
        # 权限三处出口（失效 + 两项只读）已全部按能力分配判定：不得再残留 identity 白名单
        platform_src / "domains" / "permission_meta" / "api" / "permission.py": (
            "require_capability(",
            "CAPABILITY_PLATFORM_PERMISSION_SUBJECT",
            "CAPABILITY_PLATFORM_PERMISSION_METADATA",
        ),
        platform_src / "domains" / "platform_config" / "api" / "internal_config.py": (
            "require_capability_or_service(",
        ),
    }
    for path, needles in guards.items():
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text, f"{path.name} 应含能力声明口径：{needle}"
        assert "/api/v1/org" not in text, f"{path.name} 不得残留旧路径 /api/v1/org"
        assert "/api/v1/mdm" not in text, f"{path.name} 不得残留对端路径字面量（应取自已解析的能力声明）"
        assert 'require_service("org")' not in text, f"{path.name} 不得残留旧白名单 org"

    # 权限三处出口全部改能力分配后，该文件不得再出现 identity 白名单依赖
    # （`internal_users` 的 profile / reset-target / create 仍属平台内部白名单，不在本断言范围）
    permission_api = (platform_src / "domains" / "permission_meta" / "api" / "permission.py").read_text(
        encoding="utf-8"
    )
    assert 'require_service("identity")' not in permission_api, (
        "权限出口不得残留平台内部白名单 identity（已改能力分配）"
    )

    frontend = _ROOT / "frontend"
    org_source = (frontend / "packages" / "ui_ep" / "src" / "utils" / "orgSource.ts").read_text(encoding="utf-8")
    assert "productPrefix('mdm', 'mdm')" in org_source
    endpoints = (frontend / "apps" / "desktop" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "'/api/mdm/v1/mdm'" in endpoints
    assert "/api/mdm/v1/org" not in endpoints
