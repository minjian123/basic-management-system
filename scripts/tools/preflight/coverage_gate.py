#!/usr/bin/env python3
"""覆盖率门禁（13_02）：合并并行 worker 的采集数据，导出 JSON 并判定「行 + 分支 100%」。

采集侧（`backend/bms_testing_plugin.py`）在 pytest 启动前、**早于任何被测模块导入**启动
coverage，每个进程按 pid 落一份 `<data-file>.<pid>`；本模块负责合并、导出与判定。

口径：预检（定向 / 全量）与 CI（`backend-test` / `service-test`）都只经本模块判定，
禁止再各用 `pytest --cov` / `--cov-fail-under` 另起一套——那会让「模块导入期执行的行」
落在探针启动之前，造成整片假缺口（实测曾使全仓停在 93.36%）。

用法::

    # 定向 / 服务级：只判定指定模块
    uv run python scripts/tools/preflight/coverage_gate.py --data-file backend/.coverage \\
        --out backend/coverage.json --module bms_core.db.bootstrap

    # 全量档：不限模块（报告内全部文件）
    uv run python scripts/tools/preflight/coverage_gate.py --data-file backend/.coverage \\
        --out backend/coverage.json

退出码：`0` 达标；`1` 未达标（含未采集到数据）；`2` 参数 / 环境错误。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402


@dataclass(frozen=True)
class CoverageTotals:
    """覆盖率汇总（按门禁范围过滤后）。

    Attributes:
        files: 参与判定的文件数。
        missing_lines: 未覆盖行数。
        partial_branches: 未走全的分支数。
        percent: 行 + 分支合并百分比（0~100）。
        missing_modules: 存在缺行 / 缺分支的模块名（供扩圈）。
    """

    files: int
    missing_lines: int
    partial_branches: int
    percent: float
    missing_modules: ConcurrentStableList[str]

    @property
    def passed(self) -> bool:
        """是否达标（100% 口径：无缺行、无缺分支、至少匹配到一个文件）。"""
        return self.files > 0 and self.missing_lines == 0 and self.partial_branches == 0


def data_files(data_file: Path) -> ConcurrentStableList[Path]:
    """列出待合并的采集文件（`<data-file>` 与 `<data-file>.<pid>`）。

    Args:
        data_file: 数据文件基址。

    Returns:
        tuple[Path, ...]: 存在的采集文件（按名称排序）。
    """
    candidates = [data_file, *sorted(data_file.parent.glob(f"{data_file.name}.*"))]
    return tuple(path for path in candidates if path.is_file())


def cleanup(data_file: Path) -> None:
    """清理上一轮的采集文件（每轮重跑前调用，避免数据跨轮累积）。

    Args:
        data_file: 数据文件基址。
    """
    for path in data_files(data_file):
        with contextlib.suppress(OSError):
            path.unlink()


def combine(data_file: Path) -> int:
    """合并并行 worker 的采集文件。

    Args:
        data_file: 数据文件基址。

    Returns:
        int: 合并的采集文件数（0 表示没有采集到数据）。

    Raises:
        RuntimeError: 运行环境缺 coverage。
    """
    try:
        import coverage
    except ModuleNotFoundError as error:  # pragma: no cover - 环境缺失时的显式报错
        raise RuntimeError("缺少 coverage：请用 backend 的 venv 运行（`uv run python ...`）") from error
    collected = data_files(data_file)
    if not collected:
        return 0
    instance = coverage.Coverage(data_file=str(data_file))
    instance.combine()
    instance.save()
    return len(collected)


def export_json(data_file: Path, out: Path) -> Any:
    """把合并后的数据导出为 JSON 报告。

    Args:
        data_file: 数据文件基址。
        out: JSON 报告落点。

    Returns:
        dict: 报告内容（`totals` + `files`）。

    Raises:
        RuntimeError: 运行环境缺 coverage 或数据不可读。
    """
    try:
        import coverage
    except ModuleNotFoundError as error:  # pragma: no cover - 环境缺失时的显式报错
        raise RuntimeError("缺少 coverage：请用 backend 的 venv 运行（`uv run python ...`）") from error
    out.parent.mkdir(parents=True, exist_ok=True)
    instance = coverage.Coverage(data_file=str(data_file))
    instance.load()
    instance.json_report(outfile=str(out))
    return json.loads(out.read_text(encoding="utf-8"))


def module_matches(path: str, modules: ConcurrentStableList[str]) -> bool:
    """判断报告文件是否属于给定模块（`a.b.c` ⇒ `a/b/c.py` 或 `a/b/c/__init__.py`）。

    Args:
        path: 报告里的文件路径。
        modules: 门禁范围模块；空表示全部。

    Returns:
        bool: 是否属于门禁范围。
    """
    if not modules:
        return True
    norm = path.replace("\\", "/")
    for module in modules:
        suffix = module.replace(".", "/")
        # 模块本身（`.../a/b.py` / `.../a/b/__init__.py`）或整包（`.../bms_platform/**`）
        if norm.endswith(f"{suffix}.py") or f"/{suffix}/" in f"{norm}/":
            return True
    return False


def _module_name(path: str) -> str:
    """把报告路径归一为模块名（`.../bms_core/db/keys.py` ⇒ `bms_core.db.keys`）。"""
    norm = path.replace("\\", "/")
    for marker in ("/libs/", "/services/"):
        if marker in norm:
            norm = norm.split(marker, 1)[1]
            break
    parts = norm.split("/")
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def filtered_totals(payload: Any, modules: ConcurrentStableList[str]) -> CoverageTotals:
    """按门禁范围汇总覆盖率。

    Args:
        payload: `export_json` 的报告内容。
        modules: 门禁范围模块（空表示全部）。

    Returns:
        CoverageTotals: 汇总结果。
    """
    files = payload.get("files") or {}
    matched = 0
    missing_lines = 0
    partial = 0
    covered = 0
    statements = 0
    missing_modules: ConcurrentStableList[str] = ()
    for path, entry in files.items():
        if not module_matches(str(path), modules):
            continue
        summary = entry.get("summary") or {}
        matched += 1
        lines_missing = int(summary.get("missing_lines") or 0)
        branches_partial = int(summary.get("num_partial_branches") or 0)
        missing_lines += lines_missing
        partial += branches_partial
        statements += int(summary.get("num_statements") or 0)
        covered += int(summary.get("covered_lines") or 0)
        if lines_missing or branches_partial:
            missing_modules = (*missing_modules, _module_name(str(path)))
    percent = (covered / statements * 100.0) if statements else 0.0
    return CoverageTotals(
        files=matched,
        missing_lines=missing_lines,
        partial_branches=partial,
        percent=percent,
        missing_modules=missing_modules,
    )


def describe(totals: CoverageTotals) -> str:
    """门禁结果的单行度量（供预检 / CI 日志采集）。"""
    return (
        f"[coverage] files={totals.files} missing_lines={totals.missing_lines} "
        f"partial_branches={totals.partial_branches} percent={totals.percent:.2f}"
    )


def check(
    data_file: Path,
    out: Path,
    modules: ConcurrentStableList[str] = (),
    *,
    fail_under: int = 100,
    quiet: bool = False,
) -> int:
    """合并 → 导出 → 判定（供预检 / 执行器 / CI 共用）。

    Args:
        data_file: 数据文件基址。
        out: JSON 报告落点。
        modules: 门禁范围模块（空表示全部）。
        fail_under: 门禁阈值（缺省 100，按「行 + 分支」合并百分比判定）。
        quiet: 是否抑制度量行输出。

    Returns:
        int: 退出码（0 达标 / 1 未达标 / 2 环境错误）。
    """
    module_tuple = modules
    merged = combine(data_file)
    if merged == 0:
        print(f"[coverage] 未采集到覆盖率数据（{data_file}）：不支持跳过，视为未达标", file=sys.stderr)
        return 1
    payload = export_json(data_file, out)
    totals = filtered_totals(payload, module_tuple)
    if not quiet:
        print(describe(totals))
    if totals.files == 0:
        print(f"[coverage] 门禁范围未匹配到任何文件：{'、'.join(module_tuple) or '（全部）'}", file=sys.stderr)
        return 1
    if fail_under >= 100:
        if totals.passed:
            return 0
        print(
            f"[coverage] 未达标：缺行 {totals.missing_lines} / 缺分支 {totals.partial_branches}"
            f"（{'、'.join(totals.missing_modules[:10])}）",
            file=sys.stderr,
        )
        return 1
    if totals.percent + 1e-9 >= fail_under:
        return 0
    print(f"[coverage] 未达标：{totals.percent:.2f}% < {fail_under}%", file=sys.stderr)
    return 1


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 达标 / 1 未达标 / 2 参数错误）。
    """
    parser = argparse.ArgumentParser(description="覆盖率门禁：合并并行采集数据并判定行 + 分支 100%")
    parser.add_argument("--data-file", required=True, help="覆盖率数据文件基址（如 backend/.coverage）")
    parser.add_argument("--out", required=True, help="JSON 报告落点（如 backend/coverage.json）")
    parser.add_argument("--module", action="append", default=[], help="门禁范围模块（可重复；缺省全部）")
    parser.add_argument("--fail-under", type=int, default=100, help="门禁阈值（缺省 100）")
    parser.add_argument("--quiet", action="store_true", help="不打印度量行")
    parser.add_argument("--clean", action="store_true", help="判定前先清理旧采集文件")
    args = parser.parse_args(argv)
    data_file = Path(args.data_file).resolve()
    if args.clean:
        cleanup(data_file)
    modules = tuple(str(item) for item in args.module)
    try:
        return check(data_file, Path(args.out).resolve(), modules, fail_under=args.fail_under, quiet=args.quiet)
    except RuntimeError as error:
        print(f"[coverage] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
