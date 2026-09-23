"""库键与库名单一来源测试（Kiwi 2177）：双形态派生与反解 / 库名 / 归属校验 / 运维豁免。

覆盖 `bms_core/db/keys.py`：

- 键形态：相对键（`platform` / `tenant_{code}`）与全限定键（`platform_{service}` / `tenant_{service}_{code}`）
  以及归档单键 `archive`；非法形态（空 / 未知前缀 / 缺段 / 伪键 `tenants`）快速失败；
- 反解歧义消解：`tenant_` 后首段命中已知服务标识即视为全限定键，否则整体为租户编码；
- 库名派生：`bms_{service}` / `bms_{service}_{code}` / `bms_archive`，相对键按当前服务补全；
- 归属校验：相对键恒属当前服务；全限定键越界抛 `DataOwnershipError`（10008）；
  未登记服务标识抛 `ConfigError`；运维豁免（`allow_cross_service`）放行跨服务键。
"""

from pathlib import Path

import pytest

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError, DataOwnershipError
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import (
    ARCHIVE_DATABASE,
    ARCHIVE_DB_KEY,
    PLATFORM_DB_KEY,
    PLATFORM_DB_KEY_PREFIX,
    TENANT_DB_KEY_PREFIX,
    build_platform_db_key,
    build_tenant_db_key,
    database_name,
    parse_db_key,
    platform_database_name,
    resolve_db_key,
    tenant_database_name,
)


def test_key_constants() -> None:
    """键形态常量：前缀与库名与架构「三库命名与建库标准」一致。"""
    assert PLATFORM_DB_KEY == "platform"
    assert PLATFORM_DB_KEY_PREFIX == "platform_"
    assert TENANT_DB_KEY_PREFIX == "tenant_"
    assert ARCHIVE_DB_KEY == "archive"
    assert ARCHIVE_DATABASE == "bms_archive"


def test_platform_key_build_and_parse() -> None:
    """平台键：相对键与全限定键形态、往返一致、库类别与元数据正确。"""
    assert build_platform_db_key() == "platform"
    assert build_platform_db_key("org") == "platform_org"

    relative = parse_db_key("platform")
    assert (relative.kind, relative.service, relative.is_qualified) == ("platform", None, False)

    qualified = parse_db_key("platform_tenant")
    assert (qualified.kind, qualified.service, qualified.tenant_code) == ("platform", "tenant", None)
    assert qualified.is_qualified is True
    assert qualified.raw == "platform_tenant"


def test_tenant_key_build_and_parse() -> None:
    """租户键：相对键 / 全限定键派生与反解；首段非服务标识时整体视为编码。"""
    assert build_tenant_db_key("demo") == "tenant_demo"
    assert build_tenant_db_key("demo", service="org") == "tenant_org_demo"

    relative = parse_db_key("tenant_demo")
    assert (relative.kind, relative.service, relative.tenant_code) == ("tenant", None, "demo")

    qualified = parse_db_key("tenant_org_acme")
    assert (qualified.kind, qualified.service, qualified.tenant_code) == ("tenant", "org", "acme")

    # 首段非已知服务标识 → 整体为编码（含下划线的租户编码不受影响）
    assert parse_db_key("tenant_acme_corp").tenant_code == "acme_corp"
    assert parse_db_key("tenant_acme_corp").service is None


def test_archive_key_parse() -> None:
    """归档键：单键，不服务化、无租户编码。"""
    key = parse_db_key(ARCHIVE_DB_KEY)
    assert (key.kind, key.service, key.tenant_code, key.is_qualified) == ("archive", None, None, False)


@pytest.mark.parametrize(
    "db_key",
    ["", "  ", "tenants", "foo", "platform_", "tenant_", "archive_extra"],
)
def test_parse_rejects_illegal_keys(db_key: str) -> None:
    """非法键快速失败：空 / 未知前缀 / 缺服务段或编码（含历史伪键 `tenants`）。"""
    with pytest.raises(ConfigError):
        parse_db_key(db_key)


def test_build_tenant_db_key_requires_code() -> None:
    """租户编码为空即拒。"""
    with pytest.raises(ConfigError):
        build_tenant_db_key("")


def test_database_name_derivation() -> None:
    """库名单一来源：平台 `bms_{service}`、租户 `bms_{service}_{code}`、归档 `bms_archive`。"""
    assert platform_database_name("org") == "bms_org"
    assert tenant_database_name("org", "acme") == "bms_org_acme"

    assert database_name(parse_db_key("platform"), service="org") == "bms_org"
    assert database_name(parse_db_key("platform_tenant"), service="org") == "bms_tenant"
    assert database_name(parse_db_key("tenant_demo"), service="org") == "bms_org_demo"
    assert database_name(parse_db_key("tenant_org_acme"), service="platform") == "bms_org_acme"
    assert database_name(parse_db_key("archive"), service="") == "bms_archive"


def test_database_name_requires_service_for_relative_key() -> None:
    """相对键缺服务标识时库名不可派生（提示改用全限定键）。"""
    with pytest.raises(ConfigError):
        database_name(parse_db_key("platform"), service="")


@pytest.mark.parametrize("service", ["", "bad-name!", "bad name"])
def test_database_name_rejects_illegal_identifier(service: str) -> None:
    """库名形态非法（空服务标识 / 含非法字符）即拒。"""
    with pytest.raises(ConfigError):
        platform_database_name(service)


def test_tenant_database_name_requires_code() -> None:
    """租户库名派生要求编码非空。"""
    with pytest.raises(ConfigError):
        tenant_database_name("org", "")


def test_resolve_relative_key_belongs_to_current_service() -> None:
    """相对键恒属当前服务：不触发越界。"""
    assert resolve_db_key("platform", service="org").kind == "platform"
    key = resolve_db_key("tenant_demo", service="org")
    assert (key.tenant_code, key.service) == ("demo", None)


def test_resolve_full_qualified_key_same_service() -> None:
    """全限定键服务段等于当前服务：放行。"""
    assert resolve_db_key("platform_org", service="org").service == "org"
    assert resolve_db_key("tenant_org_demo", service="org").tenant_code == "demo"


@pytest.mark.parametrize("db_key", ["platform_platform", "tenant_platform_demo"])
def test_resolve_rejects_cross_service_key(db_key: str) -> None:
    """越界键（服务段非当前服务）抛数据所有权错误 10008。"""
    with pytest.raises(DataOwnershipError) as excinfo:
        resolve_db_key(db_key, service="org")
    assert excinfo.value.code == 10008


def test_resolve_ops_exemption_allows_cross_service() -> None:
    """运维豁免：显式开启后跨服务键放行（仅运维通道使用）。"""
    assert resolve_db_key("platform_platform", service="org", allow_cross_service=True).service == "platform"
    assert resolve_db_key("tenant_org_acme", service="platform", allow_cross_service=True).tenant_code == "acme"


def test_resolve_rejects_unknown_platform_service() -> None:
    """平台全限定键服务标识未登记即拒（即使开启运维豁免）。"""
    with pytest.raises(ConfigError):
        resolve_db_key("platform_ghost", service="org", allow_cross_service=True)


def test_resolve_treats_unknown_head_as_relative_tenant_code() -> None:
    """`tenant_` 后首段非已知服务标识：整体视为租户编码（相对键），不按全限定键解。"""
    key = resolve_db_key("tenant_ghost_demo", service="org", allow_cross_service=True)
    assert (key.service, key.tenant_code) == (None, "ghost_demo")


def _factory(
    tmp_path: Path,
    service: str,
    *,
    allow_cross_service: bool = False,
    templates: bool = True,
) -> EngineFactory:
    """构造临时平台 / 租户目标的引擎工厂。

    Args:
        tmp_path: 临时目录。
        service: 运行服务标识（相对键补全用）。
        allow_cross_service: 是否开启运维豁免。
        templates: 是否启用每服务每租户连接串模板（False = 回落单库）。

    Returns:
        EngineFactory: 引擎工厂。
    """
    settings = Settings()
    settings.app.service = service
    settings.database.platform.url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    settings.database.tenants.url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_fallback.db'}"
    if templates:
        settings.database.platform.url_template = f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db"
        settings.database.tenants.url_template = f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    return EngineFactory(settings, allow_cross_service=allow_cross_service)


def test_engine_factory_resolves_service_db_names(tmp_path: Path) -> None:
    """平台 / 租户目标均按 `{database}` 解析为服务库名（相对键补当前服务）。"""
    factory = _factory(tmp_path, "org")
    assert factory.resolve_url("platform").endswith("/bms_org.db")
    assert factory.resolve_url("tenant_demo").endswith("/bms_org_demo.db")
    assert factory.resolved_url("tenant_demo").endswith("/bms_org_demo.db")


def test_engine_factory_ops_channel_cross_service(tmp_path: Path) -> None:
    """运维通道：跨服务全限定键解析到目标服务库；未豁免时越界（10008）。"""
    factory = _factory(tmp_path, "org", allow_cross_service=True)
    assert factory.resolve_url("platform_platform").endswith("/bms_platform.db")
    assert factory.resolve_url("platform_tenant").endswith("/bms_tenant.db")
    assert factory.resolve_url("tenant_org_acme").endswith("/bms_org_acme.db")
    assert factory.resolve_url("tenant_tenant_demo").endswith("/bms_tenant_demo.db")

    guarded = _factory(tmp_path, "org")
    with pytest.raises(DataOwnershipError):
        guarded.resolve_url("tenant_platform_demo")
    with pytest.raises(DataOwnershipError):
        guarded.create("platform_tenant")


def test_engine_factory_template_needs_service(tmp_path: Path) -> None:
    """相对键 + 模板含 `{service}` / `{database}` 而服务标识缺失：快速失败并提示。"""
    factory = _factory(tmp_path, "")
    with pytest.raises(ConfigError, match="需要服务标识"):
        factory.resolve_url("platform")


def test_engine_factory_empty_template_falls_back_to_url(tmp_path: Path) -> None:
    """空模板回落目标 `url` 单库（基础默认不变），无需服务标识。"""
    factory = _factory(tmp_path, "", templates=False)
    assert factory.resolve_url("platform").endswith("/platform.db")
    assert factory.resolve_url("tenant_demo").endswith("/tenant_fallback.db")
    assert factory.resolve_url("archive").endswith("/bms_archive.db")
