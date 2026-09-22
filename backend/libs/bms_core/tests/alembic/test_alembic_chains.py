"""迁移链注册测试（Kiwi 1078）：链定义、元数据子集、URL 解析、链完整性与空链。"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.migration import (
    ARCHIVE_TABLES,
    BACKEND_ROOT,
    CONFIG_SECTION,
    DEFAULT_MIGRATION_TARGET,
    PLATFORM_TABLES,
    TENANT_TABLES,
    chain_metadata,
    chain_names,
    chain_url,
    config_section,
    has_revisions,
    resolve_chain,
    resolve_chain_from_section,
)


def _config(chain_name: str) -> Config:
    """取该链的 Alembic 配置（配置段 = 链名）。

    Args:
        chain_name: 链名。

    Returns:
        Config: Alembic 配置。
    """
    return Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=config_section(resolve_chain(chain_name)))


@pytest.mark.kiwi_id(1078)
def test_chain_registry_shape() -> None:
    """链注册表：三条链（platform / tenant / archive）与各自表集。"""
    assert chain_names() == ["platform", "tenant", "archive"]
    assert resolve_chain("platform").tables == PLATFORM_TABLES
    assert resolve_chain("tenant").tables == TENANT_TABLES
    assert resolve_chain("archive").tables == ARCHIVE_TABLES
    assert resolve_chain("platform").branch == "platform"
    assert resolve_chain("platform").version_location == BACKEND_ROOT / "alembic" / "versions" / "platform"


@pytest.mark.kiwi_id(1078)
def test_chain_metadata_is_subset() -> None:
    """链元数据子集只含链表（骨架表既不入链、也不被自动建表创建）。"""
    platform = chain_metadata(resolve_chain("platform"))
    assert set(platform.tables) == PLATFORM_TABLES
    tenant = chain_metadata(resolve_chain("tenant"))
    assert set(tenant.tables) == TENANT_TABLES
    assert "sys_task" not in tenant.tables
    assert "sys_notification" not in tenant.tables
    assert chain_metadata(resolve_chain("archive")).tables == {}


@pytest.mark.kiwi_id(1078)
def test_resolve_chain_unknown_target() -> None:
    """未知链名快速失败（不误跑库）。"""
    with pytest.raises(ConfigError):
        resolve_chain("legacy")


@pytest.mark.kiwi_id(1078)
def test_config_section_mapping() -> None:
    """配置段映射：缺省链用 `[alembic]`，其余用 `[alembic:<链名>]`；反向解析一致。"""
    assert config_section(resolve_chain(DEFAULT_MIGRATION_TARGET)) == CONFIG_SECTION
    assert config_section(resolve_chain("platform")) == "alembic:platform"
    assert resolve_chain_from_section(CONFIG_SECTION).name == DEFAULT_MIGRATION_TARGET
    assert resolve_chain_from_section("alembic:archive").name == "archive"
    with pytest.raises(ConfigError):
        resolve_chain_from_section("alembic:legacy")


@pytest.mark.kiwi_id(1078)
def test_chain_url_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """连接串解析：平台 / 归档取目标 `url`；租户链经 `db_key` + `url_template` 模板。"""
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    archive_url = f"sqlite+aiosqlite:///{tmp_path / 'archive.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", platform_url)
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", archive_url)
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/tenant_{{tenant}}.db")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{tmp_path / 'fallback.db'}")
    get_settings.cache_clear()
    settings = get_settings()

    assert chain_url(resolve_chain("platform"), settings) == platform_url
    assert chain_url(resolve_chain("archive"), settings) == archive_url
    assert chain_url(resolve_chain("tenant"), settings).endswith("fallback.db")
    assert chain_url(resolve_chain("tenant"), settings, db_key="tenant_demo") == (
        f"sqlite+aiosqlite:///{tmp_path}/tenant_demo.db"
    )


@pytest.mark.kiwi_id(1078)
def test_chain_revisions_integrity() -> None:
    """链完整性：每链单 head、分支标签与链名一致、revision 全局唯一；归档链为空链。"""
    revisions: list[str] = []
    for name in chain_names():
        script = ScriptDirectory.from_config(_config(name))
        heads = script.get_heads()
        if name == "archive":
            assert heads == [] and has_revisions(resolve_chain(name)) is False
            continue
        assert len(heads) == 1, f"{name} 应恰好一个 head，实际 {heads}"
        head = script.get_revision(heads[0])
        assert head is not None
        assert tuple(head.branch_labels or ()) == (name,)
        revisions.append(head.revision)
    assert len(revisions) == len(set(revisions)), "revision 跨链重名"

    platform_head = ScriptDirectory.from_config(_config("platform")).get_current_head()
    assert platform_head == "0001_sys_tenant_module"
    assert ScriptDirectory.from_config(_config("tenant")).get_current_head() == "0001_dict_query_scheme"
