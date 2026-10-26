"""Kiwi 2244：`sqlite_dir` 基址解析与引擎 / 迁移接入。"""

from pathlib import Path

import pytest

from bms_core.core import config as config_module
from bms_core.core.config import Settings, resolve_sqlite_dir
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import archive_series, default_series, series_url

_REL = "sqlite+aiosqlite:///./bms_x.db"


@pytest.mark.kiwi_id(2244)
def test_resolve_sqlite_dir_relative(tmp_path: Path) -> None:
    """相对路径按基址解析到目标目录（并自动建目录）。"""
    target = tmp_path / "sub"
    resolved = resolve_sqlite_dir(_REL, str(target))
    # 路径分隔符归一再断言（Windows 为反斜杠、Linux 为正斜杠）
    assert resolved.replace("\\", "/").endswith("/bms_x.db")
    assert str(target) in resolved
    assert target.is_dir()


@pytest.mark.kiwi_id(2244)
def test_resolve_sqlite_dir_passthrough(tmp_path: Path) -> None:
    """绝对路径 / 非 SQLite / 内存库 / 空基址一律原样返回。"""
    base = str(tmp_path)
    assert resolve_sqlite_dir(_REL, "") == _REL
    absolute = f"sqlite+aiosqlite:///{tmp_path}/abs.db"
    assert resolve_sqlite_dir(absolute, base) == absolute
    assert resolve_sqlite_dir("mysql+aiomysql://u@host:3306/db", base) == "mysql+aiomysql://u@host:3306/db"
    assert resolve_sqlite_dir("sqlite+aiosqlite:///:memory:", base) == "sqlite+aiosqlite:///:memory:"


@pytest.mark.kiwi_id(2244)
def test_engine_resolve_url_applies_sqlite_dir(tmp_path: Path) -> None:
    """引擎解析连接串时经基址归一（平台目标）。"""
    settings = Settings()
    settings.database.sqlite_dir = str(tmp_path)
    settings.database.platform.url = _REL
    settings.database.platform.url_template = ""
    resolved = EngineFactory(settings).resolve_url()
    assert str(tmp_path / "bms_x.db") in resolved


@pytest.mark.kiwi_id(2359)
def test_resolve_sqlite_dir_relative_base_uses_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """基址本身为相对路径时以配置目录为基准（`_CONFIG_DIR`），解析到绝对路径并建目录。"""
    monkeypatch.setattr(config_module, "_CONFIG_DIR", tmp_path)

    resolved = resolve_sqlite_dir(_REL, "relative-base")

    assert str(tmp_path / "relative-base" / "bms_x.db") in resolved
    assert (tmp_path / "relative-base").is_dir()


@pytest.mark.kiwi_id(2244)
def test_series_url_applies_sqlite_dir(tmp_path: Path) -> None:
    """迁移取连接串时经基址归一（租户 / 归档回落分支）。"""
    settings = Settings()
    settings.database.sqlite_dir = str(tmp_path)
    settings.database.tenants.url = _REL
    settings.database.tenants.url_template = ""
    tenant_url = series_url(default_series(), settings)
    assert str(tmp_path / "bms_x.db") in tenant_url

    settings.database.archive.url = "sqlite+aiosqlite:///./bms_archive.db"
    archive_url = series_url(archive_series(), settings)
    assert str(tmp_path / "bms_archive.db") in archive_url
