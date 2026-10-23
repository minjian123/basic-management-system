"""服务包模型名前缀参数化测试（Kiwi 2254）：包名派生 / 配置前缀 / 严格入口 / 平台默认不变。"""

from types import SimpleNamespace

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
    """包名前缀默认 `bms`；配置覆盖后按 `{prefix}_{service}` 派生；前缀等于服务标识时去重。"""
    base = get_settings()
    assert base.app.package_prefix == "bms"
    assert service_package("platform") == "bms_platform"
    assert service_package("platform", settings=base) == "bms_platform"

    product = _settings_with_prefix("mdm")
    assert service_package("org", settings=product) == "mdm_org"
    # 前缀与产品名相同：去重为服务标识本身（与库名 `prefix == service` 去重同规则）
    assert service_package("mdm", settings=product) == "mdm"


@pytest.mark.kiwi_id(2254)
def test_platform_prefix_keeps_model_resolution() -> None:
    """默认前缀下服务包解析与改前一致（共享模型下沉后 platform 无私有模型）。"""
    modules = service_model_modules("platform")
    # 14_01：platform 的模型整包下沉到 bms_core.models.platform，服务侧 models 包已删除
    assert modules == ()
    assert require_service_model_modules("platform") == ()
    assert service_model_modules("platform", settings=get_settings()) == ()


@pytest.mark.kiwi_id(2254)
def test_declared_service_models_resolve() -> None:
    """服务包自声明清单仍可解析（txn 保留私有模型：非空且以本服务包名开头）。"""
    modules = require_service_model_modules("txn")

    assert modules
    assert all(name.startswith("bms_txn.") for name in modules)
    assert modules == service_model_modules("txn")


@pytest.mark.kiwi_id(2254)
def test_require_service_model_modules_fails_loudly() -> None:
    """严格入口：服务包不存在即 `ConfigError`（含包名与配置键）；宽松入口返回空元组。"""
    assert service_model_modules("zzz_ghost") == ()
    with pytest.raises(ConfigError) as excinfo:
        require_service_model_modules("zzz_ghost")
    message = str(excinfo.value)
    # 14_01：缺失判定在服务包一级（`bms_zzz_ghost`），不再带 `.models` 后缀
    assert "bms_zzz_ghost" in message
    assert "package_prefix" in message


@pytest.mark.kiwi_id(2254)
def test_prefix_mismatch_reports_error() -> None:
    """前缀配错（平台服务包不存在于产品前缀下）即报错——免静默空清单导致不建表。"""
    product = _settings_with_prefix("mdm")
    assert service_model_modules("platform", settings=product) == ()
    with pytest.raises(ConfigError):
        require_service_model_modules("platform", settings=product)


@pytest.mark.kiwi_id(2254)
def test_existing_package_without_declaration_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务包存在但未声明 `MODEL_MODULES` → `ConfigError`（不静默返回空清单）。"""
    from bms_core.db import migration

    def _package_exists(name: str) -> bool:
        del name
        return True

    def _import_module(name: str) -> SimpleNamespace:
        del name
        return SimpleNamespace()

    monkeypatch.setattr(migration, "_package_exists", _package_exists)
    monkeypatch.setattr(migration.importlib, "import_module", _import_module)

    with pytest.raises(ConfigError, match="MODEL_MODULES"):
        service_model_modules("platform")


@pytest.mark.kiwi_id(2254)
def test_require_service_model_modules_returns_existing_package() -> None:
    """严格入口：服务包存在时返回其私有模型清单（与宽松入口一致）。"""
    modules = require_service_model_modules("txn")

    assert modules
    assert modules == service_model_modules("txn")
