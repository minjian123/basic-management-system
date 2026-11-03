#!/usr/bin/env python3
"""覆盖率缺口报告（本仓唯一入口）：转发 engkit 门禁，并把「缺哪些行 / 哪些分支」落盘。

为什么必须走这里（《AI开发规范》「覆盖率要求」/《测试规范》§6）：

- **不要**用 `pytest --cov` 手工采集：门禁读的是 `[coverage].data_file`
  （由 engkit 采集插件按 pid 落盘并合并），手工数据不参与门禁，只会得出与门禁不一致的假缺口。
  该错误入口由 pytest 入口守卫（`bms_core.testing.coverage_guard`）直接 `exit(2)` 拦下。
- **缺行 / 缺分支**由 engkit 打印到 **stderr**；本脚本同时落盘 `.cache/coverage/gaps.txt`，
  排障一律看该文件，避免终端过滤把行号丢掉。
- **两环口径**：提交环判「改动行」（`--changed`），推送环 / CI 判「模块级 100%」（缺省）；
  提交环不要求未改动代码达标。

用法::

    # 模块级缺口（推送环口径）：只看本任务两个包
    python3 scripts/tools/preflight/coverage_report.py \
        --module bms_core.i18n --module bms_platform.domains.i18n

    # 改动行缺口（提交环口径）：清单经标准输入喂入
    git diff --cached --name-only | python3 scripts/tools/preflight/coverage_report.py --changed

退出码：0 达标 / 1 未达标 / 2 参数或环境错误。
"""

from __future__ import annotations

import contextlib
import io
import sys
import tomllib
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import forward  # noqa: E402

_GAPS_NAME = "gaps.txt"
"""缺口明细落点文件名（固定，排障只看它）。"""


def _repo_root() -> Path:
    """定位仓库根（本脚本位于 `<root>/scripts/tools/preflight/`）。

    Returns:
        Path: 仓库根。
    """
    return _SCRIPT_DIR.parents[2]


def _data_file(root: Path) -> Path:
    """从仓根 `engkit.toml` 读覆盖率数据基址（唯一事实源）。

    Args:
        root: 仓库根。

    Returns:
        Path: 数据文件绝对路径。

    Raises:
        ValueError: 配置缺 `[coverage].data_file`。
    """
    with (root / "engkit.toml").open("rb") as stream:
        config = tomllib.load(stream)
    relative = str((config.get("coverage") or {}).get("data_file") or "")
    if not relative:
        raise ValueError("[coverage].data_file 未登记")
    return (root / relative).resolve()


def _parse_args(argv: Any) -> Any:  # bare-collections:allow（命令行参数）
    """解析参数。

    Args:
        argv: 命令行参数（不含程序名）。

    Returns:
        Any: （是否改动行口径, 模块清单）。

    Raises:
        ValueError: 缺少 `--module`（模块级口径）或出现未知参数。
    """
    changed = False
    modules = []  # bare-collections:allow（命令行参数）
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--changed":
            changed = True
            index += 1
            continue
        if item == "--module":
            if index + 1 >= len(argv):
                raise ValueError("--module 缺少取值")
            modules.append(argv[index + 1])
            index += 2
            continue
        raise ValueError(f"未知参数：{item}（只接受 --changed / --module <点分模块>）")
    if not changed and not modules:
        raise ValueError("模块级口径必须至少给一个 --module（避免全仓扫描）")
    return changed, tuple(modules)


def main(
    argv: Any = None,
) -> int:  # bare-collections:allow（命令行参数）
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（与 engkit 门禁一致）。
    """
    try:
        changed, modules = _parse_args(sys.argv[1:] if argv is None else argv)
        root = _repo_root()
        data_file = _data_file(root)
    except (ValueError, OSError) as error:
        print(f"[coverage-report] 参数 / 配置错误：{error}", file=sys.stderr)
        return 2
    out_dir = data_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.json"
    if changed:
        args = [
            "coverage-changed",
            "--data-file",
            str(data_file),
            "--out",
            str(report),
            "--root",
            str(root),
        ]
    else:
        args = ["coverage", "--data-file", str(data_file), "--out", str(report)]
        for module in modules:
            args.extend(["--module", module])
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with (
        contextlib.redirect_stdout(captured_out),
        contextlib.redirect_stderr(captured_err),
    ):
        code = forward(args)
    text = captured_out.getvalue() + captured_err.getvalue()
    gaps_file = out_dir / _GAPS_NAME
    gaps_file.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    print(f"[coverage-report] 缺口明细已落盘：{gaps_file}（口径：{'改动行' if changed else '模块级 100%'}）")
    return code


if __name__ == "__main__":
    sys.exit(main())
