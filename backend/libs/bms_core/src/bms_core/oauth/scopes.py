"""开放接口 scope 登记：外部调用方授权面（OAuth2 scope）的**单一来源**与校验（R4.2）。

- `OpenScope`：单条 scope 登记记录（标识 / 说明 / 是否写接口 scope）。
- `PLATFORM_OPEN_SCOPES`：平台开放接口基础 scope（`open:read` / `open:write`）。
- `OIDC_SCOPES`：OIDC 标准 scope（`openid` / `profile` / `email`，复用 `oidc_provider` 常量）——
  BMS 兼作 IdP 的授权码客户端注册必备，故一并纳入登记集合。
- `product_scopes()`：产品域 scope（`{product_key}:read` / `{product_key}:write`）按产品档案清单
  **自动派生**（产品先注册后接入，无需另立 scope 登记）。
- `known_scopes()` / `validate_scopes()`：登记集合视图与校验（`sys_client` 注册 / 更新时调用）——
  **最小 scope 集合**＝登记集合，未登记 scope 一律拒（《项目规划说明》「开放接口管理」安全默认）。

口径分工：本模块管**授权面收敛**（第三方应用可访问范围）；内部权限码走 `BasePermissionChecker`
（`require_permission`），运行期判定走 `BaseScopeChecker`（先 scope 后权限码）。真实 `/api/open`
令牌签发与运行期 scope 判定归阶段十（开放接口管理）。
"""

from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseValueObject
from bms_core.oauth.oidc_provider import OIDC_DEFAULT_SCOPES
from bms_core.services.module_registry import PRODUCT_CATALOG, ProductRecord, product_catalog_view

__all__ = [
    "OIDC_SCOPES",
    "OPEN_SCOPES",
    "PLATFORM_OPEN_SCOPES",
    "SCOPE_ACTION_READ",
    "SCOPE_ACTION_WRITE",
    "SCOPE_SEPARATOR",
    "OpenScope",
    "known_scopes",
    "open_scopes",
    "product_scopes",
    "validate_scopes",
]

SCOPE_SEPARATOR = ":"
"""scope 的动作段分隔符（形如 `open:read` / `mdm:write`）。"""

SCOPE_ACTION_READ = "read"
"""只读动作段（按分配的 scope 放行）。"""

SCOPE_ACTION_WRITE = "write"
"""写入动作段（写接口 POST / PUT / DELETE 需**显式授予**）。"""


@dataclass(frozen=True)
class OpenScope(BaseValueObject):
    """开放接口 scope 登记记录。"""

    scope: str
    """scope 标识（形如 `open:read` / `mdm:write` / `openid`）。"""

    description: str = ""
    """说明（中文用途）。"""

    write: bool = False
    """是否写接口 scope（写接口需显式授予，未授予一律拒绝）。"""


PLATFORM_OPEN_SCOPES: ConcurrentStableList[OpenScope] = ConcurrentStableList(
    (
        OpenScope(scope=f"open{SCOPE_SEPARATOR}{SCOPE_ACTION_READ}", description="开放接口只读（按分配的 scope 放行）"),
        OpenScope(
            scope=f"open{SCOPE_SEPARATOR}{SCOPE_ACTION_WRITE}",
            description="开放接口写入（写接口需显式授予）",
            write=True,
        ),
    )
)
"""平台开放接口基础 scope（最小集合基线）。"""

OIDC_SCOPES: ConcurrentStableList[OpenScope] = ConcurrentStableList(
    OpenScope(scope=scope, description="OIDC 标准 scope（BMS 兼作 IdP 的授权码客户端必备）")
    for scope in OIDC_DEFAULT_SCOPES
)
"""OIDC 标准 scope（`openid` / `profile` / `email`）。"""


def product_scopes(product_key: str) -> ConcurrentStableList[OpenScope]:
    """取某产品的开放接口 scope（只读 + 写入两项）。

    Args:
        product_key: 产品标识（`sys_product.product_key`）。

    Returns:
        tuple[OpenScope, ...]: 该产品的 scope 登记记录（只读在前）。
    """
    return ConcurrentStableList(
        (
            OpenScope(
                scope=f"{product_key}{SCOPE_SEPARATOR}{SCOPE_ACTION_READ}",
                description=f"{product_key} 产品开放接口只读",
            ),
            OpenScope(
                scope=f"{product_key}{SCOPE_SEPARATOR}{SCOPE_ACTION_WRITE}",
                description=f"{product_key} 产品开放接口写入（写接口需显式授予）",
                write=True,
            ),
        )
    )


def _build_open_scopes(source: ConcurrentStableList[ProductRecord]) -> ConcurrentStableList[OpenScope]:
    """按产品档案清单拼装全量 scope 登记视图（平台基础 → OIDC → 产品，保持插入序）。

    Args:
        source: 产品档案清单（插入序）。

    Returns:
        tuple[OpenScope, ...]: 登记记录。
    """
    records: ConcurrentStableList[OpenScope] = ConcurrentStableList([*PLATFORM_OPEN_SCOPES, *OIDC_SCOPES])
    for record in source:
        records.update(product_scopes(record.product_key))
    return ConcurrentStableList(records)


OPEN_SCOPES: ConcurrentStableList[OpenScope] = _build_open_scopes(ConcurrentStableList(PRODUCT_CATALOG))
"""**静态基线** scope 登记视图（平台基础 + OIDC 标准 + 平台内建产品；`PRODUCT_CATALOG` 派生）。

产品仓清单在应用装配期注册（`register_product_records()`），本常量**不含**运行期产品；
运行期校验一律走 `open_scopes()` / `known_scopes()`（取合并视图），本常量只作静态基线与对照。"""


def open_scopes(products: ConcurrentStableList[ProductRecord] | None = None) -> ConcurrentStableList[OpenScope]:
    """全量 scope 登记视图（平台基础 + OIDC 标准 + 各产品域）。

    Args:
        products: 产品档案清单（插入序）；缺省取**运行期合并视图** `product_catalog_view()`
        （平台内建产品 + 产品仓装载后注册的产品，装载不改变本函数语义）。

    Returns:
        tuple[OpenScope, ...]: 登记记录（平台基础 → OIDC → 产品，保持插入序）。
    """
    source = ConcurrentStableList(product_catalog_view() if products is None else products)
    return _build_open_scopes(source)


def known_scopes(products: ConcurrentStableList[ProductRecord] | None = None) -> ConcurrentStableSet[str]:
    """登记 scope 集合（校验基准，插入序去重）。

    Args:
        products: 产品档案清单（插入序）；缺省取运行期合并视图 `product_catalog_view()`。

    Returns:
        ConcurrentStableSet[str]: 已登记 scope 标识集合。
    """
    return ConcurrentStableSet(record.scope for record in open_scopes(products))


def validate_scopes(
    scopes: ConcurrentStableList[str],
    products: ConcurrentStableList[ProductRecord] | None = None,
) -> ConcurrentStableList[str]:
    """校验 scope 集合是否全部在登记集合内（`sys_client` 注册 / 更新时调用）。

    Args:
        scopes: 待校验 scope 集合（插入序）。
        products: 产品档案清单（插入序）；缺省 `PRODUCT_CATALOG`。

    Returns:
        ConcurrentStableList[str]: 未登记 scope 明细；空列表表示通过。
    """
    known = known_scopes(products)
    return ConcurrentStableList(scope for scope in scopes if scope not in known)
