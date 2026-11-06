"""bms 服务目录 / 配置的来源实现（任务 04-6）：把「服务键 → 实例地址」解析成 `InstanceSnapshot`。

**为什么放 adapter 而不是 `instances.py`**：`instances.py` 是通用协议层，不认识 bms 的
`[service_client]` 配置；本模块只做「配置 → 快照」的翻译，依赖方向仍是 adapter → msgclient，没有反向边。

**首期实例是 msg 平台节点**：`instances.msg` / `endpoints.msg` / `base_url_template`（`{service}` 取
`msg`）三级取址。`service` 参数只用于映射表与日志；RPC 的 `/rpc/{service}/{method}` 仍发往 msg。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.service_endpoints import (
    normalize_service_endpoints,
    normalize_service_instances,
)
from bms_core.msgclient.constants import RPC_INSTANCE_SNAPSHOT_TTL_MS
from bms_core.msgclient.instances import (
    InstanceSnapshot,
    InstanceUnavailable,
)
from bms_core.msgclient.retry import Clock, SystemClock
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE, SERVICE_CLIENT_OPTION_BASE_URL

__all__ = [
    "MSG_ENDPOINT_KEY",
    "ServiceCatalogInstanceProvider",
    "msg_instance_addresses",
]

MSG_ENDPOINT_KEY = "msg"
"""消息平台实例在 `[service_client].instances` / `endpoints` 里的来源键（不是 bms 服务目录的服务键）。"""

_SCHEMES = ("http://", "https://")
"""允许的实例基址协议前缀（与 transport / service_endpoints 同口径）。"""


def _base_url_template(settings: Settings) -> str:
    """取基址模板（未配置回落 Compose DNS 缺省）。

    Args:
        settings: 应用配置。

    Returns:
        str: 基址模板（可能含 `{service}`）。
    """
    return str(settings.service_client.options.get(SERVICE_CLIENT_OPTION_BASE_URL) or DEFAULT_BASE_URL_TEMPLATE)


def _addresses_of(settings: Settings, source_key: str) -> ConcurrentStableFrozenList[str]:
    """按来源键解析实例地址（instances → endpoints → 模板）。

    Args:
        settings: 应用配置。
        source_key: 来源键（首期 `msg`；未来可对应多个池）。

    Returns:
        ConcurrentStableFrozenList[str]: 实例基址（无尾斜线、去重；至少一个）。

    Raises:
        ConfigError: 模板缺 `{service}` 占位，或派生地址不是 `http(s)`。
    """
    instances = normalize_service_instances(settings.service_client.instances).get(source_key)
    if instances:
        return instances
    endpoints = normalize_service_endpoints(settings.service_client.endpoints).get(source_key)
    if endpoints:
        return ConcurrentStableFrozenList([endpoints])
    template = _base_url_template(settings)
    if "{service}" not in template:
        raise ConfigError(
            f"消息平台实例地址不可用：请配置 [service_client].instances.{source_key} / "
            f"endpoints.{source_key}，或让 options.base_url_template 含 {{service}} 占位（{template!r}）"
        )
    base = template.replace("{service}", source_key).rstrip("/")
    if not base.startswith(_SCHEMES):
        raise ConfigError(f"消息平台实例地址非法：{base!r}（须为 http(s) 地址）")
    return ConcurrentStableFrozenList([base])


def msg_instance_addresses(settings: Settings) -> ConcurrentStableFrozenList[str]:
    """解析 msg 平台实例地址（服务目录 / 配置三级取址的唯一入口）。

    Args:
        settings: 应用配置。

    Returns:
        ConcurrentStableFrozenList[str]: 实例基址（至少一个）。

    Raises:
        ConfigError: 地址不可用 / 非法（装配期拒启）。
    """
    return _addresses_of(settings, MSG_ENDPOINT_KEY)


class ServiceCatalogInstanceProvider:
    """bms 配置来源：按来源键解析实例，TTL 内返回缓存快照。

    - 映射表：`mapping.get(service)` → `mapping.get("*")` → `default_source_key`；
    - 首期缺省 `{"*": "msg"}`，无需配置；
    - 快照地址变化时 `revision += 1`，选择器据此清理旧 origin 状态；
    - 配置在启动期加载，运行期不监听文件（变更需重启）；TTL 为未来 DNS / 远程目录预留。
    """

    def __init__(
        self,
        *,
        settings: Settings,
        mapping: ConcurrentStableDict[str, str] | None = None,
        default_source_key: str = MSG_ENDPOINT_KEY,
        clock: Clock | None = None,
        ttl_ms: int = RPC_INSTANCE_SNAPSHOT_TTL_MS,
    ) -> None:
        """初始化。

        Args:
            settings: 应用配置。
            mapping: 逻辑服务 → 来源键（None 取 `{"*": "msg"}`）。
            default_source_key: 映射表未命中时的缺省来源键。
            clock: 时钟（缺省 `SystemClock()`；用例注入 fake clock）。
            ttl_ms: 快照缓存时长（毫秒；0 表示每次重解析）。
        """
        self._settings = settings
        self._mapping = (
            ConcurrentStableDict(mapping) if mapping is not None else ConcurrentStableDict({"*": MSG_ENDPOINT_KEY})
        )
        self._default_source_key = default_source_key
        self._clock = clock if clock is not None else SystemClock()
        self._ttl_ms = ttl_ms
        self._cache: ConcurrentStableDict[str, InstanceSnapshot] = ConcurrentStableDict()
        self._revisions: ConcurrentStableDict[str, int] = ConcurrentStableDict()

    def resolve(self, service: str) -> InstanceSnapshot:
        """解析目标服务对应的实例快照（TTL 内直接返回缓存）。

        Args:
            service: 逻辑服务标识。

        Returns:
            InstanceSnapshot: 实例快照。

        Raises:
            InstanceUnavailable: 解析结果为空（配置错误通常已由 `ConfigError` 在装配期拦截）。
        """
        source_key = self._mapping.get(service) or self._mapping.get("*") or self._default_source_key
        now_ms = self._clock.now_ms()
        cached = self._cache.get(source_key)
        if cached is not None and now_ms - cached.fetched_at_ms < self._ttl_ms:
            return cached
        addresses = _addresses_of(self._settings, source_key)
        if not addresses:
            raise InstanceUnavailable(
                f"消息平台实例来源为空：{source_key}",
                pool_key=source_key,
                reason="empty_snapshot",
            )
        previous = self._cache.get(source_key)
        revision = self._revisions.get(source_key, 0)
        if previous is None or previous.addresses != addresses:
            revision += 1
        self._revisions[source_key] = revision
        snapshot = InstanceSnapshot(
            pool_key=source_key,
            addresses=addresses,
            revision=revision,
            fetched_at_ms=now_ms,
        )
        self._cache[source_key] = snapshot
        return snapshot
