"""ops.help_package 薄壳：运行镜像声明与入口转发。"""

from __future__ import annotations

import pytest

from ops import help_package

pytestmark = pytest.mark.kiwi_id(2522)


def test_shell_declares_platform_image_and_parser() -> None:
    """薄壳声明 platform 镜像，并转发命令行解析器。"""
    assert help_package.RUN_IMAGE == "platform"
    parser = help_package.build_parser()
    args = parser.parse_args(["load", "--package", "help/package.yaml", "--all-tenants"])
    assert args.all_tenants is True
    assert args.apply is False
