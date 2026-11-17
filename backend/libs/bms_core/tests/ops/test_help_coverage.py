"""`ops.help_coverage` 薄壳（08_04；Kiwi 2523）。

锁死：运行镜像为任意服务（只依赖基座）、参数解析与基座同源、未显式导入的属性可转发（测试 monkeypatch 兼容）。
"""

from __future__ import annotations

import pytest

import ops.help_coverage as shell
from bms_core.help import coverage_cli
from bms_core.tenant.seed.menu import PERMISSION_SEEDS


@pytest.mark.kiwi_id(2523)
def test_permission_seed_includes_help_manage() -> None:
    """覆盖率接口权限码 `help:manage` 已进入平台种子（12_01 维护面共用）。"""
    assert any(business == "help" and action == "manage" for business, action, _zh, _en in PERMISSION_SEEDS)


@pytest.mark.kiwi_id(2523)
def test_shell_declares_any_image_and_parser() -> None:
    """薄壳声明 `RUN_IMAGE="*"` 且参数解析与基座一致。"""
    assert shell.RUN_IMAGE == "*"
    assert shell.build_parser is coverage_cli.build_parser
    assert shell.main is coverage_cli.main
    args = shell.build_parser().parse_args(["--format", "json"])
    assert args.format == "json"


@pytest.mark.kiwi_id(2523)
def test_shell_forwards_unknown_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """未显式导入的属性转发到基座命令行实现。"""
    monkeypatch.setattr(coverage_cli, "_STRICT_ENV", "BMS_PROBE_STRICT")
    assert shell._STRICT_ENV == "BMS_PROBE_STRICT"  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(AttributeError):
        _ = shell.not_exists
