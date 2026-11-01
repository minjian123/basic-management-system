"""WorkerId 注册的 Redis 租约实现 `RedisWorkerIdRegistry`（插件名 `redis`，03_06 / 需求 03-7）。

口径：

- **占号**：配置值优先（`SET NX EX` 占得到就用），占不到走随机起点 + Lua 内循环探测（回绕、上限
  `probe_limit`），一次往返；池 `1 ~ 2^40-1`（0 保留为「未注册」哨兵）。
- **心跳**：后台线程按 `heartbeat_seconds` 续期（`GET == token` → `EXPIRE`）；连续失败达
  `lease_ttl_seconds / 3` → 重新占号并 `reconfigure`（新号必未用过，ID 仍唯一）。
- **释放**：Lua 校验令牌后 `DEL`（防迟到释放误删他人租约）；崩溃由 TTL 回收。
- **降级**：Redis 不可用 / 探测用尽 → 回落 `[app].worker_id` 并告警；生产仍未取到号由
  `assert_ready()` 拒启（`ConfigError`）。
- 心跳承载用**同步**客户端（`[redis]` 进程共享实例）：启动期与低频心跳足够，且同一实现
  同时服务异步应用与同步 ops 脚本，避免事件循环绑定。
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError

from bms_core.core.config import Settings
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.logging import get_logger
from bms_core.redis.base import shared_sync_client
from bms_core.workerid.base import (
    SOURCE_CONFIG,
    SOURCE_FALLBACK,
    SOURCE_NONE,
    SOURCE_REGISTRY,
    WORKER_ID_POOL_MAX,
    WORKER_ID_POOL_MIN,
    BaseWorkerIdRegistry,
    build_holder_token,
    build_worker_id_prefix,
)

__all__ = ["ACQUIRE_SCRIPT", "PROBE_EXHAUSTED", "RELEASE_SCRIPT", "RENEW_SCRIPT", "RedisWorkerIdRegistry"]

PROBE_EXHAUSTED = -1
"""探测结果：上限内未找到空闲号。"""

ACQUIRE_SCRIPT = """
local start = tonumber(ARGV[2])
local low, high = tonumber(ARGV[3]), tonumber(ARGV[4])
local token, ttl, limit = ARGV[5], tonumber(ARGV[6]), tonumber(ARGV[7])
local span = high - low + 1
for i = 0, limit - 1 do
  local id = low + ((start - low + i) % span)
  if redis.call('SET', ARGV[1] .. id, token, 'NX', 'EX', ttl) then return id end
end
return -1
"""
"""占号脚本：随机起点 + 线性探测 + 回绕（单次往返；返回号或 -1）。"""

RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return 0
"""
"""续期脚本：令牌一致才续期（返回 1 成功 / 0 租约已失）。"""

RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
"""释放脚本：令牌一致才删除（返回 1 删除 / 0 未持有）。"""

# `except` 语法只接受异常类元组，无法用 ConcurrentStableFrozenList 承载 ⇒ 豁免集合声明护栏
# bare-collections:allow
_REDIS_ERRORS: tuple[type[BaseException], ...] = (RedisError, OSError, RedisUnavailableError)
"""视为「Redis 不可用」的异常集合（降级判据）。"""

_LOGGER = get_logger("bms")


class RedisWorkerIdRegistry(BaseWorkerIdRegistry):
    """Redis 租约实现（插件名 `redis`）。"""

    plugin_name = "redis"

    def __init__(
        self,
        settings: Settings,
        *,
        client: Redis | None = None,
        random_start: Callable[[], int] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[app].worker_id` / `[worker_id]` / `[redis]`）。
            client: 同步客户端（测试注入 fakeredis；缺省取进程共享客户端）。
            random_start: 探测起点生成器（测试注入固定值）。
            clock: 单调时钟（测试注入）。
        """
        super().__init__(settings)
        self._client_override = client
        self._random_start = random_start if random_start is not None else self._default_start
        self._clock = clock if clock is not None else time.monotonic
        self._token: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed_since: float | None = None

    def _default_start(self) -> int:
        """缺省探测起点（池内均匀随机）。

        Returns:
            int: 起点号。
        """
        return WORKER_ID_POOL_MIN + secrets.randbelow(WORKER_ID_POOL_MAX - WORKER_ID_POOL_MIN + 1)

    def _client(self) -> Redis:
        """取同步客户端（显式注入优先）。

        Returns:
            Redis: 同步客户端。

        Raises:
            RedisUnavailableError: 未装配共享客户端（fail-closed）。
        """
        return self._client_override if self._client_override is not None else shared_sync_client()

    def acquire(self) -> None:
        """取号：配置值优先占号 → 探测 → 失败降级（幂等）。"""
        if self._source != SOURCE_NONE:
            return
        section = self._settings.worker_id
        prefix = build_worker_id_prefix(self._settings)
        self._token = build_holder_token(self._settings)
        configured = self._settings.app.worker_id
        try:
            if configured:
                key = f"{prefix}{configured}"
                if self._set_nx(key, section.lease_ttl_seconds):
                    self._activate(configured, SOURCE_CONFIG, key)
                    return
                _LOGGER.warning("worker_id_configured_taken", configured=configured)
            worker_id = self._probe(prefix, section.lease_ttl_seconds, section.probe_limit)
        except _REDIS_ERRORS as exc:
            self._degrade(f"redis_unavailable:{type(exc).__name__}")
            return
        if worker_id == PROBE_EXHAUSTED:
            self._degrade("exhausted")
            return
        self._activate(worker_id, SOURCE_REGISTRY, f"{prefix}{worker_id}")

    def release(self) -> None:
        """释放租约（先停心跳再 CAS 删除；幂等）。"""
        self._stop_heartbeat()
        key, token = self._key_name, self._token
        self._key_name = None
        self._token = None
        self._source = SOURCE_NONE
        self._failed_since = None
        if key is None or token is None:
            return
        try:
            self._client().eval(RELEASE_SCRIPT, 1, key, token)
        except _REDIS_ERRORS as exc:
            _LOGGER.warning("worker_id_release_failed", key=key, error=repr(exc))

    def heartbeat_once(self) -> None:
        """心跳单轮（供后台线程调用；测试直接驱动以覆盖分支）。"""
        key, token = self._key_name, self._token
        if key is None or token is None:
            return
        try:
            renewed = self._client().eval(RENEW_SCRIPT, 1, key, token, self._settings.worker_id.lease_ttl_seconds)
        except _REDIS_ERRORS as exc:
            self._on_heartbeat_failure(f"redis_unavailable:{type(exc).__name__}")
            return
        if renewed:
            self._failed_since = None
            return
        self._on_heartbeat_failure("lease_lost")

    def _set_nx(self, key: str, ttl: int) -> bool:
        """占用指定键（配置值优先占号）。

        Args:
            key: 注册键。
            ttl: 租约 TTL（秒）。

        Returns:
            bool: 占用成功为 True。
        """
        result = self._client().set(key, self._token or "", nx=True, ex=ttl)
        return bool(result)

    def _probe(self, prefix: str, ttl: int, limit: int) -> int:
        """探测空闲号（Lua 一次往返）。

        Args:
            prefix: 键前缀（未含号）。
            ttl: 租约 TTL（秒）。
            limit: 探测上限。

        Returns:
            int: 号值；用尽返回 `PROBE_EXHAUSTED`。
        """
        raw = self._client().eval(
            ACQUIRE_SCRIPT,
            0,
            prefix,
            self._random_start(),
            WORKER_ID_POOL_MIN,
            WORKER_ID_POOL_MAX,
            self._token or "",
            ttl,
            limit,
        )
        return int(raw)

    def _activate(self, worker_id: int, source: str, key: str) -> None:
        """生效并启动心跳。

        Args:
            worker_id: 号值。
            source: 来源标注。
            key: 持有键。
        """
        self._apply(worker_id, source, key)
        self._failed_since = None
        self._log_acquired()
        self._start_heartbeat()

    def _degrade(self, reason: str) -> None:
        """降级：回落 `[app].worker_id` 并告警。

        Args:
            reason: 降级原因（日志用）。
        """
        self._apply(self._settings.app.worker_id, SOURCE_FALLBACK, None)
        _LOGGER.warning("worker_id_degraded", reason=reason, worker_id=self._worker_id)

    def _start_heartbeat(self) -> None:
        """启动心跳线程（`_activate` / 重新占号后各调用一次）。"""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._heartbeat_loop, name="bms-worker-id-heartbeat", daemon=True)
        self._thread.start()

    def _stop_heartbeat(self) -> None:
        """停止心跳线程并等待退出（幂等）。"""
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stop.set()
        thread.join(timeout=2.0)

    def _heartbeat_loop(self) -> None:
        """心跳循环（线程体；停止事件置位即退出）。"""
        interval = self._settings.worker_id.heartbeat_seconds
        while not self._stop.wait(interval):
            self.heartbeat_once()

    def _on_heartbeat_failure(self, reason: str) -> None:
        """记录一次心跳失败；持续达 TTL/3 即尝试重新占号。

        Args:
            reason: 失败原因（日志用）。
        """
        now = self._clock()
        if self._failed_since is None:
            self._failed_since = now
        _LOGGER.warning("worker_id_heartbeat_failed", reason=reason, worker_id=self._worker_id)
        threshold = self._settings.worker_id.lease_ttl_seconds / 3
        if now - self._failed_since < threshold:
            return
        self._reallocate(reason)

    def _reallocate(self, reason: str) -> None:
        """重新占号并 `reconfigure`（失败保留原号，下轮再试）。

        Args:
            reason: 触发原因（日志用）。
        """
        old_id = self._worker_id
        self._failed_since = None
        section = self._settings.worker_id
        prefix = build_worker_id_prefix(self._settings)
        self._token = build_holder_token(self._settings)
        try:
            worker_id = self._probe(prefix, section.lease_ttl_seconds, section.probe_limit)
        except _REDIS_ERRORS as exc:
            _LOGGER.warning("worker_id_reallocate_failed", reason=reason, worker_id=old_id, error=repr(exc))
            return
        if worker_id == PROBE_EXHAUSTED:
            _LOGGER.warning("worker_id_reallocate_failed", reason="exhausted", worker_id=old_id)
            return
        self._apply(worker_id, SOURCE_REGISTRY, f"{prefix}{worker_id}")
        _LOGGER.warning("worker_id_reallocated", old_id=old_id, worker_id=worker_id, reason=reason)
