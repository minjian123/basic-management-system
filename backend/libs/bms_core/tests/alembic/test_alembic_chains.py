"""迁移链注册测试（Kiwi 1078）：分链形态（服务 × 数据源）、元数据子集、URL 解析、链完整性与空链。"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.migration import (
    BACKEND_ROOT,
    CONFIG_SECTION,
    DATASOURCES,
    DEFAULT_CHAIN_NAME,
    MigrationChain,
    alembic_config,
    archive_chain,
    build_chain_name,
    chain_metadata,
    chain_names,
    chain_url,
    config_section,
    default_chain,
    has_revisions,
    parse_chain_name,
    resolve_chain,
    resolve_chain_from_section,
    service_chains,
)


def _config(chain: MigrationChain) -> Config:
    """取该链的 Alembic 配置（配置段名由链名派生）。

    Args:
        chain: 链定义。

    Returns:
        Config: Alembic 配置。
    """
    return Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=config_section(chain))


@pytest.mark.kiwi_id(1078)
def test_chain_name_parsing() -> None:
    """链名派生与反解：`{service}:{datasource}`；形态非法 / 数据源非法快速失败。"""
    assert build_chain_name("platform", "tenant") == "platform:tenant"
    assert parse_chain_name("tenant:platform") == ("tenant", "platform")
    assert default_chain().name == DEFAULT_CHAIN_NAME
    assert archive_chain().name == "platform:archive"
    with pytest.raises(ConfigError):
        parse_chain_name("platform")
    with pytest.raises(ConfigError):
        parse_chain_name("platform:legacy")
    with pytest.raises(ConfigError):
        resolve_chain("legacy:platform")
    with pytest.raises(ConfigError):
        build_chain_name("", "platform")


@pytest.mark.kiwi_id(1078)
def test_chain_registry_shape() -> None:
    """链注册表：服务 × 数据源组合、版本目录两级、分支标签 = 链名。"""
    names = chain_names()
    assert "platform:platform" in names and "platform:tenant" in names and "org:tenant" in names
    assert len(names) == len(set(names))
    assert [chain.datasource for chain in service_chains("platform")] == list(DATASOURCES)

    platform = resolve_chain("platform:platform")
    assert platform.service == "platform"
    assert platform.datasource == "platform"
    assert platform.branch == "platform:platform"
    assert platform.version_location == BACKEND_ROOT / "alembic" / "versions" / "platform" / "platform"
    assert resolve_chain("platform:tenant").version_location == (
        BACKEND_ROOT / "alembic" / "versions" / "platform" / "tenant"
    )


@pytest.mark.kiwi_id(1078)
def test_chain_tables_derived_from_ownership() -> None:
    """表集由归属登记派生：平台链取平台层表 + 基础设施表；归档链为空；`planned` 表不进链。"""
    platform = resolve_chain("platform:platform").tables
    assert {"sys_module", "sys_module_i18n", "sys_table_ownership"} <= platform
    assert {"sys_outbox", "sys_event_consumed", "sys_event_dead_letter"} <= platform
    assert "sys_tenant" not in platform  # 租户注册归 tenant 服务

    tenant_platform = resolve_chain("tenant:platform").tables
    assert "sys_tenant" in tenant_platform
    assert "sys_module" not in tenant_platform

    tenant_chain = resolve_chain("platform:tenant").tables
    assert "sys_dict_type" in tenant_chain
    assert "sys_outbox" in tenant_chain
    assert "sys_module" not in tenant_chain

    # 未定稿表（骨架表 / 演示表）与归档链
    assert "sys_task" not in tenant_chain
    assert "demo" not in tenant_chain
    assert resolve_chain("platform:archive").tables == frozenset()
    assert "sys_outbox" not in resolve_chain("org:archive").tables


@pytest.mark.kiwi_id(1078)
def test_chain_metadata_is_subset() -> None:
    """链元数据子集 = 派生表集 ∩ 已有模型（骨架表既不入链、也不被自动建表创建）。"""
    platform = chain_metadata(resolve_chain("platform:platform"))
    assert set(platform.tables) == resolve_chain("platform:platform").tables
    tenant = chain_metadata(resolve_chain("platform:tenant"))
    assert set(tenant.tables) == resolve_chain("platform:tenant").tables
    assert "sys_task" not in tenant.tables
    assert "sys_notification" not in tenant.tables
    assert chain_metadata(resolve_chain("platform:archive")).tables == {}
    # 服务链：共享基础设施表（发件箱三表）+ 本服务自有模型表
    assert set(chain_metadata(resolve_chain("org:tenant")).tables) == {
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
        "sys_user",
    }
    assert set(chain_metadata(resolve_chain("identity:tenant")).tables) == {
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
        "sys_session",
    }


@pytest.mark.kiwi_id(1078)
def test_resolve_chain_unknown_target() -> None:
    """未知链名快速失败（不误跑库）。"""
    with pytest.raises(ConfigError):
        resolve_chain("legacy")


@pytest.mark.kiwi_id(1078)
def test_config_section_mapping() -> None:
    """配置段映射：缺省链用 `[alembic]`，其余用 `[alembic:{service}:{datasource}]`；反向解析一致。"""
    assert config_section(default_chain()) == CONFIG_SECTION
    assert config_section(resolve_chain("platform:platform")) == "alembic:platform:platform"
    assert resolve_chain_from_section(CONFIG_SECTION).name == DEFAULT_CHAIN_NAME
    assert resolve_chain_from_section("alembic:platform:platform").name == "platform:platform"
    with pytest.raises(ConfigError):
        resolve_chain_from_section("alembic:legacy")
    # 缺省链误用全限定段名 → 明确提示（不静默取错库）
    with pytest.raises(ConfigError):
        resolve_chain_from_section(f"alembic:{DEFAULT_CHAIN_NAME}")


@pytest.mark.kiwi_id(1078)
def test_alembic_config_requires_registered_section() -> None:
    """配置段缺 `version_locations` 快速失败（新增服务首次迁移须补段）。"""
    assert alembic_config(resolve_chain("platform:platform")).get_main_option("version_locations")
    with pytest.raises(ConfigError):
        alembic_config(resolve_chain("file:tenant"))


@pytest.mark.kiwi_id(1078)
def test_chain_url_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """连接串解析：平台链按服务取平台服务库；租户链回落目标 `url`；归档取 `url`；db_key 优先。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "sqlite+aiosqlite:///" + str(tmp_path / "platform.db"))
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", "sqlite+aiosqlite:///" + str(tmp_path / "archive.db"))
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", "sqlite+aiosqlite:///" + str(tmp_path / "fallback.db"))
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/tenant_{{tenant}}.db")
    get_settings.cache_clear()
    settings = get_settings()

    # platform 目标未启用模板 → 回落目标 url（基础默认不变）
    assert chain_url(resolve_chain("platform:platform"), settings).endswith("platform.db")
    assert chain_url(resolve_chain("platform:archive"), settings).endswith("archive.db")
    assert chain_url(resolve_chain("platform:tenant"), settings).endswith("fallback.db")
    assert chain_url(resolve_chain("platform:tenant"), settings, db_key="tenant_demo").endswith("tenant_demo.db")


@pytest.mark.kiwi_id(1078)
def test_chain_revisions_integrity() -> None:
    """链完整性：有脚本链单 head、分支标签与链名一致、链内 revision 唯一（跨链允许同名）。"""
    platform_head = ScriptDirectory.from_config(_config(resolve_chain("platform:platform"))).get_current_head()
    assert platform_head == "0005_sys_table_ownership"
    tenant_service_head = ScriptDirectory.from_config(_config(default_chain())).get_current_head()
    assert tenant_service_head == "0003_sys_outbox_event_version"

    for name in (
        "platform:platform",
        "platform:tenant",
        "tenant:platform",
        "tenant:tenant",
        "identity:tenant",
        "org:tenant",
    ):
        heads = ScriptDirectory.from_config(_config(resolve_chain(name))).get_heads()
        assert len(heads) == 1, f"{name} 应恰好一个 head，实际 {heads}"
        head = ScriptDirectory.from_config(_config(resolve_chain(name))).get_revision(heads[0])
        assert head is not None
        assert tuple(head.branch_labels or ()) == (name,)
        assert has_revisions(resolve_chain(name)) is True
