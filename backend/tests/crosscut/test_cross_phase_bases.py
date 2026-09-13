"""跨阶段基座契约骨架测试（Kiwi 24）。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.audit.base import AuditCapturer, FieldChange
from app.cache.base import CacheRegion, build_cache_key
from app.events.base import EventConsumer, EventEnvelope, EventPublisher
from app.models.base import Base, BaseModel
from app.models.system import SysTask, SysTaskLog
from app.repositories.demo_repository import DemoRepository
from app.scope.base import DataScope, NullDataScope
from app.sharding.base import NullShardingRouter, ShardBinding, ShardingRouter
from app.tasks.base import BaseTask


class StubRegion(CacheRegion):
    """测试缓存 Region 占位实现。"""

    def __init__(self, version: int = 1) -> None:
        self._store: dict[str, object] = {}
        self._version = version

    @property
    def domain(self) -> str:
        """业务域简称。"""
        return "user"

    def get(self, key: str) -> object | None:
        """读缓存。"""
        return self._store.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存。"""
        self._store[key] = value

    def delete(self, key: str) -> bool:
        """删缓存。"""
        return self._store.pop(key, None) is not None

    def get_global_version(self) -> int:
        """取全局版本号。"""
        return self._version


class StubRouter(ShardingRouter):
    """测试分片路由：逻辑表追加年月后缀。"""

    def resolve(self, logical_table: str, *, shard_key: object | None = None) -> ShardBinding:
        """解析物理表。"""
        return ShardBinding(db_key="shard_0", physical_table=f"{logical_table}_202609")


class RoutedRepository(DemoRepository):
    """测试仓储：暴露数据范围 / 分片钩子。"""

    def use_scope(self, scope: DataScope | None) -> None:
        """注入数据范围。"""
        self._apply_data_scope(scope)

    def current_scope(self) -> DataScope | None:
        """取当前数据范围。"""
        return self._data_scope

    def use_router(self, router: ShardingRouter | None) -> None:
        """注入分片路由。"""
        self._sharding_router = router

    def physical(self, logical_table: str) -> str:
        """解析物理表名。"""
        return self._resolve_shard(logical_table)


class StubPublisher(EventPublisher):
    """测试事件发布器。"""

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return "user_created"

    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def publish(self, event: EventEnvelope) -> None:
        """发布事件。"""
        self.events.append(event)

    def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布。"""
        self.events.append(event)


class StubConsumer(EventConsumer):
    """测试事件消费者。"""

    def __init__(self) -> None:
        self.received: list[EventEnvelope] = []

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return "user_created"

    def consume(self, event: EventEnvelope) -> None:
        """消费事件。"""
        self.received.append(event)


class StubTask(BaseTask):
    """测试任务。"""

    @property
    def name(self) -> str:
        """任务名。"""
        return "demo_task"

    def run(self, *args: object, **kwargs: object) -> object:
        """任务执行体。"""
        return (args, kwargs)


class StubCapturer(AuditCapturer):
    """测试审计捕获器。"""

    def is_audited(self, table: str) -> bool:
        """是否审计表。"""
        return table == "demo"

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: list[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """生成审计事件。"""
        return EventEnvelope(
            event_type="audit_changed",
            payload={"table": table, "model_id": model_id, "actor": actor, "changes": [c.to_dict() for c in changes]},
        )


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """SQLite 临时库（建表）。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'crosscut.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.mark.kiwi_id(24)
def test_cache_region() -> None:
    """缓存基座：key 规范 / 收写 / 版本陈旧判定。"""
    region = StubRegion(version=5)
    assert build_cache_key(tenant="t1", domain="user", business_key="42") == "bms:t1:user:42"
    assert build_cache_key(tenant=None, domain="user", business_key="42") == "bms:global:user:42"
    assert region.build_key("42", tenant="t1") == "bms:t1:user:42"
    assert region.default_ttl == 300
    assert region.get("k") is None
    region.set("k", "v")
    assert region.get("k") == "v"
    assert region.is_stale("k", 5) is False
    assert region.is_stale("k", 4) is True
    assert region.delete("k") is True
    assert region.delete("k") is False


@pytest.mark.kiwi_id(24)
def test_data_scope_and_repository_hook() -> None:
    """数据范围：占位规则 + 仓储钩子挂载。"""
    scope = NullDataScope()
    assert scope.read_predicate() is None
    assert scope.allow_write({"name": "x"}) is True
    repo = RoutedRepository()
    assert repo.current_scope() is None
    repo.use_scope(scope)
    assert repo.current_scope() is scope


@pytest.mark.kiwi_id(24)
def test_sharding_router_and_repository_hook() -> None:
    """分片路由：空路由 / 注入路由。"""
    assert NullShardingRouter().resolve("demo") == ShardBinding(db_key="default", physical_table="demo")
    repo = RoutedRepository()
    assert repo.physical("demo") == "demo"
    repo.use_router(StubRouter())
    assert repo.physical("demo") == "demo_202609"
    repo.use_router(None)
    assert repo.physical("demo") == "demo"


@pytest.mark.kiwi_id(24)
def test_event_base() -> None:
    """事件基座：信封字段 / 发布 / 消费契约。"""
    event = EventEnvelope(event_type="user_created", payload={"id": 1}, trace_id="t1")
    assert event.to_dict() == {"event_type": "user_created", "payload": {"id": 1}, "trace_id": "t1"}
    publisher = StubPublisher()
    publisher.publish(event)
    publisher.publish_transactional(event)
    assert len(publisher.events) == 2
    consumer = StubConsumer()
    assert consumer.event_type == "user_created"
    consumer.consume(event)
    assert consumer.received == [event]


@pytest.mark.kiwi_id(24)
def test_task_base_and_models(engine: Engine) -> None:
    """任务基座：契约 + 模型骨架建表与写入。"""
    task = StubTask()
    assert task.name == "demo_task"
    assert task.queue == "default"
    assert task.run(1, key="v") == ((1,), {"key": "v"})
    assert {"sys_task", "sys_task_log"} <= set(Base.metadata.tables)
    with Session(engine) as session:
        sys_task = SysTask(name="demo_task", handler="app.tasks.demo:DemoTask", cron=None, enabled=True)
        session.add(sys_task)
        session.commit()
        log = SysTaskLog(task_id=sys_task.id, status="success", result="ok")
        session.add(log)
        session.commit()
        assert isinstance(sys_task, BaseModel)
        assert log.id > 0


@pytest.mark.kiwi_id(24)
def test_audit_base() -> None:
    """审计基座：字段变更 / 捕获契约。"""
    change = FieldChange(field="name", old="a", new="b")
    assert change.to_dict() == {"field": "name", "old": "a", "new": "b"}
    capturer = StubCapturer()
    assert capturer.is_audited("demo") is True
    assert capturer.is_audited("other") is False
    event = capturer.capture(table="demo", model_id=1, changes=[change], actor=9)
    assert event.event_type == "audit_changed"
    assert event.payload["changes"] == [{"field": "name", "old": "a", "new": "b"}]
