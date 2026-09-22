"""工作区布局护栏：uv 工作区成员（共享基座库 / 各服务）与工程骨架就位。"""

import importlib.util
from pathlib import Path

import pytest

import bms_core

_BACKEND = Path(__file__).resolve().parents[4]
_SERVICES = ("platform", "identity", "tenant", "org", "file", "notification", "search", "ai", "report")


@pytest.mark.kiwi_id(1204)
def test_workspace_members_importable() -> None:
    """共享基座库与各服务包均可解析（工作区成员已装配）。"""
    assert bms_core.__version__
    for name in _SERVICES:
        assert importlib.util.find_spec(f"bms_{name}") is not None, name


@pytest.mark.kiwi_id(1204)
def test_workspace_layout_present() -> None:
    """工作区骨架就位：libs/bms_core + 9 服务工程（入口 / 路由）+ 服务脚手架。"""
    assert (_BACKEND / "libs" / "bms_core" / "src" / "bms_core" / "core").is_dir()
    assert (_BACKEND / "libs" / "bms_core" / "src" / "bms_core" / "api").is_dir()
    assert (_BACKEND / "libs" / "bms_core" / "src" / "bms_core" / "application.py").is_file()
    for name in _SERVICES:
        package = _BACKEND / "services" / name / "src" / f"bms_{name}"
        assert (package / "api").is_dir(), name
        assert (package / "main.py").is_file(), name
        assert (package / "__main__.py").is_file(), name
        assert (_BACKEND / "services" / name / "pyproject.toml").is_file(), name
    assert (_BACKEND / "scripts" / "new_service.py").is_file()
