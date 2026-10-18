"""迁移链注册测试（Kiwi 1078 / 2307）：分链形态（服务 × 数据源）、元数据子集、URL 解析、空链与临时链脚本。"""

from pathlib import Path

import pytest

from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db import migration
from bms_core.db.migration import (
    BACKEND_ROOT,
    CONFIG_SECTION,
    DATASOURCES,
    DEFAULT_CHAIN_NAME,
    alembic_config,
    archive_chain,
    build_chain_name,
    chain_metadata,
    chain_names,
    chain_url,
    config_section,
    default_chain,
    has_revisions,
    head_revision,
    parse_chain_name,
    resolve_chain,
    resolve_chain_from_section,
    service_chains,
)


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
    assert "platform:platform" in names and "platform:tenant" in names and "file:tenant" in names
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
    assert {"sys_module", "sys_module_i18n", "sys_product", "sys_table_ownership"} <= platform
    assert {"sys_outbox", "sys_event_consumed", "sys_event_dead_letter"} <= platform
    assert "sys_tenant" not in platform  # 租户注册归 tenant 服务

    tenant_platform = resolve_chain("tenant:platform").tables
    assert "sys_tenant" in tenant_platform
    assert "sys_module" not in tenant_platform

    tenant_chain = resolve_chain("platform:tenant").tables
    assert "sys_dict_type" not in tenant_chain
    assert "sys_role" in tenant_chain
    assert "sys_outbox" in tenant_chain
    assert "sys_module" not in tenant_chain

    # 未定稿表（骨架表 / 演示表）与归档链
    assert "sys_task" not in tenant_chain
    assert "demo" not in tenant_chain
    assert resolve_chain("platform:archive").tables == frozenset()
    assert "sys_outbox" not in resolve_chain("org:archive").tables


@pytest.mark.kiwi_id(1078)
@pytest.mark.kiwi_id(2247)
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
    # `org` 的迁移链随组织主数据归 mdm 产品服务（2026-10-07，bms 11_01）：bms 侧已无该服务工程与链脚本，
    # 其链与表由 mdm 仓库维护；本用例只对 bms 内已建服务成立。
    # 角色域 5 表 + 用户 / 账号锁定两表归 platform 服务租户库
    # （02_03：与平台元数据同服务；02_05：用户（账号）归口 platform，消除跨服务引用）
    assert {
        "sys_role",
        "sys_user_role",
        "sys_role_permission",
        "sys_role_field",
        "sys_data_scope",
        "sys_user",
        "sys_account_lock",
    } <= set(chain_metadata(resolve_chain("platform:tenant")).tables)
    assert set(chain_metadata(resolve_chain("identity:tenant")).tables) == {
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
        "sys_session",
        "sys_identity_provider",
        "sys_client",
    }
    assert set(chain_metadata(resolve_chain("identity:platform")).tables) == {
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
        "sys_user_identity",
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
def test_backend_root_raises_when_no_alembic_ini(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """工程布局异常：向上无含 `alembic.ini` 的目录 → `ConfigError`（不静默回落）。"""
    from bms_core.db import migration

    monkeypatch.setattr(migration, "__file__", str(tmp_path / "ghost" / "migration.py"))

    with pytest.raises(ConfigError, match=r"alembic\.ini"):
        migration._find_backend_root()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(1078)
def test_build_chain_name_rejects_invalid_datasource() -> None:
    """链名构造：数据源段非法（非 platform / tenant / archive）即拒。"""
    with pytest.raises(ConfigError, match="数据源段非法"):
        build_chain_name("platform", "legacy")


@pytest.mark.kiwi_id(1078)
def test_build_chain_name_rejects_unknown_service() -> None:
    """链名构造：服务标识未登记即拒（不误跑未登记服务库）。"""
    with pytest.raises(ConfigError, match="服务标识未登记"):
        build_chain_name("ghost", "platform")


@pytest.mark.kiwi_id(1078)
def test_head_revision_of_empty_chain_is_none() -> None:
    """空链（无版本脚本）head 为 None：供「已是最新」幂等判定，不报错。"""
    assert has_revisions(resolve_chain("platform:archive")) is False
    assert head_revision(resolve_chain("platform:archive")) is None


@pytest.mark.kiwi_id(1078)
def test_alembic_config_rejects_empty_version_locations(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置段存在但 `version_locations` 为空 → `ConfigError`（缺段按未登记处理）。"""

    class _EmptyConfig:
        """Alembic 配置替身：`version_locations` 为空。"""

        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def get_main_option(self, name: str) -> str | None:
            """恒定返回空（模拟缺 `version_locations`）。"""
            del name
            return None

    from bms_core.db import migration

    monkeypatch.setattr(migration, "Config", _EmptyConfig)

    with pytest.raises(ConfigError, match="version_locations"):
        alembic_config(resolve_chain("platform:platform"))


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
@pytest.mark.kiwi_id(2307)
def test_head_revision_driven_by_temp_chain_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """临时链脚本自检：仓库脚本清空后，「有脚本链」分支（`has_revisions` / `head_revision`）由临时链驱动。"""
    versions = tmp_path / "versions"
    location = versions / "platform" / "platform"
    location.mkdir(parents=True)
    (location / "0001_demo.py").write_text(
        'revision: str = "0001_demo"\n'
        "down_revision: str | None = None\n"
        'branch_labels: tuple[str, ...] = ("platform:platform",)\n'
        "def upgrade() -> None:\n    pass\n"
        "def downgrade() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "alembic.ini").write_text(
        "[alembic:platform:platform]\n"
        "path_separator = os\n"
        f"script_location = {BACKEND_ROOT / 'alembic'}\n"
        f"version_locations = {location}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(migration, "VERSIONS_ROOT", versions)
    monkeypatch.setattr(migration, "BACKEND_ROOT", tmp_path)

    chain = resolve_chain("platform:platform")
    assert chain.version_location == location
    assert migration.has_revisions(chain) is True
    assert head_revision(chain) == "0001_demo"
