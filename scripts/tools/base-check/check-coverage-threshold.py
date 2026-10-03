#!/usr/bin/env python3
"""认证模块路径级覆盖率门禁（04_04）。

口径：核心模块（认证）行覆盖率 ≥80%，按**路径子阈值**校验——既有的整体 / 服务级
`--cov-fail-under=70` 保持不动，本门禁在其之上对认证相关路径集合单独设 80% 阈值：

1. 认证（identity 服务）：`services/identity/src/bms_identity/`；
2. 认证（bms_core 横切）：`api/base.py`（登录态依赖）、`session`、`security`、`captcha`、
   `ratelimit`、`permission`、`masking`、`idp`、`oauth`。

数据源为 coverage.py JSON 报告（`pytest --cov-report=json:coverage.json`；文件键以 `backend/`
为基准，脚本按后缀匹配归一）。新增模块（RBAC / 工作流）接入时，在 `_COVERAGE_GROUPS` 追加条目
并同步 `--self-test`。由 CI `backend-test`（硬门禁）与 preflight（本地同口径）调用。

用法::

    python3 scripts/tools/base-check/check-coverage-threshold.py [bms 仓库根] [--coverage-json <path>]
    python3 scripts/tools/base-check/check-coverage-threshold.py --self-test

退出码：0 全部达标；1 存在未达标或口径异常（无匹配文件 / 语句数为 0）；2 覆盖率数据缺失或不可解析。
"""

import json
import sys
from pathlib import Path

#: 覆盖率路径组：(组名, 阈值百分比, 路径后缀元组)。文件键以 `backend/` 为基准，按后缀匹配。
_COVERAGE_GROUPS = (
    ("认证（identity 服务）", 80, ("services/identity/src/bms_identity/",)),
    (
        "认证（bms_core 横切）",
        80,
        (
            "libs/bms_core/src/bms_core/api/base.py",
            "libs/bms_core/src/bms_core/session/",
            "libs/bms_core/src/bms_core/security/",
            "libs/bms_core/src/bms_core/captcha/",
            "libs/bms_core/src/bms_core/ratelimit/",
            "libs/bms_core/src/bms_core/permission/",
            "libs/bms_core/src/bms_core/masking/",
            "libs/bms_core/src/bms_core/idp/",
            "libs/bms_core/src/bms_core/oauth/",
        ),
    ),
)

#: 默认覆盖率报告路径（相对仓库根）。
_DEFAULT_REPORT = "backend/coverage.json"


def normalize_key(key):
    """归一覆盖率文件键（统一分隔符、去 `./` 与前导斜杠），便于后缀匹配。

    Args:
        key: coverage JSON 的文件键。

    Returns:
        str: 归一后的键。
    """
    text = key.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def summarize(files):
    """把 coverage JSON 的 `files` 归一为文件摘要列表。

    Args:
        files: coverage JSON 的 `files` 映射（键 → `{"summary": {...}}`）。

    Returns:
        list: 元素为 `(归一键, covered_lines, num_statements)`；结构异常项跳过。
    """
    summary = []
    for raw_key, item in files.items():
        if not isinstance(item, dict):
            continue
        stat = item.get("summary")
        if not isinstance(stat, dict):
            continue
        covered = stat.get("covered_lines")
        total = stat.get("num_statements")
        if not isinstance(covered, int) or not isinstance(total, int):
            continue
        summary.append((normalize_key(str(raw_key)), covered, total))
    return summary


def evaluate(summary, groups=_COVERAGE_GROUPS):
    """按路径组评估行覆盖率，返回行清单与问题清单（纯函数，便于自检）。

    Args:
        summary: `summarize` 的输出（归一文件摘要）。
        groups: 路径组声明（默认模块级 `_COVERAGE_GROUPS`）。

    Returns:
        tuple: `(rows, problems)`——rows 元素为 `(组名, 匹配文件数, 实测百分比或 None, 阈值)`；
        problems 为问题描述元组（空表示全部达标）。
    """
    rows = []
    problems = []
    for name, threshold, suffixes in groups:
        covered = 0
        total = 0
        matched = 0
        for key, cov, num in summary:
            if any(key.endswith(suffix) or suffix in key for suffix in suffixes):
                matched += 1
                covered += cov
                total += num
        if matched == 0:
            rows.append((name, 0, None, threshold))
            problems.append(f"{name}：无匹配文件（覆盖率数据键口径漂移或遗漏）")
            continue
        if total <= 0:
            rows.append((name, matched, None, threshold))
            problems.append(f"{name}：语句数为 0，无法计算覆盖率")
            continue
        percent = covered * 100.0 / total
        rows.append((name, matched, percent, threshold))
        if percent < threshold:
            problems.append(f"{name}：行覆盖率 {percent:.1f}% < 阈值 {threshold}%")
    return tuple(rows), tuple(problems)


def check_coverage_thresholds(summary, groups=_COVERAGE_GROUPS):
    """仅返回问题清单（`evaluate` 的简化出口）。

    Args:
        summary: 归一文件摘要。
        groups: 路径组声明。

    Returns:
        tuple: 问题描述元组（空表示全部达标）。
    """
    return evaluate(summary, groups)[1]


def _self_test():
    """自检：正常达标通过；低于阈值 / 无匹配 / 空语句 / 部分组缺失四类反例被拦截。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    identity_file = ("services/identity/src/bms_identity/api/auth.py", 90, 100)
    core_file = ("libs/bms_core/src/bms_core/api/base.py", 85, 100)
    irrelevant = ("services/file/src/bms_file/api/file.py", 10, 10)
    cases = [
        ("正常达标", [identity_file, core_file], 0),
        ("identity 低于阈值", [("services/identity/src/bms_identity/api/auth.py", 70, 100), core_file], 1),
        ("无匹配文件", [irrelevant], 2),
        ("语句数为 0", [("services/identity/src/bms_identity/api/auth.py", 0, 0), core_file], 1),
        ("横切组缺失", [identity_file], 1),
    ]
    bad = 0
    for title, summary, expect in cases:
        found = check_coverage_thresholds(summary)
        flag = "OK" if len(found) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(found)} 项")
    print(f"\n[check-coverage-threshold self-test] {'通过' if not bad else '不通过'}：断言用例 {len(cases)} 个")
    return 1 if bad else 0


def _parse_args(argv):
    """解析命令行：位置参数（仓库根）与 `--coverage-json` 取值。

    Args:
        argv: `sys.argv[1:]`。

    Returns:
        tuple: `(仓库根 Path, 报告路径 Path)`。
    """
    report_arg = None
    positional = []
    index = 0
    while index < len(argv):
        if argv[index] == "--coverage-json" and index + 1 < len(argv):
            report_arg = argv[index + 1]
            index += 2
            continue
        if not argv[index].startswith("-"):
            positional.append(argv[index])
        index += 1
    root = Path(positional[0] if positional else ".").resolve()
    report = Path(report_arg).resolve() if report_arg else root / _DEFAULT_REPORT
    return root, report


def main():
    """入口：读取覆盖率 JSON 并按路径组校验子阈值。

    Returns:
        int: 退出码。
    """
    if "--self-test" in sys.argv:
        return _self_test()
    _, report = _parse_args(sys.argv[1:])
    if not report.is_file():
        print(f"[check-coverage-threshold] 覆盖率报告缺失：{report}")
        print("  先跑 `uv run pytest --cov-report=json:coverage.json ...`（或在 CI backend-test 内）再校验")
        return 2
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        files = payload["files"]
    except (ValueError, KeyError, TypeError) as exc:
        print(f"[check-coverage-threshold] 覆盖率报告不可解析：{exc}")
        return 2
    rows, problems = evaluate(summarize(files))
    for name, matched, percent, threshold in rows:
        actual = "无匹配文件" if percent is None else f"{percent:.1f}%"
        if percent is not None and percent >= threshold:
            mark = "通过"
        else:
            mark = "未达标" if percent is not None else "口径异常"
        print(f"  {name}：{actual}（匹配文件 {matched}，阈值 {threshold}%）{mark}")
    if problems:
        print(f"\n[check-coverage-threshold] 不通过：{len(problems)} 项")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("\n[check-coverage-threshold] 通过：认证相关路径行覆盖率均达阈值")
    return 0


if __name__ == "__main__":
    sys.exit(main())
