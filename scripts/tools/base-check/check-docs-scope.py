#!/usr/bin/env python3
"""排期与工时落点护栏（check-docs-scope）。

口径见《计划文档规范》「排期唯一落点与边界」节与《文档生成规范》「架构节点的语义与实现分层」节：
排期与工时（状态 / 完成日期 / 工时 / 排期窗口 / 甘特 / 里程碑 / 波次）**只有两个落点**——

1. 平台《总体项目规划》（`bms文档/规划/总体项目规划.md`）；
2. 各阶段计划文档（`bms文档/项目/{阶段}/计划/**`）。

其余文档（需求 / 任务 / 任务附属记录 / 设计节点 / 规划节点 / 索引与首页 / 阶段报告等）一律不得出现，
由本脚本强制拦截。白名单：

- `bms文档/规范/**`：工时与排期字段的定义源（规范只写原则与字段契约，不承载某阶段排期数据）；
- `bms文档/资料/**`：外部服务与工具的辅助资料（描述对象是工具本身，非本项目进度）；
- `bms文档/用户文档/**`：本地资源凭据（已 gitignore）。

单行豁免：行内含 `docs-scope:allow` 标记（如引用规范原文举例）时不判定，用于极少数确需保留的
引用场景，须在行内写明理由。

用法::

    python3 scripts/tools/base-check/check-docs-scope.py [bms 仓库根]
    python3 scripts/tools/base-check/check-docs-scope.py --self-test

退出码：0 无违规；1 存在违规；2 目录缺失。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

#: 违规特征：词面 + 数据形态（工时数字 `{数字}h` 与 `{数字}.{数字}h`）。
RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"工时"), "工时字样"),
    (re.compile(r"排期"), "排期字样"),
    (re.compile(r"里程碑"), "里程碑字样"),
    (re.compile(r"甘特"), "甘特字样"),
    (re.compile(r"波次"), "波次字样"),
    (re.compile(r"工期"), "工期字样"),
    (re.compile(r"(?<![0-9A-Za-z])M\d{1,2}(?![0-9A-Za-z])"), "里程碑编号"),
    # 工时数字：`{数字}h`；带比较符（≤ < ≥ > ～）的是时长约束（如 RTO ≤4h），不判工时。
    (re.compile(r"(?<![\w.≤<≥>～~])\d+(?:\.\d+)?h(?![0-9A-Za-z])"), "工时数字"),
)

#: 行级豁免标记。
ALLOW_MARKER = "docs-scope:allow"

#: 白名单：文档根下的相对路径前缀（目录）与精确文件。
WHITELIST_DIRS = ("规范/", "资料/", "用户文档/")
WHITELIST_FILES = ("规划/总体项目规划.md",)

#: 阶段计划目录（`项目/{阶段}/计划/`）。
PLAN_DIR_RE = re.compile(r"^项目/[^/]+/计划/")


def is_whitelisted(rel: str) -> bool:
    """判断文档根下的相对路径是否在白名单内。

    Args:
        rel: 相对 `bms文档/` 的 POSIX 路径。

    Returns:
        bool: 白名单内（可不写排期与工时）为 True。
    """
    if rel in WHITELIST_FILES:
        return True
    if rel.startswith(WHITELIST_DIRS):
        return True
    return bool(PLAN_DIR_RE.match(rel))


def scan_text(text: str) -> tuple[tuple[int, str, str], ...]:
    """扫描单份文档正文，返回违规清单。

    Args:
        text: 文档正文。

    Returns:
        tuple[tuple[int, str, str], ...]: (行号, 违规类型, 命中片段) 列表。
    """
    findings: ConcurrentStableList[tuple[int, str, str]] = ConcurrentStableList()
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern, label in RULES:
            match = pattern.search(line)
            if match:
                findings.add((number, label, match.group(0)))
                break
    return findings


def iter_docs(docs_root: Path) -> tuple[Path, ...]:
    """列出文档根下全部 Markdown 文档（排除白名单）。

    Args:
        docs_root: `bms文档/` 目录。

    Returns:
        tuple[Path, ...]: 待检文档路径（按路径排序）。
    """
    result = []
    for path in sorted(docs_root.rglob("*.md")):
        rel = path.relative_to(docs_root).as_posix()
        if is_whitelisted(rel):
            continue
        result.append(path)
    return tuple(result)


def check(root: Path) -> int:
    """执行全量检查并打印结果。

    Args:
        root: bms 仓库根目录。

    Returns:
        int: 退出码（0 无违规 / 1 有违规 / 2 目录缺失）。
    """
    docs_root = root / "bms文档"
    if not docs_root.is_dir():
        print(f"未找到文档根目录：{docs_root}")
        return 2
    violations = 0
    checked = 0
    for path in iter_docs(docs_root):
        checked += 1
        findings = scan_text(path.read_text(encoding="utf-8"))
        if not findings:
            continue
        violations += len(findings)
        rel = path.relative_to(docs_root)
        for number, label, snippet in findings:
            print(f"{rel}:{number}: [{label}] {snippet}")
    print(f"\n[check-docs-scope] 检查 {checked} 份文档：违规 {violations} 处")
    if violations:
        print("排期与工时只允许出现在《总体项目规划》与各阶段计划文档；详见《计划文档规范》「排期唯一落点与边界」节")
        return 1
    return 0


def _self_test() -> int:
    """自检：规则与白名单的判定是否与口径一致。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    failures: ConcurrentStableList[str] = ConcurrentStableList()

    def expect(name: str, actual: object, wanted: object) -> None:
        if actual != wanted:
            failures.add(f"{name}: 实际 {actual!r}，期望 {wanted!r}")

    expect("工时数字", bool(scan_text("本任务 4h 交付")), True)
    expect("小数工时", bool(scan_text("合计 34.5h")), True)
    expect("工时字样", bool(scan_text("工时台账已回写")), True)
    expect("排期字样", bool(scan_text("剩余排期见计划")), True)
    expect("里程碑编号", bool(scan_text("M1 门禁达成")), True)
    expect("甘特字样", bool(scan_text("甘特图见计划")), True)
    expect("波次字样", bool(scan_text("按波次推进")), True)
    expect("工期字样", bool(scan_text("工期偏差 20%")), True)
    expect("合规正文", bool(scan_text("本任务交付会话管理三端点，用例 Kiwi 2195")), False)
    expect("时长约束非工时", bool(scan_text("恢复：RTO ≤4h、RPO ≤1h")), False)
    expect("小数非工时", bool(scan_text("版本 3.14 与 1.5 倍")), False)
    expect("豁免标记", bool(scan_text('见《计划文档规范》「排期窗口格式」节 <!-- docs-scope:allow:引用规范原文 -->')), False)
    expect("白名单-规范", is_whitelisted("规范/计划文档规范.md"), True)
    expect("白名单-总体规划", is_whitelisted("规划/总体项目规划.md"), True)
    expect("白名单-阶段计划", is_whitelisted("项目/06_认证与安全/计划/01_计划_认证与安全.md"), True)
    expect("白名单-资料", is_whitelisted("资料/开发服务器/linux/Docker部署使用说明.md"), True)
    expect("非白名单-任务", is_whitelisted("项目/06_认证与安全/任务/01_认证与会话/01_认证与会话.md"), False)
    expect("非白名单-架构节点", is_whitelisted("设计/架构设计/03_架构设计_总体架构.md"), False)
    expect("非白名单-需求", is_whitelisted("项目/06_认证与安全/需求/00_需求_认证与安全.md"), False)
    expect("非白名单-首页", is_whitelisted("文档首页.md"), False)
    expect("非白名单-其他规划", is_whitelisted("规划/项目规划说明.md"), False)

    if failures:
        print("[check-docs-scope --self-test] 失败：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("[check-docs-scope --self-test] 全部通过")
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（默认取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    args = tuple(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return _self_test()
    paths = [item for item in args if not item.startswith("-")]
    return check(Path(paths[0] if paths else ".").resolve())


if __name__ == "__main__":
    sys.exit(main())
