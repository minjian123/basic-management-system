"""服务端点覆盖登记：服务键 → 基址（跨能力域共享的寻址补充）。

口径（为什么需要这一层）：
- 容器部署下服务间寻址按 `[service_client].options.base_url_template` 派生（`http://{service}:8000`，
  Compose / K8s 的服务名即 DNS），**无需任何覆盖**；
- **本机裸跑**时各服务监听回环别名（`127.0.0.x`），`{service}` 名字仍要靠系统 hosts 解析——而
  加一条别名就要管理员权限（Windows 写 hosts 需提权）。端点覆盖把「名字 → 地址」这一层收到配置里，
  本机由开发脚本按 `[service_client].endpoints` 注入，不再改系统 hosts，跨平台一致；
- **单一来源**：服务间同步调用（`servicecall`）与能力寻址（`collaboration` 第二段拓扑解析）都只经
  `service_base_url()` 取基址，不允许两处各写一套推导；未覆盖的服务一律回落基址模板，
  行为与引入覆盖前完全一致（缺省空表）。

失败语义：覆盖表非法（服务键为空 / 基址不是 `http(s)://` 绝对地址）→ `ConfigError`（拒启级），
不静默回落模板——静默回落会把「配错了」伪装成「名字解析不通」，排障成本极高。
"""

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ConfigError

__all__ = [
    "ServiceEndpointSource",
    "ServiceInstanceSource",
    "normalize_service_endpoints",
    "normalize_service_instances",
    "register_service_endpoints",
    "reset_service_endpoints",
    "service_base_url",
]

_SCHEMES = ("http://", "https://")
"""允许的基址协议前缀（服务间调用只走 HTTP(S)）。"""

ServiceEndpointSource = ConcurrentStableDict[str, str] | ConcurrentStableFrozenDict[str, str]
"""端点覆盖来源形态（配置字段是可变的 `ConcurrentStableDict`，归一后转不可变冻结表）。"""

ServiceInstanceSource = (
    ConcurrentStableDict[str, ConcurrentStableList[str]]
    | ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[str]]
)
"""多实例地址来源形态（服务键 → 地址列表；配置字段是 `ConcurrentStableDict[str, ConcurrentStableList]`）。"""


def normalize_service_endpoints(
    endpoints: ServiceEndpointSource | None,
) -> ConcurrentStableFrozenDict[str, str]:
    """校验并归一服务端点覆盖（服务键 → 基址）。

    Args:
        endpoints: 原始覆盖表（`[service_client].endpoints`；None / 空表表示不覆盖）。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 归一后的覆盖表（服务键去首尾空白、基址去尾斜杠）。

    Raises:
        ConfigError: 服务键为空，或基址不是 `http(s)://` 绝对地址。
    """
    if not endpoints:
        return ConcurrentStableFrozenDict[str, str]()
    normalized: ConcurrentStableDict[str, str] = ConcurrentStableDict[str, str]()
    for raw_service, raw_base in endpoints.items():
        service = str(raw_service).strip()
        base = str(raw_base).strip().rstrip("/")
        if not service:
            raise ConfigError(f"服务端点覆盖的服务键不得为空：{raw_service!r}")
        if not base.startswith(_SCHEMES):
            raise ConfigError(f"服务端点覆盖须为 http(s) 绝对地址：{service} → {raw_base!r}")
        normalized[service] = base
    return ConcurrentStableFrozenDict[str, str](normalized)


def normalize_service_instances(
    instances: ServiceInstanceSource | None,
) -> ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[str]]:
    """校验并归一多实例地址（服务键 → 地址列表）。

    与 `normalize_service_endpoints` 同口径：服务键去首尾空白、地址去尾斜线并按插入序去重；**显式空
    列表视为配置错误**（表达「这个来源没有实例」应删掉该项，而不是写空数组让调用方猜是否回落）。

    Args:
        instances: 原始多实例表（`[service_client].instances`；None / 空表表示不配置）。

    Returns:
        ConcurrentStableFrozenDict[str, tuple[str, ...]]: 归一后的地址表。

    Raises:
        ConfigError: 服务键为空、地址列表为空，或地址不是 `http(s)://` 绝对地址。
    """
    if not instances:
        return ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[str]]()
    normalized: ConcurrentStableDict[str, ConcurrentStableFrozenList[str]] = ConcurrentStableDict()
    for raw_service, raw_addresses in instances.items():
        service = str(raw_service).strip()
        if not service:
            raise ConfigError(f"多实例配置的服务键不得为空：{raw_service!r}")
        addresses = ConcurrentStableFrozenList(
            dict.fromkeys(str(address).strip().rstrip("/") for address in raw_addresses)
        )
        if not addresses:
            raise ConfigError(f"多实例配置的地址列表不得为空：{service}")
        for base in addresses:
            if not base.startswith(_SCHEMES):
                raise ConfigError(f"多实例配置须为 http(s) 绝对地址：{service} → {base!r}")
        normalized[service] = addresses
    return ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[str]](normalized)


_service_endpoints: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict[str, str]()
"""已登记的服务端点覆盖（装配期按配置登记；空表 = 全部按基址模板派生）。"""


def register_service_endpoints(endpoints: ServiceEndpointSource | None) -> None:
    """登记服务端点覆盖（装配期调用；重复登记以后者为准）。

    Args:
        endpoints: 原始覆盖表（校验口径同 `normalize_service_endpoints`）。

    Raises:
        ConfigError: 覆盖表非法（服务键为空 / 基址非 `http(s)` 绝对地址）。
    """
    global _service_endpoints
    _service_endpoints = normalize_service_endpoints(endpoints)


def reset_service_endpoints() -> None:
    """复位服务端点覆盖（应用生命周期收尾与测试隔离用；生产路径不单独调用）。"""
    global _service_endpoints
    _service_endpoints = ConcurrentStableFrozenDict[str, str]()


def service_base_url(service: str, base_url_template: str) -> str:
    """取目标服务基址：覆盖优先，未覆盖按基址模板派生。

    Args:
        service: 目标服务标识。
        base_url_template: 基址模板（占位 `{service}`；缺省值由调用方声明，本模块不重复定义）。

    Returns:
        str: 目标服务基址（无尾斜杠）。
    """
    override = _service_endpoints.get(service)
    if override is not None:
        return override
    return base_url_template.format(service=service).rstrip("/")
