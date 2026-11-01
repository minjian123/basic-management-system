"""WorkerId 注册接入用例（Kiwi 2398）：装配顺序 / 生命周期 / ops 入口覆盖 / compose 注入语义。

真 Redis 双实例用例见 `test_workerid_real_redis.py`（`BMS_TEST_REDIS_URL` 未配置即跳过）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import fakeredis
import pytest
from fastapi import FastAPI
from redis import Redis

from bms_core.core import config as config_module
from bms_core.core.assembly import BASE_PLUGIN_KEYS, assemble_base_plugins, register_platform_plugins
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.id import MAX_WORKER_ID, id_generator
from bms_core.core.resources import ResourceManager
from bms_core.redis.base import clear_shared_redis_client, current_shared_redis_client, shared_sync_client
from bms_core.redis.bootstrap import ensure_shared_redis_client
from bms_core.redis.null import NullRedisClient
from bms_core.redis.redis import RedisRedisClient
from bms_core.workerid.null import NullWorkerIdRegistry
from ops._worker import BOOTSTRAPPED_MODULES, EXCLUDED_MODULES

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _BACKEND_ROOT.parent

_BASE_CONFIG = """
[app]
name = "BMS 测试"
env = "dev"
worker_id = {worker_id}
service = "platform"
unit = "platform"

[server]
host = "127.0.0.1"
port = 8000

[log]
level = "INFO"

[database.platform]
url = "sqlite+aiosqlite:///./workerid_it.db"

[database.tenants]
url = "sqlite+aiosqlite:///./workerid_it.db"

[database.archive]
url = "sqlite+aiosqlite:///./workerid_it.db"

[redis]
provider = "{redis_provider}"
url = "redis://localhost:6379/0"
required = false

[worker_id]
enabled = {enabled}
provider = "{worker_provider}"
lease_ttl_seconds = 60
heartbeat_seconds = 20
probe_limit = 256
"""


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    worker_id: int = 0,
    enabled: bool = True,
    redis_provider: str = "redis",
    worker_provider: str = "redis",
) -> Settings:
    """构造隔离配置。

    Args:
        monkeypatch: monkeypatch 夹具。
        tmp_path: 临时目录。
        worker_id: `[app].worker_id`。
        enabled: 注册开关。
        redis_provider: `[redis].provider`。
        worker_provider: `[worker_id].provider`。

    Returns:
        Settings: 应用配置。
    """
    body = _BASE_CONFIG.format(
        worker_id=worker_id,
        enabled=str(enabled).lower(),
        redis_provider=redis_provider,
        worker_provider=worker_provider,
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


@pytest.fixture(autouse=True)
def _restore_generator() -> Iterator[None]:
    """用例后复原进程级生成器与共享客户端登记。

    Yields:
        None: 用例运行期。
    """
    yield
    id_generator.reconfigure(0)
    clear_shared_redis_client()


@pytest.mark.kiwi_id(2398)
def test_worker_id_registry_is_base_plugin_right_after_redis() -> None:
    """`worker_id_registry` 属基础能力，且排在 `redis_client` 之后（依赖共享客户端）。"""
    keys = list(BASE_PLUGIN_KEYS)
    assert "worker_id_registry" in keys
    assert keys.index("worker_id_registry") > keys.index("redis_client")


@pytest.mark.kiwi_id(2398)
async def test_assembly_acquires_lease_and_shutdown_releases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """装配即取号（`app.state.worker_id_registry` + 生成器生效）；关闭时释放租约。"""
    settings = _settings(monkeypatch, tmp_path, worker_id=23)
    fake = _fake()
    monkeypatch.setattr("bms_core.workerid.redis.shared_sync_client", lambda: fake)
    app = FastAPI()
    app.state.settings = settings
    resources = ResourceManager()
    register_platform_plugins(settings, app, resources)

    await assemble_base_plugins(app, settings, resources)

    registry = app.state.worker_id_registry
    assert (registry.worker_id, registry.source) == (23, "config")
    assert ((id_generator.next_id() >> 38) & MAX_WORKER_ID) == 23
    key = cast("str", registry.key_name)
    assert fake.get(key) is not None

    await resources.aclose()

    assert fake.get(key) is None


@pytest.mark.kiwi_id(2398)
async def test_assembly_with_registration_disabled_uses_bypass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`[worker_id].enabled=false`：装配走旁路实现（不访问 Redis），按配置值生效。"""
    settings = _settings(monkeypatch, tmp_path, enabled=False, worker_id=31)
    app = FastAPI()
    app.state.settings = settings
    resources = ResourceManager()
    register_platform_plugins(settings, app, resources)

    await assemble_base_plugins(app, settings, resources)

    registry = app.state.worker_id_registry
    assert isinstance(registry, NullWorkerIdRegistry)
    assert (registry.worker_id, registry.source) == (31, "config")
    await resources.aclose()


@pytest.mark.kiwi_id(2398)
async def test_assembly_with_null_provider_uses_bypass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`provider=null`（应急旁路）：解析到 null 实现，不触发 Redis 取号。"""
    settings = _settings(monkeypatch, tmp_path, worker_provider="null", worker_id=32)
    app = FastAPI()
    app.state.settings = settings
    resources = ResourceManager()
    register_platform_plugins(settings, app, resources)

    await assemble_base_plugins(app, settings, resources)

    registry = app.state.worker_id_registry
    assert isinstance(registry, NullWorkerIdRegistry)
    assert registry.worker_id == 32
    await resources.aclose()


@pytest.mark.kiwi_id(2398)
def test_ensure_shared_redis_client_registers_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """非应用进程登记共享客户端：幂等复用；`provider` 非 redis 时登记 null 实现（fail-closed）。"""
    settings = _settings(monkeypatch, tmp_path)
    clear_shared_redis_client()

    first = ensure_shared_redis_client(settings)
    second = ensure_shared_redis_client(settings)

    assert isinstance(first, RedisRedisClient)
    assert first is second
    assert current_shared_redis_client() is first

    bypass = _settings(monkeypatch, tmp_path, redis_provider="")
    clear_shared_redis_client()
    assert isinstance(ensure_shared_redis_client(bypass), NullRedisClient)
    with pytest.raises(RedisUnavailableError):
        shared_sync_client()


@pytest.mark.kiwi_id(2398)
def test_ops_entries_are_all_classified() -> None:
    """ops 入口覆盖护栏：调用 `asyncio.run` 的入口须在引导 / 排除清单内，且引导项确已接入。"""
    ops_dir = _BACKEND_ROOT / "ops"
    online_calls: ConcurrentStableList[str] = ConcurrentStableList()
    for path in ops_dir.glob("*.py"):
        if path.name.startswith("_"):
            continue
        module = f"ops.{path.stem}"
        source = path.read_text(encoding="utf-8")
        if "asyncio.run(" in source:
            online_calls.add(module)
        if module in BOOTSTRAPPED_MODULES:
            assert "run_with_worker_id(" in source or "worker_id_lease_sync(" in source, module
    for module in online_calls:
        assert module in BOOTSTRAPPED_MODULES or module in EXCLUDED_MODULES, (
            f"ops 入口未分类（接租约或列入排除）：{module}"
        )


@pytest.mark.kiwi_id(2398)
def test_compose_injection_is_preference_only() -> None:
    """部署编排：每容器仍注入 `BMS_APP__WORKER_ID`（互不相同），语义为「显式偏好 / 兜底」。"""
    text = (_REPO_ROOT / "deploy" / "compose" / "services.yml").read_text(encoding="utf-8")
    values = [
        line.split("BMS_APP__WORKER_ID:", 1)[1].strip() for line in text.splitlines() if "BMS_APP__WORKER_ID:" in line
    ]
    assert len(values) >= 10
    assert len(set(values)) == len(values)
    assert "显式偏好" in text
