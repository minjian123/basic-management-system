"""工程根定位用例（`bms_core/core/paths.py`）：环境变量优先、向上搜根、fail-closed。

覆盖三条语义：
1. `BMS_BACKEND_ROOT` 命中 → 直接采用（不做链接解析）；
2. 变量缺省 → 自锚点向上搜首个含标记文件的目录；
3. 变量取值无效 / 向上未搜到 → `ConfigError`（不静默回落）。

关键回归：搜索**不穿透符号链接**。`.venv` 外置为符号链接时，包体真实路径在依赖仓、
`Path.resolve()` 会解析过去导致搜不到工程根；`absolute()` 保留链接层级方能命中。

**临时布局落仓外**（04-6-2 `--basetemp` 收口）：`--basetemp` 已钉到 `backend/.cache/pytest`，
`tmp_path` 因此**位于仓库内**，向上搜索必然命中真实的 `backend/alembic.ini`——「无标记」与
「软链外层无工程根」两类断言必须在**仓库之外**的目录里构造（系统临时目录）。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from bms_core.core.exceptions import ConfigError
from bms_core.core.paths import BACKEND_ROOT_ENV, resolve_backend_root


@pytest.fixture(autouse=True)
def _clear_root_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """隔离宿主环境：避免开发机已导出的 `BMS_BACKEND_ROOT` 影响用例。"""
    monkeypatch.delenv(BACKEND_ROOT_ENV, raising=False)


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    """搭一个最小布局：`<tmp>/backend/<锚点>`，返回 (工程根, 锚点文件)。"""
    backend = tmp_path / "backend"
    anchor = backend / "pkg" / "anchor.py"
    anchor.parent.mkdir(parents=True)
    anchor.write_text("", encoding="utf-8")
    return backend, anchor


@contextmanager
def _outside_repo() -> Generator[Path]:
    """仓库之外的临时根目录（用完即删）。

    Yields:
        Path: 系统临时目录下的独立根（祖先链里没有工程根标记）。
    """
    root = Path(tempfile.mkdtemp(prefix="bms-paths-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_resolve_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """环境变量命中：直接返回其取值（即使锚点位于别处）。"""
    backend, anchor = _layout(tmp_path)
    (backend / "alembic.ini").write_text("", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "alembic.ini").write_text("", encoding="utf-8")
    monkeypatch.setenv(BACKEND_ROOT_ENV, str(other))
    assert resolve_backend_root("alembic.ini", anchor=anchor) == other


def test_resolve_env_override_expands_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """环境变量取值支持 `~` 展开（`Path.expanduser`）：家目录下的工程根可写成 `~/...`。"""
    home_backend = tmp_path / "home" / "backend"
    home_backend.mkdir(parents=True)
    (home_backend / "alembic.ini").write_text("", encoding="utf-8")
    anchor = tmp_path / "repo" / "pkg" / "anchor.py"
    anchor.parent.mkdir(parents=True)
    anchor.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # Windows 的 expanduser 以 USERPROFILE 为准
    monkeypatch.setenv(BACKEND_ROOT_ENV, "~/backend")
    assert resolve_backend_root("alembic.ini", anchor=anchor) == home_backend


def test_resolve_env_override_without_marker_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """环境变量 fail-closed：目录存在但缺标记文件 → 报错并指出变量名与目录。"""
    _, anchor = _layout(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv(BACKEND_ROOT_ENV, str(empty))
    with pytest.raises(ConfigError, match=BACKEND_ROOT_ENV):
        resolve_backend_root("alembic.ini", anchor=anchor)


def test_resolve_searches_upwards_without_env(tmp_path: Path) -> None:
    """变量缺省：自锚点向上取首个含标记文件的祖先目录。"""
    backend, anchor = _layout(tmp_path)
    (backend / "alembic.ini").write_text("", encoding="utf-8")
    assert resolve_backend_root("alembic.ini", anchor=anchor) == backend


def test_resolve_raises_when_marker_absent() -> None:
    """向上无标记文件 → `ConfigError`（不静默回落最顶层祖先）。"""
    with _outside_repo() as root:
        _, anchor = _layout(root)
        with pytest.raises(ConfigError, match="未找到后端工程根"):
            resolve_backend_root("alembic.ini", anchor=anchor)


def test_resolve_does_not_follow_symlink() -> None:
    """回归：搜索不穿透符号链接——`.venv` 外置为符号链接时仍能命中仓库内工程根。

    构造：`<tmp>/repo/backend/`（含标记）内 `.venv` 软链到 `<tmp>/ext`，包体实体在
    `<tmp>/ext/site-packages/pkg/anchor.py`，经**仓内软链路径**取锚点。真实外置态下
    `Path.resolve()` 会解析到 `<tmp>/ext` 而搜不到 `backend/`；`absolute()` 保留链接层级。
    """
    with _outside_repo() as root:
        backend = root / "repo" / "backend"
        backend.mkdir(parents=True)
        (backend / "alembic.ini").write_text("", encoding="utf-8")
        ext = root / "ext" / "site-packages" / "pkg"
        ext.mkdir(parents=True)
        (ext / "anchor.py").write_text("", encoding="utf-8")
        (backend / ".venv").symlink_to(root / "ext")

        # 经仓内软链路径取锚点：字面路径仍位于 backend/ 之下
        anchor = backend / ".venv" / "site-packages" / "pkg" / "anchor.py"
        assert anchor.is_file()
        # 对照：解析真实路径会丢失工程根（回落到临时根的祖先链）
        assert not any((p / "alembic.ini").is_file() for p in anchor.resolve().parents)
        assert resolve_backend_root("alembic.ini", anchor=anchor) == backend


def test_resolve_defaults_anchor_to_module_file() -> None:
    """锚点缺省为本模块文件：真实仓库布局下应命中 bms 后端工程根。"""
    root = resolve_backend_root("alembic.ini")
    assert (root / "alembic.ini").is_file()
    assert (root / "libs" / "bms_core").is_dir()
