#!/usr/bin/env python3
"""阶段度量与用例执行统计采集（《项目规划说明》§25.2 度量 / §25.3 L1 执行链）。

**只读脚本**：不改代码、不改数据、不建 Issue，只产出数据供阶段测试报告使用
（报告结论与经验教训由 AI 汇总，再交第二 AI 交叉审核；见 §25.3）。默认不写仓库文件
（`--out` 显式指定才落 JSON）；跑测试会生成 `.coverage` / `coverage/` 等本地产物，均已被 `.gitignore` 忽略。

采集四项：

1. **阶段工期偏差**：计划「里程碑对照」的 M1 基线 vs 本阶段实际完成日（需求文档最后完成日期）
2. **缺陷分布与收敛**：GitLab Issue（`state=all`，按 `defect-auto` / 其他标签聚合）
3. **覆盖率**：后端 `pytest --cov`（TOTAL 行）+ 前端双端 `coverage-summary.json`
4. **用例执行统计**：后端 pytest 摘要 + 前端 Vitest 摘要 + Playwright（本阶段未启用）

用法::

    python3 scripts/tools/governance/collect_metrics.py
    python3 scripts/tools/governance/collect_metrics.py --with-frontend          # 重跑前端覆盖率
    python3 scripts/tools/governance/collect_metrics.py --skip-tests --out /tmp/metrics.json

退出码：0 = 采集完成（即使个别数据源降级）；2 = 根目录 / 阶段目录不存在。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REQ_META_RE = re.compile(r"^优先级：\S+（[^）]*）\u3000\|\u3000状态：(\S+)\u3000\|\u3000完成日期：(\S+)\s*$")
PYTEST_SUMMARY_RE = re.compile(r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) failed)?")
PYTEST_TOTAL_RE = re.compile(
    r"^TOTAL\s+(?P<stmts>\d+)\s+(?P<miss>\d+)\s+(?P<br>\d+)\s+(?P<brmiss>\d+)\s+(?P<pct>\d+)%", re.M
)
VITEST_TESTS_RE = re.compile(r"Tests\s+(\d+) passed")
VITEST_FILES_RE = re.compile(r"Test Files\s+(\d+) passed")
DURATION_RE = re.compile(r"in ([\d.]+)s")
PYTEST_COVERAGE_TOTAL_RE = re.compile(r"Total coverage:\s*([\d.]+)%")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """去掉终端颜色控制符（Vitest 摘要在有色输出中夹带 ANSI 转义）。"""
    return ANSI_RE.sub("", text)


def parse_env_file(path: Path) -> dict[str, str]:
    """读取键值型凭据文件（仅取需要的键，不回显值）。"""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> tuple[int, str]:
    """执行只读命令，返回 (退出码, 合并输出)。"""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:  # 命令缺失或超时按降级处理
        return 127, f"（命令未执行：{exc}）"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def collect_duration(stage_dir: Path) -> dict[str, object]:
    """度量一：阶段工期偏差（基线取计划「里程碑对照」；偏差率 = 偏差天数 / 排期长度）。"""
    plan_files = sorted((stage_dir / "计划").glob("01_计划_*.md"))
    baseline: date | None = None
    start: date | None = None
    if plan_files:
        plan_text = plan_files[0].read_text(encoding="utf-8")
        match = re.search(r"自 (\d{4}-\d{2}-\d{2}) 起排", plan_text)
        if match:
            start = date.fromisoformat(match.group(1))
        for line in plan_text.splitlines():
            if line.startswith("| M1 ") and "原 M1" in line:
                found = DATE_RE.search(line)
                if found:
                    baseline = date.fromisoformat(found.group(0))
                break
    actual: date | None = None
    for doc in sorted((stage_dir / "需求").glob("*.md")):
        if doc.name.startswith("00_"):
            continue
        for line in doc.read_text(encoding="utf-8").splitlines():
            meta = REQ_META_RE.match(line)
            if meta and meta.group(1) == "已完成" and DATE_RE.fullmatch(meta.group(2)):
                value = date.fromisoformat(meta.group(2))
                actual = value if actual is None or value > actual else actual
    if baseline is None or actual is None:
        return {"baseline": None, "actual": None, "delta_days": None, "delta_pct": None, "over_threshold": None}
    delta = (actual - baseline).days
    length = (baseline - start).days if start else 0
    pct = round(abs(delta) / length * 100, 1) if length else None
    return {
        "baseline": baseline.isoformat(),
        "plan_start": start.isoformat() if start else None,
        "actual": actual.isoformat(),
        "delta_days": delta,
        "plan_days": length or None,
        "delta_pct": pct,
        "over_threshold": bool(pct is not None and pct > 20),
    }


def collect_defects(root: Path) -> dict[str, object]:
    """度量二：缺陷分布与收敛（GitLab Issue）。"""
    env = parse_env_file(root / "deploy" / ".env")
    api = env.get("GITLAB_API_URL")
    token = env.get("GITLAB_API_TOKEN")
    if not api or not token:
        return {"available": False, "reason": "deploy/.env 缺 GITLAB_API_URL / GITLAB_API_TOKEN", "items": []}
    url = f"{api.rstrip('/')}/projects/bms%2Fbms/issues?state=all&per_page=100"
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:  # 内网自托管地址，凭据取本地 .env
            items = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # 网络 / 鉴权失败按降级处理，不阻断采集
        return {"available": False, "reason": f"GitLab API 不可达：{type(exc).__name__}", "items": []}
    rows = [
        {
            "iid": item["iid"],
            "state": item["state"],
            "title": item["title"],
            "labels": item.get("labels", []),
            "created_at": item["created_at"][:10],
            "closed_at": (item.get("closed_at") or "")[:10],
        }
        for item in items
    ]
    auto = [row for row in rows if "defect-auto" in row["labels"]]
    manual = [row for row in rows if "defect-auto" not in row["labels"] and any(str(tag).startswith("defect") for tag in row["labels"])]
    auto_like = [row for row in rows if any(str(tag).startswith("defect") for tag in row["labels"])]
    high_open = [
        row
        for row in rows
        if row["state"] == "opened"
        and any(str(tag).upper() in ("P0", "P1") for tag in row["labels"])
    ]
    return {
        "available": True,
        "total": len(rows),
        "open": sum(1 for row in rows if row["state"] == "opened"),
        "closed": sum(1 for row in rows if row["state"] == "closed"),
        "defect_auto": len(auto),
        "defect_manual": len(manual),
        "defect_labelled": len(auto_like),
        "p0_p1_open": len(high_open),
        "items": rows,
    }


def collect_coverage(root: Path, skip_tests: bool, with_frontend: bool) -> dict[str, object]:
    """度量三 + 用例执行统计：后端 pytest 与前端 Vitest。"""
    backend = root / "backend"
    backend_data: dict[str, object] = {"ran": False}
    if not skip_tests:
        code, out = run(
            ["uv", "run", "pytest", "-q", "--cov=app", "--cov-branch", "--cov-fail-under=70"],
            cwd=backend,
            timeout=900,
        )
        out = strip_ansi(out)
        total = PYTEST_TOTAL_RE.search(out)
        precise = PYTEST_COVERAGE_TOTAL_RE.search(out)
        summary = PYTEST_SUMMARY_RE.search(out)
        duration = DURATION_RE.search(out)
        backend_data = {
            "ran": True,
            "exit_code": code,
            "passed": int(summary.group(1)) if summary else None,
            "skipped": int(summary.group(2) or 0) if summary else None,
            "failed": int(summary.group(3) or 0) if summary else (1 if code else 0),
            "duration_s": float(duration.group(1)) if duration else None,
            "branches_enabled": bool(total),
            "lines_pct": float(precise.group(1)) if precise else (int(total.group("pct")) if total else None),
        }
    frontend: dict[str, object] = {}
    for name in ("apps/desktop", "apps/mobile"):
        project = root / name
        if with_frontend and not skip_tests:
            code, raw = run(["npm", "run", "test:cov"], cwd=project, timeout=900)
            out = strip_ansi(raw)
            tests = VITEST_TESTS_RE.search(out)
            files = VITEST_FILES_RE.search(out)
            frontend[name] = {
                "ran": True,
                "exit_code": code,
                "tests_passed": int(tests.group(1)) if tests else None,
                "files_passed": int(files.group(1)) if files else None,
            }
        summary_path = project / "coverage" / "coverage-summary.json"
        if summary_path.is_file():
            data = json.loads(summary_path.read_text(encoding="utf-8")).get("total", {})
            frontend.setdefault(name, {})
            frontend[name].update(  # type: ignore[union-attr]
                {
                    "coverage_lines_pct": data.get("lines", {}).get("pct"),
                    "coverage_branches_pct": data.get("branches", {}).get("pct"),
                    "coverage_functions_pct": data.get("functions", {}).get("pct"),
                    "coverage_file_mtime": date.fromtimestamp(summary_path.stat().st_mtime).isoformat(),
                }
            )
        else:
            frontend.setdefault(name, {})
            frontend[name].update({"coverage_lines_pct": None, "note": "缺 coverage-summary.json"})  # type: ignore[union-attr]
    return {"backend": backend_data, "frontend": frontend}


def main(argv: list[str] | None = None) -> int:
    """入口：采集四项并分区打印（可选落 JSON）。"""
    parser = argparse.ArgumentParser(description="阶段度量与用例执行统计采集（只读）")
    parser.add_argument("--stage", default="01_项目骨架", help="阶段目录名（默认 01_项目骨架）")
    parser.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试执行（只取已有覆盖率产物）")
    parser.add_argument("--with-frontend", action="store_true", help="重跑前端覆盖率（npm run test:cov）")
    parser.add_argument("--out", default=None, help="把结果写为 JSON（默认只打印）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    stage_dir = root / "bms文档" / "项目" / args.stage
    if not stage_dir.is_dir():
        print(f"未找到阶段目录：{stage_dir}")
        return 2

    duration = collect_duration(stage_dir)
    defects = collect_defects(root)
    coverage = collect_coverage(root, args.skip_tests, args.with_frontend)
    result = {
        "stage": args.stage,
        "collected_at": date.today().isoformat(),
        "duration": duration,
        "defects": defects,
        "coverage": coverage,
    }

    print(f"== 阶段度量采集（{args.stage}，{result['collected_at']}）==")
    print("\n[1/4] 阶段工期偏差（基线：《项目骨架计划》里程碑对照 M1）")
    if duration["baseline"]:
        print(
            f"  基线 {duration['baseline']} / 排期起点 {duration['plan_start']}（工期 {duration['plan_days']} 天）"
            f" / 实际 {duration['actual']} / 偏差 {duration['delta_days']} 天（{duration['delta_pct']}%）"
            f" / 超 20% 阈值：{'是' if duration['over_threshold'] else '否'}"
        )
    else:
        print("  未能解析基线或实际完成日期")

    print("\n[2/4] 缺陷分布与收敛（GitLab Issue）")
    if defects["available"]:
        print(
            f"  总数 {defects['total']} / 打开 {defects['open']} / 已闭环 {defects['closed']}"
            f" / 自动缺陷 {defects['defect_auto']} / 手工缺陷 {defects['defect_manual']}"
            f" / P0-P1 未清零：{defects['p0_p1_open']}"
        )
        for row in defects["items"]:
            print(f"    #{row['iid']} [{row['state']}] {row['title'][:70]} | {row['labels']}")
    else:
        print(f"  降级：{defects['reason']}")

    print("\n[3/4] 覆盖率（后端行 / 分支；前端行 / 分支）")
    backend = coverage["backend"]
    if backend.get("ran"):
        print(
            f"  后端：行/语句 {backend.get('lines_pct')}%、分支覆盖 {'已启用' if backend.get('branches_enabled') else '未启用'}"
            f"（用例 {backend.get('passed')} passed / {backend.get('skipped')} skipped / {backend.get('failed')} failed，{backend.get('duration_s')}s）"
            f" → 门禁 ≥ 70%：{'达标' if (backend.get('lines_pct') or 0) >= 70 else '不达标'}"
        )
    else:
        print("  后端：跳过测试执行（--skip-tests），无本次覆盖率")
    for name, data in coverage["frontend"].items():
        pct = data.get("coverage_lines_pct")
        print(
            f"  {name}：行 {pct}%、分支 {data.get('coverage_branches_pct')}%（产物日期 {data.get('coverage_file_mtime')}）"
            f" → 门禁 ≥ 70%：{'达标' if (pct or 0) >= 70 else '待确认'}"
        )

    print("\n[4/4] 用例执行统计")
    for name, data in coverage["frontend"].items():
        if data.get("ran"):
            print(f"  {name}：Test Files {data.get('files_passed')} passed / Tests {data.get('tests_passed')} passed")
    print("  Playwright E2E：本阶段未启用（tests/e2e 待建，重验证层分档开关 deploy/ci/verify/e2e 未开）")

    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 JSON：{args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
