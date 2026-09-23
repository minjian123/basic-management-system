"""网关声明式配置命令行：由服务目录生成 / 校验 `deploy/gateway/apisix.yaml`。

用法::

    uv run python -m ops.gateway_config render          # 生成（覆盖写入配置）
    uv run python -m ops.gateway_config render --print  # 生成并打印
    uv run python -m ops.gateway_config check           # 零漂移校验（CI / 预检用）
    uv run python -m ops.gateway_config check --root .  # 指定仓库根

薄入口：真正的生成逻辑在 `bms_core/services/gateway_catalog.py`（可单测）。
为在无后端依赖的精简环境（CI `base-integrity` 的 python:3.14-slim）下也可运行，
本脚本仅依赖标准库 + `bms_core` 的 stdlib 导入链，并自行把共享库源码根加入 `sys.path`。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _BACKEND_ROOT / "libs" / "bms_core" / "src"
sys.path.insert(0, str(_SRC_ROOT))

from bms_core.services.gateway_catalog import (  # noqa: E402
    render_apisix_config,
    render_apisix_yaml,
    validate_service_discovery,
)

REPO_ROOT = _BACKEND_ROOT.parent
"""仓库根（`backend/` 的父目录）。"""

CONFIG_RELATIVE = Path("deploy/gateway/apisix.yaml")
"""生成件相对仓库根的路径。"""


def config_path(root: Path) -> Path:
    """生成件的绝对路径。

    Args:
        root: 仓库根。

    Returns:
        Path: `deploy/gateway/apisix.yaml` 路径。
    """
    return root / CONFIG_RELATIVE


def render(root: Path, *, to_stdout: bool = False) -> int:
    """生成并写入 `apisix.yaml`。

    Args:
        root: 仓库根。
        to_stdout: 是否同时打印生成内容。

    Returns:
        int: 退出码（0 成功）。
    """
    text = render_apisix_yaml()
    target = config_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if to_stdout:
        print(text, end="")
    else:
        print(f"[gateway_config] 已生成 {target}")
    return 0


def check(root: Path) -> int:
    """校验仓库内生成件与服务目录零漂移、且服务发现无硬编码 IP。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 一致；1 缺失 / 漂移 / 硬编码 IP）。
    """
    target = config_path(root)
    if not target.is_file():
        print(f"[gateway_config] 缺失生成件：{target}（运行 render 生成）", file=sys.stderr)
        return 1
    if target.read_text(encoding="utf-8") != render_apisix_yaml():
        print(
            f"[gateway_config] 网关配置与服务目录不一致：{target}\n"
            "  运行 `uv run python -m ops.gateway_config render` 重新生成"
            "（来源：服务目录 SERVICE_CATALOG）",
            file=sys.stderr,
        )
        return 1
    violations = validate_service_discovery(render_apisix_config())
    if violations:
        print(
            f"[gateway_config] 服务发现校验失败（禁硬编码 IP）：{target}",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    print(f"[gateway_config] 通过：{target} 与服务目录一致、服务发现无硬编码 IP")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="生成 / 校验网关声明式配置（服务目录为单一来源）")
    parser.add_argument("command", choices=("render", "check"), help="render 生成；check 零漂移校验")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="仓库根（缺省自动定位）")
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="render 时打印生成内容")
    args = parser.parse_args(argv)
    if args.command == "render":
        return render(args.root, to_stdout=args.to_stdout)
    return check(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
