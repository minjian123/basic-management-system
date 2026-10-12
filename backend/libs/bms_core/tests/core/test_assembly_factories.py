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


async def test_assemble_plugins_rejects_required_redis_without_provider() -> None:
    """装配入口：Redis 为必需能力但 provider 为空即拒启（不进入逐项装配）。"""
    settings = Settings()
    settings.redis.required = True
    settings.redis.provider = ""

    with pytest.raises(PluginError, match="Redis 为基础能力"):
        await assembly.assemble_plugins(FastAPI(), settings, cast("Any", object()))
