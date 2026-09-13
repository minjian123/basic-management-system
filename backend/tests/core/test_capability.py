"""能力域中间层基类测试（Kiwi 26）：占位 / 能力域 / 异步资源。"""

import pytest

from app.audit.base import AuditCapturer
from app.cache.base import CacheRegion
from app.core.capability import (
    BaseAsyncResource,
    BaseCapability,
    BaseEventWorker,
    BaseNullObject,
    BasePlaceholder,
    BaseStub,
)
from app.core.config import Settings
from app.db.engine import EngineFactory
from app.events.base import EventConsumer, EventPublisher
from app.scope.base import DataScope, NullDataScope
from app.sharding.base import ShardingRouter
from app.tasks.base import BaseTask


class EmptyStub(BaseStub):
    """未实现占位样例。"""

    def no_feature(self) -> None:
        """无功能点的未实现。"""
        raise self._not_implemented()

    def with_feature(self) -> None:
        """带功能点的未实现。"""
        raise self._not_implemented("导出")


@pytest.mark.kiwi_id(26)
def test_placeholder_hierarchy() -> None:
    """占位层级与描述：空实现带占位标记。"""
    assert issubclass(BaseNullObject, BasePlaceholder)
    assert issubclass(BaseStub, BasePlaceholder)
    placeholder = NullDataScope()
    assert placeholder.placeholder is True
    assert "占位实现" in placeholder.describe()


@pytest.mark.kiwi_id(26)
def test_stub_uniform_error() -> None:
    """未实现占位：统一异常消息（含 / 不含功能点）。"""
    stub = EmptyStub()
    with pytest.raises(NotImplementedError) as no_feature:
        stub.no_feature()
    assert "尚未实现" in str(no_feature.value)
    with pytest.raises(NotImplementedError) as with_feature:
        stub.with_feature()
    assert "导出" in str(with_feature.value)


@pytest.mark.kiwi_id(26)
def test_capability_keys() -> None:
    """能力域标识：各契约 `key` 就位。"""
    assert BaseCapability().key == "capability"
    assert CacheRegion.key == "cache"
    assert DataScope.key == "data_scope"
    assert ShardingRouter.key == "sharding"
    assert AuditCapturer.key == "audit"
    assert BaseTask.key == "task"
    assert BaseEventWorker.key == "event"


@pytest.mark.kiwi_id(26)
def test_event_worker_contract() -> None:
    """事件工作单元：发布 / 消费共享父类。"""
    assert issubclass(EventPublisher, BaseEventWorker)
    assert issubclass(EventConsumer, BaseEventWorker)


@pytest.mark.kiwi_id(26)
async def test_async_resource_context() -> None:
    """异步资源：`async with` 进入并释放；`aclose` 幂等。"""
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    async with EngineFactory(settings) as factory:
        assert isinstance(factory, BaseAsyncResource)
        factory.create("platform")
    await factory.aclose()


@pytest.mark.kiwi_id(26)
async def test_app_lifespan_closes_resources() -> None:
    """应用生命周期：关闭时统一释放异步资源。"""
    from app.main import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        assert app.state.engine_factory is not None
