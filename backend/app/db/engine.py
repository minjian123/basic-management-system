"""多数据源异步引擎工厂。

- EngineRegistry：按数据源 key 懒加载 AsyncEngine（首次访问创建，字典缓存），避免全量租户连接常驻
- 连接池：pool_size / max_overflow 从 config.toml [database] 读取；
  多 worker 部署按 总连接数 = worker × (pool_size + max_overflow) ≤ DB max_connections 70% 规划
- 平台库（platform）与租户库（tenant:{code}，URL 由模板生成）为阶段一入口，读写分离留待阶段八
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.config import DatabaseSettings, get_settings

registry: EngineRegistry | None = None


def _build_engine(url: str, settings: DatabaseSettings) -> AsyncEngine:
    """按方言构造异步引擎：SQLite 不启用连接池，其余按配置 pool_size / max_overflow。"""
    kwargs: dict[str, Any] = {
        "echo": settings.echo,
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = settings.pool_size
        kwargs["max_overflow"] = settings.max_overflow
    return create_async_engine(url, **kwargs)


class EngineRegistry:
    """数据源引擎注册表：懒加载 + 池上限 + 闲置回收。"""

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self._settings = settings or get_settings().database
        self._engines: dict[str, AsyncEngine] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, url: str | None = None) -> AsyncEngine:
        """获取指定数据源引擎；不存在则按配置创建（懒加载）。"""
        if key not in self._engines:
            async with self._lock:
                if key not in self._engines:
                    self._engines[key] = _build_engine(url or self._url_for(key), self._settings)
        return self._engines[key]

    def _url_for(self, key: str) -> str:
        """数据源 key → 连接串：platform 用平台库 URL，tenant:{code} 用模板替换 {code}。"""
        if key == "platform":
            return self._settings.platform_url
        if key.startswith("tenant:"):
            code = key.removeprefix("tenant:")
            return self._settings.tenant_url_template.replace("{code}", code)
        raise KeyError(f"unknown datasource key: {key}")

    async def dispose(self, key: str | None = None) -> None:
        """释放指定引擎（None 时释放全部），应用关闭时调用。"""
        if key is not None:
            engine = self._engines.pop(key, None)
            if engine is not None:
                await engine.dispose()
            return
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()

    async def idle_recycle(self, idle_seconds: float = 300.0) -> None:
        """闲置回收：当前仅预留接口，SQLAlchemy pool_recycle 由连接池层兜底。"""
        # 阶段一引擎均为懒加载且池上限受控，闲置回收策略阶段八随连接监控落地
        _ = idle_seconds


def get_registry() -> EngineRegistry:
    """获取全局引擎注册表单例（测试可通过参数注入覆盖）。"""
    global registry
    if registry is None:
        registry = EngineRegistry()
    return registry


async def get_platform_engine() -> AsyncEngine:
    """获取平台库异步引擎。"""
    return await get_registry().get("platform")


async def get_tenant_engine(tenant_code: str) -> AsyncEngine:
    """获取指定租户库异步引擎（懒创建）。"""
    return await get_registry().get(f"tenant:{tenant_code}")


async def db_check() -> bool:
    """平台库连通性检查（SELECT 1），供 /readyz 使用；失败返回 False 不抛异常。"""
    try:
        engine = await get_platform_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
