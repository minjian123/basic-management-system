"""作业运行参数解析与容错回落（`[jobs]` → 生效值）。

配置由 `JobSettings` 承担类型 / 取值范围约束；本模块负责**关系型约束**与**运行期容错**：

- 租约必须大于心跳间隔的 3 倍（否则心跳前即过期，同一作业被重复抢占）；
- 非法 / 缺失值回落代码默认并记告警（作业执行不被配置面拖死）；
- 作业类型声明的 `timeout / max_attempts / backoff / concurrency` 由调用方显式覆盖。
"""

from __future__ import annotations

from typing import Any

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import JobSettings
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject

__all__ = ["DEFAULT_LIMITS", "JobLimits"]

_LOGGER = get_logger("bms")

DEFAULT_LIMITS: dict[str, Any] = {
    "poll_interval_seconds": 2.0,
    "claim_batch_size": 10,
    "global_concurrency": 4,
    "per_tenant_concurrency": 2,
    "lease_seconds": 300,
    "heartbeat_interval_seconds": 30,
    "progress_interval_seconds": 2.0,
    "max_attempts_default": 3,
    "backoff_seconds_default": 30,
    "backoff_max_seconds": 3600,
    "timeout_seconds_default": 1800,
    "result_max_chars": 65536,
    "error_max_chars": 512,
    "retention_days": 30,
    "shutdown_grace_seconds": 60,
    "tenant_cache_ttl_seconds": 60,
}
"""代码默认值（配置缺失 / 非法时的回落基线）。"""


class JobLimits(BaseFrameworkObject):
    """作业生效参数（构造即解析并回落；`warnings` 为本次回落明细）。"""

    def __init__(self, settings: JobSettings | None = None) -> None:
        """初始化并解析生效参数。

        Args:
            settings: 作业配置节；None 取代码默认。
        """
        base = settings if settings is not None else JobSettings()
        self.warnings: ConcurrentStableList[str] = ConcurrentStableList()
        self.poll_interval_seconds = self._positive_float(
            base.poll_interval_seconds, DEFAULT_LIMITS["poll_interval_seconds"], "poll_interval_seconds"
        )
        self.claim_batch_size = self._positive_int(
            base.claim_batch_size, DEFAULT_LIMITS["claim_batch_size"], "claim_batch_size"
        )
        self.global_concurrency = self._positive_int(
            base.global_concurrency, DEFAULT_LIMITS["global_concurrency"], "global_concurrency"
        )
        self.per_tenant_concurrency = self._positive_int(
            base.per_tenant_concurrency, DEFAULT_LIMITS["per_tenant_concurrency"], "per_tenant_concurrency"
        )
        self.heartbeat_interval_seconds = self._positive_int(
            base.heartbeat_interval_seconds,
            DEFAULT_LIMITS["heartbeat_interval_seconds"],
            "heartbeat_interval_seconds",
        )
        self.lease_seconds = self._resolve_lease(
            self._positive_int(base.lease_seconds, DEFAULT_LIMITS["lease_seconds"], "lease_seconds"),
            self.heartbeat_interval_seconds,
        )
        self.progress_interval_seconds = self._non_negative_float(
            base.progress_interval_seconds,
            DEFAULT_LIMITS["progress_interval_seconds"],
            "progress_interval_seconds",
        )
        self.max_attempts_default = self._positive_int(
            base.max_attempts_default, DEFAULT_LIMITS["max_attempts_default"], "max_attempts_default"
        )
        self.backoff_seconds_default = self._non_negative_int(
            base.backoff_seconds_default, DEFAULT_LIMITS["backoff_seconds_default"], "backoff_seconds_default"
        )
        self.backoff_max_seconds = self._non_negative_int(
            base.backoff_max_seconds, DEFAULT_LIMITS["backoff_max_seconds"], "backoff_max_seconds"
        )
        self.timeout_seconds_default = self._positive_int(
            base.timeout_seconds_default, DEFAULT_LIMITS["timeout_seconds_default"], "timeout_seconds_default"
        )
        self.result_max_chars = self._positive_int(
            base.result_max_chars, DEFAULT_LIMITS["result_max_chars"], "result_max_chars"
        )
        self.error_max_chars = self._positive_int(
            base.error_max_chars, DEFAULT_LIMITS["error_max_chars"], "error_max_chars"
        )
        self.retention_days = self._positive_int(
            base.retention_days, DEFAULT_LIMITS["retention_days"], "retention_days"
        )
        self.shutdown_grace_seconds = self._non_negative_int(
            base.shutdown_grace_seconds, DEFAULT_LIMITS["shutdown_grace_seconds"], "shutdown_grace_seconds"
        )
        self.tenant_cache_ttl_seconds = self._positive_int(
            base.tenant_cache_ttl_seconds, DEFAULT_LIMITS["tenant_cache_ttl_seconds"], "tenant_cache_ttl_seconds"
        )
        self.change_channel = base.change_channel or "bms:global:job:changed"
        self.enabled = bool(base.enabled)
        self.worker_id = base.worker_id or ""

    def _warn(self, key: str, value: object, default: object) -> None:
        """记录一次回落告警。

        Args:
            key: 配置键。
            value: 非法值。
            default: 回落值。
        """
        message = f"[jobs].{key} 取值非法（{value!r}），回落 {default!r}"
        self.warnings.add(message)
        _LOGGER.warning("作业参数回落默认值", key=key, value=repr(value), fallback=repr(default))

    def _positive_int(self, value: object, default: int, key: str) -> int:
        """取正整数（bool / 非 int / 非正回落默认）。

        Args:
            value: 原值。
            default: 默认值。
            key: 配置键。

        Returns:
            int: 生效值。
        """
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            self._warn(key, value, default)
            return default
        return value

    def _non_negative_int(self, value: object, default: int, key: str) -> int:
        """取非负整数（bool / 非 int / 负数回落默认）。

        Args:
            value: 原值。
            default: 默认值。
            key: 配置键。

        Returns:
            int: 生效值。
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            self._warn(key, value, default)
            return default
        return value

    def _positive_float(self, value: object, default: float, key: str) -> float:
        """取正浮点数。

        Args:
            value: 原值。
            default: 默认值。
            key: 配置键。

        Returns:
            float: 生效值。
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
            self._warn(key, value, default)
            return default
        return float(value)

    def _non_negative_float(self, value: object, default: float, key: str) -> float:
        """取非负浮点数。

        Args:
            value: 原值。
            default: 默认值。
            key: 配置键。

        Returns:
            float: 生效值。
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
            self._warn(key, value, default)
            return default
        return float(value)

    def _resolve_lease(self, lease_seconds: int, heartbeat_interval_seconds: int) -> int:
        """校验租约与心跳关系（租约须大于心跳 × 3）。

        Args:
            lease_seconds: 租约时长。
            heartbeat_interval_seconds: 心跳间隔。

        Returns:
            int: 生效租约；关系不满足时抬到「心跳 × 3 + 1」并告警。
        """
        minimum = heartbeat_interval_seconds * 3 + 1
        if lease_seconds < minimum:
            self._warn("lease_seconds", lease_seconds, minimum)
            return minimum
        return lease_seconds
