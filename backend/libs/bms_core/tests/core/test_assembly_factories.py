"""平台插件装配工厂用例（`core/assembly.py`）：惰性工厂构造 + 依赖解析 + 拒绝分支。

补齐装配清单中各 factory 的实例构造（Redis / 内存实现构造期不建连）、跨服务依赖解析、
依赖缺失 / 白名单非法 / 必需能力缺 provider 的拒启语义。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI

from bms_core.core import assembly
from bms_core.core.config import Settings
from bms_core.core.exceptions import PluginError


def test_lazy_factories_construct_without_connecting() -> None:
    """惰性工厂：Redis / 内存实现构造期不建连，各自返回能力实例。"""
    settings = Settings()
    assert assembly.RedisRedisClientFactory(settings).create() is not None
    assert assembly.PrometheusMetricsFactory(settings).create() is not None
    assert assembly.MemoryCacheRegionFactory().create() is not None
    assert assembly.RedisCacheRegionFactory(settings).create() is not None
    assert assembly.MemoryDistributedLockFactory().create() is not None
    assert assembly.RedisDistributedLockFactory(settings).create() is not None
    assert assembly.MemoryRateLimiterFactory().create() is not None
    assert assembly.RedisRateLimiterFactory(settings).create() is not None
    assert assembly.MemorySessionStoreFactory().create() is not None
    assert assembly.RedisSessionStoreFactory(settings).create() is not None
    assert assembly.MemoryIdpStateStoreFactory().create() is not None
    assert assembly.RedisIdpStateStoreFactory(settings).create() is not None
    assert assembly.MemoryDictCacheRegionFactory().create() is not None
    assert assembly.RedisDictCacheRegionFactory(settings).create() is not None
    assert assembly.RedisConfigCacheRegionFactory(settings).create() is not None
    assert assembly.RedisIdempotencyStoreFactory(settings).create() is not None
    assert assembly.RedisConsistencyBarrierFactory(settings).create() is not None


def test_minio_factory_rejects_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """MinIO 工厂：SDK 依赖缺失即拒启（`PluginError`）。"""

    def _missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(assembly, "import_module", _missing)

    with pytest.raises(PluginError, match="minio"):
        assembly.MinioObjectStorageFactory(Settings()).create()


def test_http_dependency_factories_resolve_service_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """跨服务依赖工厂：解析已装配的服务间调用客户端（配置 / 取数 / 翻译出口）。"""
    sentinel = object()

    def _resolve(*args: object, **kwargs: object) -> object:
        return sentinel

    monkeypatch.setattr(assembly, "resolve_plugin", _resolve)
    app = FastAPI()
    app.state.settings = Settings()

    assert assembly.HttpConfigSourceFactory(app).create() is not None
    assert assembly.HttpDataSourceFactory(app).create() is not None
    assert assembly.HttpDictTranslatorFactory(app).create() is not None


def test_table_ownership_guard_factory_rejects_invalid_entries(tmp_path: Path) -> None:
    """数据所有权守卫：绝对路径直取；白名单语义非法即拒启。"""
    settings = Settings()
    path = tmp_path / "exceptions.json"
    settings.data_ownership.exceptions_file = str(path)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "exceptions": [
                    {
                        "service": "ghost-service",
                        "target_prefix": "ghost_table",
                        "access": "read",
                        "exit": "no-such-exit",
                        "consumer": "c",
                        "reason": "r",
                        "alternative": "a",
                        "expiry": "2026-12-31",
                        "registered_at": "2026-13-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PluginError, match="数据所有权例外白名单非法"):
        assembly.TableOwnershipGuardFactory(settings).create()


def test_platform_plugins_rebuild_after_reset_uses_current_settings() -> None:
    """`reset()` 后重新装配用**当前**配置重建工厂（不沿用上一次装配的配置快照）。

    回归背景（2026-10-22 CI）：platform / identity 在 `prepare_settings` 把 `[permission].provider`
    改为 `rbac`；插件工厂在登记时捕获该配置。注册表 `reset()` 只解冻、不清显式登记，若幂等键取
    「注册表实例」就会跳过重新登记，导致后续未登记取数实现的服务（file / ai 等）解析 masking 时
    仍走 rbac 校验器并因缺数据来源拒启。
    """
    from bms_core.core.plugin import default_plugin_registry, resolve_plugin
    from bms_core.core.resources import ResourceManager
    from bms_core.masking.null import NullMasker
    from bms_core.permission.sources import reset_permission_data_sources

    # 用进程默认注册表（自动候选已登记其中；换新实例会丢 null 实现），结束时复位避免顺序污染
    registry = default_plugin_registry()
    registry.reset()
    reset_permission_data_sources()
    app = FastAPI()
    resources = ResourceManager()
    try:
        stale = Settings()
        stale.permission.provider = "rbac"  # 模拟 platform / identity 的 prepare_settings 就地改写
        assembly.register_platform_plugins(stale, app, resources)

        registry.reset()  # 测试隔离：解冻回未构建态
        reset_permission_data_sources()
        fresh = Settings()
        fresh.permission.provider = ""
        assembly.register_platform_plugins(fresh, app, resources)

        masker = resolve_plugin("masking", "")
        assert isinstance(masker, NullMasker)
    finally:
        registry.reset()
        reset_permission_data_sources()


async def test_assemble_plugins_rejects_required_redis_without_provider() -> None:
    """装配入口：Redis 为必需能力但 provider 为空即拒启（不进入逐项装配）。"""
    settings = Settings()
    settings.redis.required = True
    settings.redis.provider = ""

    with pytest.raises(PluginError, match="Redis 为基础能力"):
        await assembly.assemble_plugins(FastAPI(), settings, cast("Any", object()))
