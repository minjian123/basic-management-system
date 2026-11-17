"""帮助覆盖率台账命令行实现（08_04）。

入口是 `ops.help_coverage` 薄壳；本模块负责参数解析、平台库连接、豁免 / 基线读取与输出，
判定逻辑全部在 `bms_core.help.coverage`（纯函数引擎），保证命令行与接口数字一致。

退出码：`0` 成功（含告警）/ `1` 强档存在豁免后缺口或对账不一致 / `2` 参数、配置、库或豁免文件错误。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.help.coverage import (
    COVERAGE_KIND_ACTION,
    COVERAGE_KIND_MENU,
    HelpCoverageBaselineError,
    HelpCoverageExemptionError,
    HelpCoverageLedger,
    HelpCoverageScope,
    build_baseline_diff,
    build_help_coverage_ledger,
    ledger_is_blocked,
    load_help_coverage_exemptions,
    render_json,
    render_markdown,
    render_text,
)
from bms_core.repositories.help_coverage import load_help_coverage_snapshot
from bms_core.tenant.seed.tenant import resolve_url

__all__ = ["build_parser", "main"]

_STRICT_ENV = "BMS_HELP_COVERAGE_STRICT"
"""强档环境变量（`--strict` 优先）。"""

_TRUE_VALUES = ConcurrentStableList(("1", "true", "yes", "on"))
"""环境变量真值集合（大小写不敏感）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="帮助覆盖率台账（按钮 / 菜单对账，分产品与模块）")
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="输出格式（text / json / markdown，缺省 text）",
    )
    parser.add_argument("--output", default="", help="写入文件（与终端输出同内容；缺省只打印）")
    parser.add_argument("--strict", action="store_true", help="强档：存在豁免后缺口或对账不一致即退出码 1")
    parser.add_argument("--exemptions", action="append", default=[], help="豁免文件路径（可重复；给出即覆盖配置）")
    parser.add_argument("--as-of", default="", help="判定日期 YYYY-MM-DD（缺省当天）")
    parser.add_argument("--baseline", default="", help="上次 JSON 台账，输出覆盖增减与缺口新增 / 消除")
    parser.add_argument("--product-key", action="append", default=[], help="产品过滤（可重复）")
    parser.add_argument("--module-key", action="append", default=[], help="模块过滤（可重复）")
    parser.add_argument(
        "--kind",
        action="append",
        choices=(COVERAGE_KIND_ACTION, COVERAGE_KIND_MENU),
        default=[],
        help="明细类别过滤（可重复；不影响摘要与对账）",
    )
    parser.add_argument("--include-covered", action="store_true", help="明细包含已覆盖行")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（缺省取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (HelpCoverageExemptionError, HelpCoverageBaselineError, ValueError, OSError) as exc:
        print(f"[help_coverage] 失败：{exc}")
        return 2


async def _run(args: argparse.Namespace) -> int:
    """执行一次台账生成。

    Args:
        args: 已解析参数。

    Returns:
        int: 退出码。

    Raises:
        HelpCoverageExemptionError: 豁免文件非法。
        HelpCoverageBaselineError: 基线台账不可解析。
        ValueError: 日期 / 配置非法。
        OSError: 文件读写失败。
    """
    as_of = _parse_as_of(cast("str", args.as_of))
    exemptions = load_help_coverage_exemptions(
        _exemption_paths(args.exemptions),
        strict_paths=bool(args.exemptions),
    )
    scope = HelpCoverageScope(
        product_keys=ConcurrentStableFrozenList(cast("list[str]", args.product_key)),
        module_keys=ConcurrentStableFrozenList(cast("list[str]", args.module_key)),
        kinds=ConcurrentStableFrozenList(cast("list[str]", args.kind)),
        include_covered=bool(args.include_covered) or bool(args.baseline),
    )
    url = resolve_url(cast("str", args.url), service=PLATFORM_SERVICE_KEY)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            snapshot = await load_help_coverage_snapshot(session)
    finally:
        await engine.dispose()
    ledger = build_help_coverage_ledger(snapshot, as_of=as_of, exemptions=exemptions, scope=scope)
    if args.baseline:
        if scope.product_keys or scope.module_keys or scope.kinds:
            raise ValueError("--baseline 不能与过滤参数同用（对比须为全量口径）")
        baseline = _load_json(cast("str", args.baseline))
        ledger = replace(ledger, baseline_diff=build_baseline_diff(ledger, baseline))
    rendered = _render(ledger, cast("str", args.format))
    print(rendered, end="")
    if args.output:
        target = Path(cast("str", args.output))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    strict = bool(args.strict) or _strict_env()
    if strict and ledger_is_blocked(ledger):
        return 1
    return 0


def _parse_as_of(raw: str) -> date:
    """解析判定日期。

    Args:
        raw: `YYYY-MM-DD` 或空串。

    Returns:
        date: 判定日期（空串取当天）。

    Raises:
        ValueError: 日期非法。
    """
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"--as-of 非法：{raw!r}（须为 YYYY-MM-DD）") from exc


def _exemption_paths(explicit: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """取豁免文件路径（显式参数优先，否则读配置）。

    Args:
        explicit: 命令行给出的路径。

    Returns:
        ConcurrentStableList[str]: 路径列表。
    """
    if explicit:
        return ConcurrentStableList(explicit)
    return ConcurrentStableList(get_settings().help_coverage.exemption_paths)


def _strict_env() -> bool:
    """读取强档环境变量。

    Returns:
        bool: 是否强档。
    """
    value = os.environ.get(_STRICT_ENV, "").strip().lower()
    return value in _TRUE_VALUES


def _load_json(raw_path: str) -> object:
    """读取基线 JSON。

    Args:
        raw_path: 文件路径。

    Returns:
        object: `json.loads` 结果。

    Raises:
        HelpCoverageBaselineError: 文件不可读或不是合法 JSON。
    """
    path = Path(raw_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HelpCoverageBaselineError(f"基线台账不可读或不是合法 JSON：{raw_path}（{exc}）") from exc


def _render(ledger: HelpCoverageLedger, fmt: str) -> str:
    """按格式渲染台账。

    Args:
        ledger: 台账。
        fmt: `text` / `json` / `markdown`。

    Returns:
        str: 渲染结果。
    """
    if fmt == "json":
        return render_json(ledger)
    if fmt == "markdown":
        return render_markdown(ledger)
    return render_text(ledger)
