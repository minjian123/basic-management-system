"""字典配置（`[dict]` 节）与三节基线（Kiwi 2372）：缺省值 / 分层覆盖 / 字段别名 / 基线不缺节。"""

from pathlib import Path

import pytest

from bms_core.core import config
from bms_core.core.config import DictSettings, Settings, load_settings

_VALID_BASE = """
[app]
name = "BMS 基础管理系统"
env = "dev"

[server]
host = "0.0.0.0"
port = 8000

[log]
level = "INFO"

[database.platform]
url = "sqlite+aiosqlite:///./app.db"

[database.tenants]
url = "sqlite+aiosqlite:///./app.db"

[database.archive]
url = "sqlite+aiosqlite:///./app.db"
"""


def _use_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    """把配置目录指向临时目录并写入 config.toml。

    Args:
        monkeypatch: 夹具。
        tmp_path: 临时目录。
        body: `config.toml` 内容。
    """
    (tmp_path / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(config, "_config_dir", lambda: tmp_path)


@pytest.mark.kiwi_id(2372)
def test_dict_settings_defaults() -> None:
    """参数缺省值：TTL / 空结果 TTL / 锁 / L1 / 探针 / 失效开关。"""
    settings = DictSettings()
    assert settings.type_ttl_seconds == 300
    assert settings.empty_ttl_seconds == 30
    assert settings.lock_ttl_seconds == 5
    assert settings.lock_wait_seconds == 0.05
    assert settings.l1_max_items == 1024
    assert settings.probe_limit == 2001
    assert settings.invalidate_on_write is True


@pytest.mark.kiwi_id(2372)
def test_dict_section_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`[dict]` 节被读入 `Settings.dict_options`（TOML 键经别名映射）。"""
    body = (
        _VALID_BASE
        + """
[dict]
type_ttl_seconds = 7
empty_ttl_seconds = 2
lock_ttl_seconds = 3
lock_wait_seconds = 0.01
l1_max_items = 8
probe_limit = 9
invalidate_on_write = false
"""
    )
    _use_config_dir(monkeypatch, tmp_path, body)
    settings = load_settings()
    assert settings.dict_options.type_ttl_seconds == 7
    assert settings.dict_options.empty_ttl_seconds == 2
    assert settings.dict_options.lock_ttl_seconds == 3
    assert settings.dict_options.lock_wait_seconds == pytest.approx(0.01)
    assert settings.dict_options.l1_max_items == 8
    assert settings.dict_options.probe_limit == 9
    assert settings.dict_options.invalidate_on_write is False


@pytest.mark.kiwi_id(2372)
def test_dict_section_without_field_would_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`[dict]` 与字段必须同批落地：字段缺失时未知节被严格模式拒绝（`extra=forbid` 的语义锚点）。"""
    body = (
        _VALID_BASE
        + """
[dict_unknown]
type_ttl_seconds = 1
"""
    )
    _use_config_dir(monkeypatch, tmp_path, body)
    with pytest.raises(Exception, match=r"dict_unknown|Extra inputs"):
        load_settings()


@pytest.mark.kiwi_id(2372)
def test_dict_options_field_alias() -> None:
    """字段别名契约：TOML 节名 `dict` ↔ 字段 `dict_options`（字段名不得叫 `dict`，否则遮蔽 `BaseSettings.dict()`）。"""
    field = Settings.model_fields["dict_options"]
    assert field.validation_alias == "dict"


@pytest.mark.kiwi_id(2372)
def test_baseline_has_dict_sections() -> None:
    """基线 `config.toml` 必须声明三节（缺任一节 → test / prod 落到 null provider，字典恒空）。"""
    baseline = (Path(config._CONFIG_DIR) / "config.toml").read_text(encoding="utf-8")  # pyright: ignore[reportPrivateUsage]
    for section in ("[data_source]", "[dict_translator]", "[dict_cache_region]", "[dict]"):
        assert section in baseline, f"基线 config.toml 缺配置节 {section}"
