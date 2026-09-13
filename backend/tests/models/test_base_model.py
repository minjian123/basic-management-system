"""ORM 模型基类测试（Kiwi 19）：SQLite 临时库验证字段 / 审计 / 软删除 / 乐观锁。"""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, String, UniqueConstraint, create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from app.core.base import BaseObject
from app.core.context import current_user_id
from app.core.id import SnowflakeGenerator, configure_id_generator, generate_id, initial_worker_id
from app.models.base import Base, BaseModel
from app.models.demo import Demo


class Widget(BaseModel):
    """测试模型：带 `(name, deleted_at)` 复合唯一。"""

    __tablename__ = "widget"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_widget_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(16))


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.mark.kiwi_id(19)
def test_fields_and_snowflake_id(session: Session) -> None:
    """字段齐备；id 为雪花值；审计 / 软删除 / 版本默认正确；to_dict 排除内部状态。"""
    widget = Widget(name="a")
    session.add(widget)
    session.commit()
    assert widget.id > 0
    assert widget.created_at is not None and widget.updated_at is not None
    assert widget.created_by is None and widget.updated_by is None
    assert widget.deleted_at is None and widget.version == 1
    data = widget.to_dict()
    assert {"id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at", "version"} <= set(data)
    assert "_sa_instance_state" not in data


@pytest.mark.kiwi_id(19)
def test_audit_context_and_update(session: Session) -> None:
    """审计从上下文填充；更新刷新 updated_at / updated_by，保留 created_at。"""
    token = current_user_id.set(7)
    try:
        widget = Widget(name="a")
        session.add(widget)
        session.commit()
    finally:
        current_user_id.reset(token)
    assert (widget.created_by, widget.updated_by) == (7, 7)
    created = widget.created_at

    token = current_user_id.set(9)
    try:
        widget.name = "b"
        session.commit()
    finally:
        current_user_id.reset(token)
    assert widget.created_at == created
    assert widget.updated_at >= created
    assert widget.updated_by == 9


@pytest.mark.kiwi_id(19)
def test_optimistic_lock_and_stale(engine: Engine) -> None:
    """version 自动 +1；并发旧版本更新抛 StaleDataError。"""
    with Session(engine) as s1, Session(engine) as s2:
        widget = Widget(name="x")
        s1.add(widget)
        s1.commit()
        widget_id = widget.id

        first = s1.get(Widget, widget_id)
        stale = s2.get(Widget, widget_id)
        assert first is not None and stale is not None
        first.name = "a1"
        s1.commit()
        assert first.version == 2

        stale.name = "b1"
        with pytest.raises(StaleDataError):
            s2.commit()


@pytest.mark.kiwi_id(19)
def test_soft_delete_frees_unique(session: Session) -> None:
    """软删除写 deleted_at 释放复合唯一键；删除行同键可共存。"""
    first = Widget(name="a")
    session.add(first)
    session.commit()
    first.deleted_at = datetime(2026, 1, 1)
    session.commit()

    second = Widget(name="a")
    session.add(second)
    session.commit()
    assert second.id != first.id

    third = Widget(name="a", deleted_at=datetime(2026, 1, 2))
    session.add(third)
    session.commit()
    assert third.id not in {first.id, second.id}


@pytest.mark.kiwi_id(19)
def test_snowflake_unique_and_monotonic() -> None:
    """雪花 ID 唯一且单调递增。"""
    generator = SnowflakeGenerator(worker_id=1)
    ids = [generator.next_id() for _ in range(1000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


@pytest.mark.kiwi_id(19)
def test_snowflake_seq_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """同毫秒序列用尽后等待下一毫秒，ID 不重复。"""
    generator = SnowflakeGenerator(worker_id=0)
    calls = {"n": 0}

    def fake_time() -> float:
        calls["n"] += 1
        return 2_000_000_000.0 if calls["n"] <= 4097 else 2_000_000_000.001

    monkeypatch.setattr("app.core.id.time.time", fake_time)
    ids = [generator.next_id() for _ in range(4097)]
    assert len(set(ids)) == 4097


@pytest.mark.kiwi_id(19)
def test_snowflake_clock_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    """小幅回拨等待追平；大幅回拨抛错。"""
    small = iter([2_000_000_000.0, 1_999_999_999.996])
    monkeypatch.setattr("app.core.id.time.time", lambda: next(small))
    generator = SnowflakeGenerator(worker_id=0)
    generator.next_id()
    assert generator.next_id() > 0

    large = iter([2_000_000_000.0, 1_999_000_000.0])
    monkeypatch.setattr("app.core.id.time.time", lambda: next(large))
    generator2 = SnowflakeGenerator(worker_id=0)
    generator2.next_id()
    with pytest.raises(RuntimeError):
        generator2.next_id()


@pytest.mark.kiwi_id(19)
def test_configure_and_invalid_worker() -> None:
    """配置生成器生效；边界 WorkerId 合法、越界报错。"""
    configure_id_generator(2)
    assert generate_id() > 0
    assert SnowflakeGenerator(worker_id=1023).next_id() > 0
    with pytest.raises(ValueError):
        SnowflakeGenerator(worker_id=9999)


@pytest.mark.kiwi_id(19)
def test_initial_worker_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """WorkerId 从环境变量解析，非法 / 越界回退 0。"""
    read_env = initial_worker_id
    monkeypatch.delenv("BMS_WORKER_ID", raising=False)
    assert read_env() == 0
    monkeypatch.setenv("BMS_WORKER_ID", "abc")
    assert read_env() == 0
    monkeypatch.setenv("BMS_WORKER_ID", "5")
    assert read_env() == 5
    monkeypatch.setenv("BMS_WORKER_ID", "99999")
    assert read_env() == 0


@pytest.mark.kiwi_id(19)
def test_demo_model_and_generator_inherit_base_object() -> None:
    """demo 示例模型继承 BaseModel；雪花生成器纳入 L0 继承体系。"""
    assert issubclass(Demo, BaseModel)
    assert issubclass(SnowflakeGenerator, BaseObject)
