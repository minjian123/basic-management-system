"""应用装配期校验路径补齐用例（`bms_core/application.py`）。

补齐既有用例未触达的分支：连接池预算告警（平台 / 租户两路）、指标器缺失时跳过库数量上报、
表归属离线清单违规拒启、接库不可读降级放行与接库记录不一致拒启。
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest
from support_app import ApplicationFactory

from bms_core import application as app_module
from bms_core.core import assembly
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import CatalogError
from bms_core.redis.base import clear_shared_redis_client, shared_redis_client
from bms_core.services.table_registry import (
    register_table_records,
    reset_table_records,
    table_record,
)


class _BrokenScope:
    """会话作用域替身：进入即抛错（模拟库不可读）。"""

    async def __aenter__(self) -> object:
        """进入即抛错。

        Raises:
            RuntimeError: 库不可读。
        """
        raise RuntimeError("db down")

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """退出（占位）。

        Args:
            exc_type: 异常类型。
            exc: 异常对象。
            tb: 回溯。
        """


class _Scalars:
    """`Result.scalars()` 替身：恒定返回一条记录。"""

    def all(self) -> ConcurrentStableList[object]:
        """返回记录清单。

        Returns:
            ConcurrentStableList[object]: 单条记录。
        """
        return ConcurrentStableList([object()])


class _Result:
    """查询结果替身。"""

    def scalars(self) -> _Scalars:
        """返回标量集合。

        Returns:
            _Scalars: 标量集合替身。
        """
        return _Scalars()


class _Session:
    """会话替身：`execute` 恒定返回一条记录。"""

    async def execute(self, statement: object) -> _Result:
        """执行查询（占位）。

        Args:
            statement: SQL 语句（占位）。

        Returns:
            _Result: 结果替身。
        """
        del statement
        return _Result()


class _SessionScope:
    """会话作用域替身：产出占位会话。"""

    async def __aenter__(self) -> Any:
        """产出会话。

        Returns:
            Any: 会话替身。
        """
        return _Session()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """退出（占位）。

        Args:
            exc_type: 异常类型。
            exc: 异常对象。
            tb: 回溯。
        """


def _broken_scope(*args: object, **kwargs: object) -> _BrokenScope:
    """构造恒抛错的会话作用域。

    Args:
        args: 位置参数（忽略）。
        kwargs: 关键字参数（忽略）。

    Returns:
        _BrokenScope: 会话作用域替身。
    """
    del args, kwargs
    return _BrokenScope()


def _session_scope(*args: object, **kwargs: object) -> _SessionScope:
    """构造产出占位会话的作用域。

    Args:
        args: 位置参数（忽略）。
        kwargs: 关键字参数（忽略）。

    Returns:
        _SessionScope: 会话作用域替身。
    """
    del args, kwargs
    return _SessionScope()


def _from_row(row: object) -> object:
    """清单行 → 记录（替身：原样返回）。

    Args:
        row: 行对象。

    Returns:
        object: 行对象。
    """
    return row


def _ownership_errors(view: object, records: object) -> ConcurrentStableList[str]:
    """接库对账替身：恒定返回一条不一致。

    Args:
        view: 清单视图（忽略）。
        records: 接库记录（忽略）。

    Returns:
        ConcurrentStableList[str]: 问题清单。
    """
    del view, records
    return ConcurrentStableList(["库中缺登记行"])


def _ownership_ok(view: object, records: object) -> ConcurrentStableList[str]:
    """接库对账替身：恒定通过（空问题清单）。

    Args:
        view: 清单视图（忽略）。
        records: 接库记录（忽略）。

    Returns:
        ConcurrentStableList[str]: 空问题清单。
    """
    del view, records
    return ConcurrentStableList()


def _platform_warnings(settings: object) -> ConcurrentStableList[str]:
    """平台连接池预算告警替身：恒定返回一条。

    Args:
        settings: 应用配置（忽略）。

    Returns:
        ConcurrentStableList[str]: 告警文案。
    """
    del settings
    return ConcurrentStableList(["平台超限"])


def _tenant_warnings(settings: object, limit: object) -> ConcurrentStableList[str]:
    """租户连接池预算告警替身：恒定返回一条。

    Args:
        settings: 应用配置（忽略）。
        limit: 活跃租户上限（忽略）。

    Returns:
        ConcurrentStableList[str]: 告警文案。
    """
    del settings, limit
    return ConcurrentStableList(["租户超限"])


def _app() -> Any:
    """构造装配期校验所需的最小应用替身。

    Returns:
        Any: 应用替身（含身份 / 引擎注册表 / 会话工厂）。
    """
    return SimpleNamespace(
        state=SimpleNamespace(
            service_identity=SimpleNamespace(name=app_module.PLATFORM_SERVICE_KEY),
            engine_registry=object(),
            session_factory=object(),
        )
    )


async def test_service_lifespan_warns_on_pool_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动期连接池预算超限：平台 / 租户两类各记一条告警，不阻断启动。"""
    monkeypatch.setattr(app_module, "pool_budget_warnings", _platform_warnings)
    monkeypatch.setattr(app_module, "tenant_pool_budget_warnings", _tenant_warnings)
    app = ApplicationFactory().create(None)
    async with app_module.service_lifespan(app):
        assert app.state.service_identity.name == "core_test"


async def test_record_db_inventory_skips_without_metrics() -> None:
    """指标器缺失：库数量上报直接跳过（不构造指标）。"""
    app = SimpleNamespace(state=SimpleNamespace())
    await app_module._record_db_inventory(cast("Any", app), get_settings())  # pyright: ignore[reportPrivateUsage]


async def test_validate_table_ownership_offline_conflict() -> None:
    """离线清单违规（同表异值注入）→ 拒启（CatalogError）。"""
    record = table_record("sys_notification")
    assert record is not None
    register_table_records(ConcurrentStableList([replace(record, note="冲突登记")]))
    try:
        with pytest.raises(CatalogError):
            await app_module._validate_table_ownership(_app())  # pyright: ignore[reportPrivateUsage]
    finally:
        reset_table_records()


async def test_validate_table_ownership_degrades_when_db_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """接库不可读（未迁移）→ 降级放行并标记 `ownership_degraded`。"""
    monkeypatch.setattr(app_module, "session_scope", _broken_scope)
    app = _app()
    await app_module._validate_table_ownership(app)  # pyright: ignore[reportPrivateUsage]
    assert app.state.ownership_degraded is True


async def test_validate_table_ownership_rejects_db_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """接库记录与清单不一致 → 拒启（CatalogError）。"""
    monkeypatch.setattr(app_module, "session_scope", _session_scope)
    monkeypatch.setattr(app_module, "TableRecord", SimpleNamespace(from_row=_from_row))
    monkeypatch.setattr(app_module, "validate_table_ownership", _ownership_errors)
    with pytest.raises(CatalogError):
        await app_module._validate_table_ownership(_app())  # pyright: ignore[reportPrivateUsage]


async def test_validate_table_ownership_passes_when_consistent(monkeypatch: pytest.MonkeyPatch) -> None:
    """接库记录与清单一致 → 正常返回（不抛错，不置降级标记）。"""
    monkeypatch.setattr(app_module, "session_scope", _session_scope)
    monkeypatch.setattr(app_module, "TableRecord", SimpleNamespace(from_row=_from_row))
    monkeypatch.setattr(app_module, "validate_table_ownership", _ownership_ok)
    app = _app()
    await app_module._validate_table_ownership(app)  # pyright: ignore[reportPrivateUsage]
    assert getattr(app.state, "ownership_degraded", False) is False


@pytest.mark.kiwi_id(2299)
async def test_lifespan_assembles_base_capabilities_before_db_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启动顺序（缺陷 #104 回归）：基础能力（Redis 统一客户端）先于开库引导 / 接库校验登记。

    开库引导与接库校验都要取数据库引擎，而引擎注册表的**跨实例创建锁**经分布式锁基座取共享
    Redis 客户端；该客户端由基础能力装配期登记，未登记时取到 `null` 实现即 fail-closed 拒启
    （platform 接库校验读本服务平台库故必然触发）。用例先清空共享登记，再断言两个取库步骤
    执行时取到的是真实客户端（即基础能力已先行装配）。
    """
    monkeypatch.setenv("BMS_REDIS__PROVIDER", "redis")
    get_settings.cache_clear()
    clear_shared_redis_client()
    observed: ConcurrentStableList[str] = ConcurrentStableList()

    async def _spy_schema(*args: object, **kwargs: object) -> ConcurrentStableList[str]:
        observed.add(type(shared_redis_client()).__name__)
        return ConcurrentStableList()

    async def _spy_catalog(app: object) -> None:
        del app
        observed.add(type(shared_redis_client()).__name__)

    monkeypatch.setattr(app_module, "ensure_development_schema", _spy_schema)
    monkeypatch.setattr(app_module, "_validate_service_catalog", _spy_catalog)
    app = ApplicationFactory().create(None)
    async with app_module.service_lifespan(app):
        assert app.state.startup_complete is True
    assert list(observed) == ["RedisRedisClient", "RedisRedisClient"]


@pytest.mark.kiwi_id(2300)
async def test_assemble_base_plugins_batches_without_duplicate_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """基础能力分批装配：先装基础能力、再装其余能力；已装配接线不重复解析，累计结果完整。"""
    app = ApplicationFactory().create(None)
    resolved: ConcurrentStableList[str] = ConcurrentStableList()
    original = assembly._resolve_or_reject  # pyright: ignore[reportPrivateUsage]

    def _spy(wiring: assembly.PluginWiring, provider: str) -> object:
        resolved.add(wiring.plugin_key)
        return original(wiring, provider)

    monkeypatch.setattr(assembly, "_resolve_or_reject", _spy)
    settings = get_settings()
    base = await assembly.assemble_base_plugins(app, settings, app.state.resources)
    assert list(base.keys()) == list(assembly.BASE_PLUGIN_KEYS)
    assert list(resolved) == list(assembly.BASE_PLUGIN_KEYS)
    full = await assembly.assemble_plugins(app, settings, app.state.resources)
    expected = {wiring.plugin_key for wiring in assembly.PLUGIN_WIRINGS}
    assert set(full.keys()) == expected
    assert set(app.state.assembled_plugin_keys) == expected
    assert resolved.count("redis_client") == 1
    await app.state.resources.aclose()
