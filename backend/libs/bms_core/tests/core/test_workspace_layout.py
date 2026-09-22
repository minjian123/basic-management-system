"""工作区布局护栏：uv 工作区成员（共享基座库 / 平台服务）与工程骨架就位。"""

import importlib.util
from pathlib import Path

import pytest

import bms_core

_BACKEND = Path(__file__).resolve().parents[4]


@pytest.mark.kiwi_id(1204)
def test_workspace_members_importable() -> None:
    """共享基座库与平台服务包均可解析（工作区成员已装配）。"""
    assert bms_core.__version__
    assert importlib.util.find_spec("bms_platform") is not None


@pytest.mark.kiwi_id(1204)
def test_workspace_layout_present() -> None:
    """工作区骨架就位：libs/bms_core + services/platform + 服务脚手架。"""
    assert (_BACKEND / "libs" / "bms_core" / "src" / "bms_core" / "core").is_dir()
    assert (_BACKEND / "libs" / "bms_core" / "src" / "bms_core" / "api").is_dir()
    assert (_BACKEND / "services" / "platform" / "src" / "bms_platform" / "api").is_dir()
    assert (_BACKEND / "services" / "platform" / "src" / "bms_platform" / "main.py").is_file()
    assert (_BACKEND / "scripts" / "new_service.py").is_file()
