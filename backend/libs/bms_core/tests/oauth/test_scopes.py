"""开放接口 scope 登记测试（Kiwi 2250）：平台基础 / OIDC 标准 / 产品域派生 / 校验 / 注入产品清单。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.oauth.oidc_provider import OIDC_DEFAULT_SCOPES
from bms_core.oauth.scopes import (
    OPEN_SCOPES,
    PLATFORM_OPEN_SCOPES,
    SCOPE_SEPARATOR,
    known_scopes,
    open_scopes,
    product_scopes,
    validate_scopes,
)
from bms_core.services.module_registry import PRODUCT_CATALOG, ProductRecord

pytestmark = pytest.mark.kiwi_id(2250)


def test_platform_open_scopes_registered() -> None:
    """平台基础 scope：`open:read` / `open:write`，写 scope 需显式授予（write 标记）。"""
    assert [record.scope for record in PLATFORM_OPEN_SCOPES] == ["open:read", "open:write"]
    assert {record.scope for record in PLATFORM_OPEN_SCOPES if record.write} == {"open:write"}
    assert SCOPE_SEPARATOR == ":"
    assert {record.scope for record in PLATFORM_OPEN_SCOPES if not record.write} == {"open:read"}


def test_oidc_scopes_included_in_registry() -> None:
    """OIDC 标准 scope（授权码客户端必备）纳入登记集合。"""
    registered = {record.scope for record in OPEN_SCOPES}
    assert set(OIDC_DEFAULT_SCOPES) <= registered


def test_product_scopes_derived_from_product_catalog() -> None:
    """产品域 scope 按产品档案清单派生（只读 + 写入），无需另行登记。"""
    assert [record.scope for record in product_scopes("mdm")] == ["mdm:read", "mdm:write"]
    assert {record.scope for record in open_scopes() if record.scope.startswith("mdm:")} == {"mdm:read", "mdm:write"}
    assert {record.scope for record in open_scopes()} == {record.scope for record in OPEN_SCOPES}
    assert all(record.product_key for record in PRODUCT_CATALOG)


def test_known_scopes_and_validation() -> None:
    """登记集合：平台基础 + OIDC + 产品域；未登记 scope 逐项检出。"""
    known = known_scopes()
    assert {"open:read", "open:write", "openid", "profile", "email"} <= known
    assert {"biz:read", "biz:write", "cw:write", "mdm:read"} <= known
    assert validate_scopes(ConcurrentStableList(["open:read", "mdm:write", "openid"])) == []
    assert validate_scopes(ConcurrentStableList(["open:read", "ghost:read", "mdm:admin"])) == [
        "ghost:read",
        "mdm:admin",
    ]


def test_validation_uses_injected_product_catalog() -> None:
    """产品清单可注入（产品服务装配场景）：登记集合随注入清单收窄。"""
    products = ConcurrentStableList([ProductRecord(product_key="mdm", name="主数据管理")])
    assert validate_scopes(ConcurrentStableList(["mdm:read"]), products) == []
    assert validate_scopes(ConcurrentStableList(["biz:read"]), products) == ["biz:read"]
    assert validate_scopes(ConcurrentStableList(), products) == []
