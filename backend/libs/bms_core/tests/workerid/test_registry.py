"""WorkerId 注册租约算法用例（Kiwi 2397）：探测 / 配置优先 / 释放 / TTL / 心跳 / 降级 / 拒启。

覆盖 `bms_core/workerid/{base,redis,null,lease}.py`；Redis 侧一律 fakeredis（支持 Lua），零外部依赖。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import fakeredis
import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from bms_core.core import config as config_module
from bms_core.core.config import Settings, load_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.id import MAX_WORKER_ID, id_generator
from bms_core.redis.base import clear_shared_redis_client
from bms_core.workerid.base import (
    SOURCE_CONFIG,
    SOURCE_FALLBACK,
    SOURCE_NONE,
    SOURCE_REGISTRY,
    WORKER_ID_POOL_MAX,
    build_holder_token,
    build_worker_id_key,
    build_worker_id_prefix,
    worker_id_unit,
)
from bms_core.workerid.lease import (
    build_worker_id_registry,
    ensure_worker_id_ready,
    worker_id_lease,
    worker_id_lease_sync,
)
from bms_core.workerid.null import NullWorkerIdRegistry
from bms_core.workerid.redis import PROBE_EXHAUSTED, RedisWorkerIdRegistry

_BASE_CONFIG = """
[app]
name = "BMS 测试"
env = "{env}"
worker_id = {worker_id}
service = "{service}"
unit = "{unit}"

[server]
host = "127.0.0.1"
port = 8000

[log]
level = "INFO"

[database.platform]
url = "sqlite+aiosqlite:///./workerid_test.db"

[database.tenants]
url = "sqlite+aiosqlite:///./workerid_test.db"

[database.archive]
url = "sqlite+aiosqlite:///./workerid_test.db"

[redis]
provider = "redis"
url = "redis://localhost:6379/0"
required = false

[worker_id]
enabled = {enabled}
provider = "{provider}"
lease_ttl_seconds = {ttl}
heartbeat_seconds = {heartbeat}
probe_limit = {probe}
"""


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    env: str = "dev",
    worker_id: int = 0,
    service: str = "",
    unit: str = "",
    enabled: bool = True,
    provider: str = "redis",
    ttl: int = 60,
    heartbeat: int = 20,
    probe: int = 256,
) -> Settings:
    """构造隔离配置（临时 config.toml；屏蔽外部 BMS_ 环境变量）。

    Args:
        monkeypatch: monkeypatch 夹具。
        tmp_path: 临时目录。
        env: 运行环境。
        worker_id: `[app].worker_id`（显式偏好 / 兜底）。
        service: 服务标识。
        unit: 部署单元标识。
        enabled: 注册开关。
        provider: 实现名。
        ttl: 租约 TTL（秒）。
        heartbeat: 心跳间隔（秒）。
        probe: 探测上限。

    Returns:
        Settings: 应用配置。
    """
    body = _BASE_CONFIG.format(
        env=env,
        worker_id=worker_id,
        service=service,
        unit=unit,
        enabled=str(enabled).lower(),
        provider=provider,
        ttl=ttl,
        heartbeat=heartbeat,
        probe=probe,
    )
    (tmp_path / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(config_module, "_config_dir", lambda: tmp_path)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in ("BMS_ENV", "BMS_APP__WORKER_ID", "BMS_APP__SERVICE", "BMS_APP__UNIT"):
        monkeypatch.delenv(key, raising=False)
    for key in list(os.environ):
        if key.startswith(("BMS_WORKER_ID__", "BMS_REDIS__")):
            monkeypatch.delenv(key, raising=False)
    return Settings()


def _fake() -> Redis:
    """fakeredis 同步客户端（支持 Lua）。

    Returns:
        Redis: 假客户端。
    """
    return cast("Redis", fakeredis.FakeRedis(decode_responses=True))


class _Broken:
    """Redis 故障替身：`set` / `eval` 一律抛连接异常（模拟不可用）。"""

    def set(self, *args: Any, **kwargs: Any) -> Any:
        """模拟 `SET` 失败。"""
        raise RedisConnectionError("boom")

    def eval(self, *args: Any, **kwargs: Any) -> Any:
        """模拟 `EVAL` 失败。"""
        raise RedisConnectionError("boom")


class _Clock:
    """可拨动的单调时钟替身。"""

    def __init__(self) -> None:
        """初始化（从 0 起）。"""
        self.now = 0.0

    def __call__(self) -> float:
        """取当前时刻。

        Returns:
            float: 当前时刻。
        """
        return self.now


def _starts(*values: int) -> Any:
    """构造按序返回的探测起点生成器（用尽重复末值）。

    Args:
        *values: 起点序列。

    Returns:
        Any: 无参可调用。
    """
    seq = list(values)

    def _next() -> int:
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return _next


@pytest.fixture(autouse=True)
def _restore_generator() -> Iterator[None]:
    """用例后复原进程级生成器（WorkerId 回落 0）。

    Yields:
        None: 用例运行期。
    """
    yield
    id_generator.reconfigure(0)
    clear_shared_redis_client()


@pytest.mark.kiwi_id(2397)
def test_configured_worker_id_is_acquired_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """配置值优先占号：占得到就用它（`source=config`），并写 TTL。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=11)
    client = _fake()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(3))

    registry.acquire()

    assert registry.worker_id == 11
    assert registry.source == SOURCE_CONFIG
    assert registry.key_name == build_worker_id_key(settings, 11)
    assert 0 < int(cast("Any", client.ttl(cast("Any", registry.key_name)))) <= 60
    assert ((id_generator.next_id() >> 38) & MAX_WORKER_ID) == 11
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_configured_worker_id_taken_falls_back_to_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """配置值已被占：改走注册分配（`source=registry`），告警不阻断。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=11)
    client = _fake()
    client.set(build_worker_id_key(settings, 11), "other-holder", ex=60)
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(11))

    registry.acquire()

    assert registry.worker_id == 12
    assert registry.source == SOURCE_REGISTRY
    assert client.get(cast("str", registry.key_name)) != "other-holder"
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_probe_uses_random_start_and_skips_occupied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """无显式配置：按随机起点探测，起点被占则顺延。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    first = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(5))
    first.acquire()
    second = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(5))
    second.acquire()

    assert (first.worker_id, second.worker_id) == (5, 6)
    first.release()
    second.release()


@pytest.mark.kiwi_id(2397)
def test_release_frees_id_for_reuse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """释放后号可复用（CAS 删除）。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    first = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7))
    first.acquire()
    key = cast("str", first.key_name)

    first.release()
    assert client.get(key) is None

    second = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7))
    second.acquire()
    assert second.worker_id == 7
    second.release()


@pytest.mark.kiwi_id(2397)
def test_release_does_not_delete_other_holder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """令牌不匹配不误删：迟到释放不会删掉新持有者的租约。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7))
    registry.acquire()
    key = cast("str", registry.key_name)
    client.set(key, "new-holder", ex=60)

    registry.release()

    assert client.get(key) == "new-holder"
    assert registry.key_name is None
    assert registry.source == SOURCE_NONE


@pytest.mark.kiwi_id(2397)
def test_expired_lease_can_be_reclaimed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TTL 到期（键消失）后同一号可被再次占用。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    first = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(9))
    first.acquire()
    client.delete(cast("str", first.key_name))  # 模拟 TTL 到期 / 进程崩溃

    second = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(9))
    second.acquire()

    assert second.worker_id == 9
    assert second.source == SOURCE_REGISTRY
    second.release()


@pytest.mark.kiwi_id(2397)
def test_acquire_degrades_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redis 不可用：回落 `[app].worker_id`（`source=fallback`），不持键。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=21)
    registry = RedisWorkerIdRegistry(settings, client=cast("Redis", _Broken()), random_start=_starts(1))

    registry.acquire()

    assert registry.worker_id == 21
    assert registry.source == SOURCE_FALLBACK
    assert registry.key_name is None
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_acquire_degrades_when_shared_client_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """共享客户端未登记（`RedisUnavailableError`）：同样按降级口径回落。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=22)
    clear_shared_redis_client()
    registry = RedisWorkerIdRegistry(settings, random_start=_starts(1))

    registry.acquire()

    assert (registry.worker_id, registry.source) == (22, SOURCE_FALLBACK)
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_acquire_degrades_when_probe_exhausted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """探测上限内无空闲号：按降级口径回落配置值。"""
    settings = _settings(monkeypatch, tmp_path, probe=1)
    client = _fake()
    client.set(build_worker_id_key(settings, 33), "other-holder", ex=60)
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(33))

    registry.acquire()

    assert (registry.worker_id, registry.source) == (0, SOURCE_FALLBACK)


@pytest.mark.kiwi_id(2397)
def test_acquire_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重复 `acquire` 不换号、不重复占键。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(5))
    registry.acquire()
    first = registry.worker_id

    registry.acquire()

    assert registry.worker_id == first
    assert len(list(client.keys("*worker_id*"))) == 1  # pyright: ignore[reportUnknownMemberType]
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_null_registry_uses_configured_worker_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """旁路实现：直接用配置值（`source=config`），释放只清标记。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=13, enabled=False)
    registry = NullWorkerIdRegistry(settings)

    registry.acquire()
    registry.acquire()

    assert (registry.worker_id, registry.source, registry.key_name) == (13, SOURCE_CONFIG, None)
    registry.release()
    assert registry.source == SOURCE_NONE


@pytest.mark.kiwi_id(2397)
def test_assert_ready_allows_dev_and_prod_with_configured_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """非生产环境与「生产已配置号」均放行。"""
    dev = _settings(monkeypatch, tmp_path, env="dev", worker_id=0)
    ensure_worker_id_ready(NullWorkerIdRegistry(dev))

    configured = _settings(monkeypatch, tmp_path, env="prod", worker_id=41)
    registry = NullWorkerIdRegistry(configured)
    registry.acquire()
    ensure_worker_id_ready(registry)
    assert registry.worker_id == 41


@pytest.mark.kiwi_id(2397)
def test_assert_ready_raises_in_prod_with_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """生产环境仍为 0：`assert_ready` 抛 `ConfigError`（40001）。"""
    settings = _settings(monkeypatch, tmp_path, env="prod", worker_id=0)
    registry = NullWorkerIdRegistry(settings)
    registry.acquire()

    with pytest.raises(ConfigError) as excinfo:
        ensure_worker_id_ready(registry)
    assert "WorkerId" in str(excinfo.value)


@pytest.mark.kiwi_id(2397)
def test_build_registry_by_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """按 `[worker_id]` 选实现：关闭 / `null` → 旁路，`redis` → 租约，非法 provider → 拒绝。"""
    disabled = _settings(monkeypatch, tmp_path, enabled=False)
    assert isinstance(build_worker_id_registry(disabled), NullWorkerIdRegistry)

    null_provider = _settings(monkeypatch, tmp_path, provider="null")
    assert isinstance(build_worker_id_registry(null_provider), NullWorkerIdRegistry)

    redis_provider = _settings(monkeypatch, tmp_path, provider="redis")
    assert isinstance(build_worker_id_registry(redis_provider), RedisWorkerIdRegistry)

    invalid = _settings(monkeypatch, tmp_path, provider="etcd")
    with pytest.raises(ConfigError):
        build_worker_id_registry(invalid)


@pytest.mark.kiwi_id(2397)
def test_key_prefix_isolated_by_env_and_unit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """键按 env + unit 隔离；unit 空回落 service，再空回落 default。"""
    unit = _settings(monkeypatch, tmp_path, env="test", unit="biz-unit", service="platform")
    assert worker_id_unit(unit) == "biz-unit"
    assert build_worker_id_prefix(unit) == "bms:test:biz-unit:worker_id:v2:"
    assert build_worker_id_key(unit, 5) == "bms:test:biz-unit:worker_id:v2:5"

    by_service = _settings(monkeypatch, tmp_path, env="test", service="platform")
    assert build_worker_id_prefix(by_service) == "bms:test:platform:worker_id:v2:"

    fallback = _settings(monkeypatch, tmp_path, env="test")
    assert build_worker_id_prefix(fallback) == "bms:test:default:worker_id:v2:"

    token = build_holder_token(by_service)
    parts = token.split("|")
    assert len(parts) == 4
    assert parts[0] == "platform"
    assert parts[2].isdigit()


@pytest.mark.kiwi_id(2397)
def test_pool_bounds_exclude_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """注册池上界与雪花机器段一致，且 0 不参与分配（缺省起点同样落在池内）。"""
    assert WORKER_ID_POOL_MAX == MAX_WORKER_ID
    assert PROBE_EXHAUSTED == -1
    settings = _settings(monkeypatch, tmp_path)
    registry = RedisWorkerIdRegistry(settings, client=_fake())
    start = registry._default_start()  # pyright: ignore[reportPrivateUsage]
    assert 1 <= start <= MAX_WORKER_ID


@pytest.mark.kiwi_id(2397)
def test_heartbeat_renews_lease(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """心跳续期：TTL 被拉回租约时长。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(5))
    registry.acquire()
    key = cast("str", registry.key_name)
    client.expire(key, 3)

    registry.heartbeat_once()

    assert int(cast("Any", client.ttl(key))) > 3
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_heartbeat_reallocates_after_lease_lost(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """心跳失租：连续失败达 TTL/3 后重新占号并同步生成器。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    clock = _Clock()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7, 9), clock=clock)
    registry.acquire()
    assert registry.worker_id == 7
    client.delete(cast("str", registry.key_name))  # 租约丢失（过期或被他人抢占）

    registry.heartbeat_once()
    assert registry.worker_id == 7

    clock.now = 25.0
    registry.heartbeat_once()

    assert registry.worker_id == 9
    assert registry.source == SOURCE_REGISTRY
    assert ((id_generator.next_id() >> 38) & MAX_WORKER_ID) == 9
    registry.release()


@pytest.mark.kiwi_id(2397)
def test_heartbeat_keeps_id_when_reallocate_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重新占号失败（Redis 抖动）：保留原号并下轮重试。"""
    settings = _settings(monkeypatch, tmp_path)
    client = _fake()
    clock = _Clock()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7), clock=clock)
    registry.acquire()
    client.delete(cast("str", registry.key_name))
    registry._client_override = cast("Any", _Broken())  # pyright: ignore[reportPrivateUsage]

    registry.heartbeat_once()
    clock.now = 25.0
    registry.heartbeat_once()

    assert registry.worker_id == 7
    assert registry.source == SOURCE_REGISTRY


@pytest.mark.kiwi_id(2397)
def test_heartbeat_keeps_id_when_reallocate_exhausted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重新占号探测用尽：保留原号（不换号）。"""
    settings = _settings(monkeypatch, tmp_path, probe=1)
    client = _fake()
    clock = _Clock()
    registry = RedisWorkerIdRegistry(settings, client=client, random_start=_starts(7), clock=clock)
    registry.acquire()
    client.delete(cast("str", registry.key_name))
    client.set(build_worker_id_key(settings, 7), "other-holder", ex=60)

    registry.heartbeat_once()
    clock.now = 25.0
    registry.heartbeat_once()

    assert registry.worker_id == 7
    assert registry.source == SOURCE_REGISTRY


@pytest.mark.kiwi_id(2397)
def test_heartbeat_without_lease_is_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未持有租约（降级 / 未取号）时心跳为空操作。"""
    settings = _settings(monkeypatch, tmp_path)
    registry = RedisWorkerIdRegistry(settings, client=_fake())

    registry.heartbeat_once()

    assert registry.source == SOURCE_NONE


@pytest.mark.kiwi_id(2397)
def test_heartbeat_loop_runs_until_stopped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """心跳循环体执行一轮即随停止事件退出（线程体逻辑单测，不依赖真实 sleep）。"""

    class _Stop:
        """停止事件替身：首次等待返回 False（跑一轮），之后返回 True。"""

        def __init__(self) -> None:
            """初始化（计数 0）。"""
            self.calls = 0

        def wait(self, timeout: float) -> bool:
            """模拟 `Event.wait`。

            Args:
                timeout: 间隔。

            Returns:
                bool: 是否已停止。
            """
            self.calls += 1
            return self.calls > 1

    settings = _settings(monkeypatch, tmp_path)
    registry = RedisWorkerIdRegistry(settings, client=_fake())
    stop = _Stop()
    registry._stop = cast("Any", stop)  # pyright: ignore[reportPrivateUsage]

    registry._heartbeat_loop()  # pyright: ignore[reportPrivateUsage]

    assert stop.calls == 2


@pytest.mark.kiwi_id(2397)
def test_release_reports_redis_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """释放时 Redis 抖动只告警，不抛错（键由 TTL 回收）。"""
    settings = _settings(monkeypatch, tmp_path)
    registry = RedisWorkerIdRegistry(settings, client=_fake(), random_start=_starts(5))
    registry.acquire()
    registry._client_override = cast("Any", _Broken())  # pyright: ignore[reportPrivateUsage]

    registry.release()

    assert registry.key_name is None


@pytest.mark.kiwi_id(2397)
def test_sync_lease_context_manager_acquires_and_releases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """同步上下文：取号生效，退出即释放（生产配置校验一并生效）。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=17)
    monkeypatch.setattr("bms_core.workerid.redis.shared_sync_client", lambda: _fake())
    clear_shared_redis_client()

    with worker_id_lease_sync(settings) as registry:
        assert (registry.worker_id, registry.source) == (17, SOURCE_CONFIG)
        key = cast("str", registry.key_name)

    assert build_worker_id_key(settings, 17) == key
    assert registry.key_name is None


@pytest.mark.kiwi_id(2397)
async def test_async_lease_context_manager_acquires_and_releases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """异步上下文：取号生效，退出即释放。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=18)
    monkeypatch.setattr("bms_core.workerid.redis.shared_sync_client", lambda: _fake())
    clear_shared_redis_client()

    async with worker_id_lease(settings) as registry:
        assert (registry.worker_id, registry.source) == (18, SOURCE_CONFIG)

    assert registry.key_name is None


@pytest.mark.kiwi_id(2397)
def test_sync_lease_context_rejects_prod_without_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """生产环境无号可用：上下文在交出前即拒启（`ConfigError`）。"""
    settings = _settings(monkeypatch, tmp_path, env="prod", worker_id=0, enabled=False)

    with pytest.raises(ConfigError), worker_id_lease_sync(settings):
        pytest.fail("不应进入上下文")


_MINIMAL_CONFIG = """
[app]
name = "BMS 测试"
env = "dev"

[server]
host = "127.0.0.1"
port = 8000

[log]
level = "INFO"

[database.platform]
url = "sqlite+aiosqlite:///./workerid_min.db"

[database.tenants]
url = "sqlite+aiosqlite:///./workerid_min.db"

[database.archive]
url = "sqlite+aiosqlite:///./workerid_min.db"
"""


def _write_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    """写入临时配置并清空外部 `BMS_` 环境变量（保证默认值断言稳定）。

    Args:
        monkeypatch: monkeypatch 夹具。
        tmp_path: 临时目录。
        body: config.toml 内容。
    """
    (tmp_path / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(config_module, "_config_dir", lambda: tmp_path)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("BMS_"):
            monkeypatch.delenv(key, raising=False)


@pytest.mark.kiwi_id(2397)
def test_worker_id_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`[worker_id]` 缺省值：启用、租约实现、TTL 60 / 心跳 20 / 探测 256。"""
    _write_config(monkeypatch, tmp_path, _MINIMAL_CONFIG)

    section = Settings().worker_id

    assert (section.enabled, section.provider) == (True, "redis")
    assert section.lease_ttl_seconds == 60
    assert section.heartbeat_seconds == 20
    assert section.probe_limit == 256


@pytest.mark.kiwi_id(2397)
def test_worker_id_settings_rejects_heartbeat_not_less_than_ttl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """心跳间隔必须小于租约 TTL（否则续租永远赶不上过期）。"""
    _write_config(
        monkeypatch,
        tmp_path,
        _MINIMAL_CONFIG + "\n[worker_id]\nlease_ttl_seconds = 30\nheartbeat_seconds = 30\n",
    )

    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "heartbeat_seconds" in str(excinfo.value)
