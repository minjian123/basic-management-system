"""服务包模型名前缀参数化测试（Kiwi 2254）：包名派生 / 配置前缀 / 严格入口 / 平台默认不变。"""

import pytest

from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.migration import (
    require_service_model_modules,
    service_model_modules,
    service_package,
)


def _settings_with_prefix(prefix: str) -> Settings:
    """基于全局配置构造覆盖 `[app].package_prefix` 的配置对象。

    Args:
        prefix: 目标包名前缀。

    Returns:
        Settings: 覆盖后的配置对象。
    """
    base = get_settings()
    return base.model_copy(update={"app": base.app.model_copy(update={"package_prefix": prefix})})


@pytest.mark.kiwi_id(2254)
def test_service_package_prefix_default_and_override() -> None:
    """包名前缀默认 `bms`；配置覆盖后按 `{prefix}_{service}` 派生（产品场景 `mdm_org`）。"""
    base = get_settings()
    assert base.app.package_prefix == "bms"
    assert service_package("platform") == "bms_platform"
    assert service_package("platform", settings=base) == "bms_platform"

    product = _settings_with_prefix("mdm")
    assert service_package("org", settings=product) == "mdm_org"


@pytest.mark.kiwi_id(2254)
def test_platform_prefix_keeps_model_resolution() -> None:
    """默认前缀下模型模块解析与改前一致（platform 服务包自声明模块清单可解析）。"""
    modules = service_model_modules("platform")
    assert modules
    assert all(name.startswith("bms_platform.") for name in modules)
    assert modules == service_model_modules("platform", settings=get_settings())


@pytest.mark.kiwi_id(2254)
def test_require_service_model_modules_fails_loudly() -> None:
    """严格入口：服务包不存在即 `ConfigError`（含包名与配置键）；宽松入口返回空元组。"""
    assert service_model_modules("zzz_ghost") == ()
    with pytest.raises(ConfigError) as excinfo:
        require_service_model_modules("zzz_ghost")
    message = str(excinfo.value)
    assert "bms_zzz_ghost.models" in message
    assert "package_prefix" in message


@pytest.mark.kiwi_id(2254)
def test_prefix_mismatch_reports_error() -> None:
    """前缀配错（平台服务包不存在于产品前缀下）即报错——免静默空清单导致不建表。"""
    product = _settings_with_prefix("mdm")
    assert service_model_modules("platform", settings=product) == ()
    with pytest.raises(ConfigError):
        require_service_model_modules("platform", settings=product)
