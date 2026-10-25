"""业务域迁移清单注册（Kiwi 1076 / 1077 / 2352）：清单名 / 版本记录表 / 目录 / 域表集 / 单元聚合 / 旧形态拒绝。

口径见 07C `03_02` 详细设计 §3.1~§3.5 与架构 39「数据与库」节：库随部署单元、表归属与清单按业务域，
**拆 / 合不切清单**（任一拓扑下库结构 = 所含域表集并集，表名不变）。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.exceptions import ConfigError
from bms_core.db.migration import (
    ARCHIVE_SERIES_NAME,
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    DEFAULT_SERIES_NAME,
    config_section,
    default_series,
    domain_series,
    known_domains,
    parse_series_name,
    resolve_series,
    series_names,
    series_tables,
    unit_domains,
    unit_series,
    version_table_name,
)
from bms_core.services.table_registry import infrastructure_tables, unit_tables


@pytest.mark.kiwi_id(1076)
def test_series_name_and_version_table() -> None:
    """清单名 `{domain}:{datasource}` 与版本记录表 `alembic_version_{domain}`（每清单独立一张）。"""
    assert parse_series_name("user:tenant") == ("user", DATASOURCE_TENANT)
    assert version_table_name("user") == "alembic_version_user"
    assert version_table_name("platform_registry") == "alembic_version_platform_registry"
    series = resolve_series("user:tenant")
    assert series.name == "user:tenant"
    assert series.domain == "user"
    assert series.datasource == DATASOURCE_TENANT
    assert series.branch == series.name
    assert series.version_table == "alembic_version_user"
    assert series.version_location.as_posix().endswith("versions/user/tenant")
    assert default_series().name == DEFAULT_SERIES_NAME == "platform_registry:tenant"


@pytest.mark.kiwi_id(1076)
def test_series_name_rejects_legacy_service_form() -> None:
    """旧 `{service}:{datasource}` 形态**不兼容**：命中服务标识即报错并提示改用域清单名。"""
    with pytest.raises(ConfigError, match="服务标识"):
        parse_series_name("platform:tenant")
    with pytest.raises(ConfigError, match="数据源段"):
        parse_series_name("user:legacy")
    with pytest.raises(ConfigError):
        parse_series_name("user")
    with pytest.raises(ConfigError, match="未登记"):
        parse_series_name("no_such_domain:tenant")


@pytest.mark.kiwi_id(1076)
def test_series_registry_shape() -> None:
    """清单全集 = 已登记域 × 平台 / 租户 + 归档单清单；域清单按域取（三种数据源）。"""
    names = series_names()
    assert DEFAULT_SERIES_NAME in names
    assert ARCHIVE_SERIES_NAME in names
    assert f"{ARCHIVE_SERIES_NAME.split(':')[0]}:tenant" not in names
    assert [item.datasource for item in domain_series("user")] == [
        DATASOURCE_PLATFORM,
        DATASOURCE_TENANT,
        DATASOURCE_ARCHIVE,
    ]
    assert default_series().tables == resolve_series(DEFAULT_SERIES_NAME).tables


@pytest.mark.kiwi_id(1077)
def test_config_section_mapping() -> None:
    """配置段名：缺省清单用 `[alembic]`，其余 `[alembic:{清单名}]`；缺省清单误用全限定段名即拒。"""
    from bms_core.db.migration import resolve_series_from_section

    assert config_section(default_series()) == "alembic"
    user = resolve_series("user:tenant")
    assert config_section(user) == "alembic:user:tenant"
    assert resolve_series_from_section("alembic").name == DEFAULT_SERIES_NAME
    assert resolve_series_from_section("alembic:user:tenant").name == "user:tenant"
    with pytest.raises(ConfigError):
        resolve_series_from_section(f"alembic:{DEFAULT_SERIES_NAME}")
    with pytest.raises(ConfigError):
        resolve_series_from_section("engine")


@pytest.mark.kiwi_id(2352)
def test_series_tables_by_domain_only() -> None:
    """域清单表集**只含本域表**；基础设施表不进任何域清单（由单元级建表集追加）。"""
    infra = infrastructure_tables()
    assert infra, "基础设施表应已登记（发件箱三表）"
    user_tables = series_tables("user", DATASOURCE_TENANT)
    assert user_tables, "user 域应已登记租户库表"
    assert not (user_tables & infra), "基础设施表不得进域清单"
    assert user_tables == resolve_series("user:tenant").tables
    assert not series_tables("no_such_domain", DATASOURCE_TENANT)


@pytest.mark.kiwi_id(2352)
def test_unit_aggregation_is_topology_invariant() -> None:
    """合并 / 拆分两拓扑下单元建表集一致：并集相同、表名不变（拆合不切清单）。"""
    domains = unit_domains("platform")
    assert len(domains) > 1, "platform 单元应承载多个业务域（合并拓扑）"
    for datasource in (DATASOURCE_PLATFORM, DATASOURCE_TENANT):
        merged = unit_tables(domains, datasource)
        split: ConcurrentStableSet[str] = ConcurrentStableSet()
        for domain in domains:
            split |= ConcurrentStableSet(unit_tables([domain], datasource))
        assert ConcurrentStableSet(merged) == split, f"{datasource}：合并与拆分的表集并集不一致"
        # 表名不随拓扑变化：域表集只由域派生，与单元组成无关
        for domain in domains:
            assert set(series_tables(domain, datasource)) <= ConcurrentStableSet(merged)


@pytest.mark.kiwi_id(2352)
def test_unit_series_order_and_scope() -> None:
    """单元内多清单按域名稳定排序（可复现），且每清单只属于一个域。"""
    series = unit_series("platform", DATASOURCE_TENANT)
    domains = [item.domain for item in series]
    assert domains == sorted(domains)
    assert len(domains) == len(set(domains))
    assert all(item.datasource == DATASOURCE_TENANT for item in series)
    assert "user" in domains and "platform_registry" in domains


@pytest.mark.kiwi_id(2352)
def test_known_domains_from_layout() -> None:
    """域清单唯一来源是域布局声明（不另起第二套登记）：已知域至少覆盖平台侧核心域。"""
    domains = set(known_domains())
    assert {"user", "role", "tenant", "platform_registry", "menu_form", "permission_meta"} <= domains
    # 域标识一律 snake_case（无连字符）
    assert all("-" not in domain for domain in domains)
