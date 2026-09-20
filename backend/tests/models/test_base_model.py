"""ORM 模型基类测试（Kiwi 19）：SQLite 临时库验证字段 / 审计 / 软删除 / 乐观锁。"""

import types
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, String, UniqueConstraint, create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from app.core.base import BaseObject
from app.core.context import current_user_id
from app.core.id import SnowflakeGenerator, id_generator
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


@pytest.mark.kiwi_id(30)
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


@pytest.mark.kiwi_id(30)
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


@pytest.mark.kiwi_id(30)
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


@pytest.mark.kiwi_id(30)
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


@pytest.mark.kiwi_id(30)
def test_snowflake_unique_and_monotonic() -> None:
    """雪花 ID 唯一且单调递增。"""
    generator = SnowflakeGenerator(worker_id=1)
    ids = [generator.next_id() for _ in range(1000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def _fake_time_module(values: list[float]) -> types.SimpleNamespace:
    """构造只暴露 `time.time()` 的假 time 模块。

    直接 patch 全局 `time.time`（`app.core.id.time` 即 time 模块本身）会影响进程内所有调用方
    ——pytest 插件（Kiwi 结果导入）、IDE 侧 shim 等都会读到假时钟，序列用尽即 `StopIteration`。
    故这里替换 `app.core.id.time` 对象，并让序列用尽后回落到最后一个值：既保留原用例的
    时钟序列语义，又不干扰外部调用方。
    """
    seq = iter(values)
    fallback = values[-1]
    return types.SimpleNamespace(time=lambda: next(seq, fallback))


@pytest.mark.kiwi_id(30)
def test_snowflake_seq_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """同毫秒序列用尽后等待下一毫秒，ID 不重复。"""
    generator = SnowflakeGenerator(worker_id=0)
    monkeypatch.setattr("app.core.id.time", _fake_time_module([2_000_000_000.0] * 4097 + [2_000_000_000.001]))
    ids = [generator.next_id() for _ in range(4097)]
    assert len(set(ids)) == 4097


@pytest.mark.kiwi_id(30)
def test_snowflake_clock_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    """小幅回拨等待追平；大幅回拨抛错。"""
    monkeypatch.setattr(
        "app.core.id.time",
        _fake_time_module([2_000_000_000.0, 1_999_999_999.996, 2_000_000_000.0]),
    )
    generator = SnowflakeGenerator(worker_id=0)
    generator.next_id()
    assert generator.next_id() > 0

    monkeypatch.setattr(
        "app.core.id.time",
        _fake_time_module([2_000_000_000.0, 1_999_000_000.0, 2_000_000_000.0]),
    )
    generator2 = SnowflakeGenerator(worker_id=0)
    generator2.next_id()
    with pytest.raises(RuntimeError):
        generator2.next_id()


@pytest.mark.kiwi_id(30)
def test_configure_and_invalid_worker() -> None:
    """配置生成器生效；边界 WorkerId 合法、越界报错。"""
    id_generator.reconfigure(2)
    assert id_generator.next_id() > 0
    assert SnowflakeGenerator(worker_id=1023).next_id() > 0
    with pytest.raises(ValueError):
        SnowflakeGenerator(worker_id=9999)


@pytest.mark.kiwi_id(30)
def test_default_worker_id_is_zero() -> None:
    """导入期默认 WorkerId 为 0（旧名 `BMS_WORKER_ID` 兜底已移除，部署经 `BMS_APP__WORKER_ID` 注入）。"""
    worker_id = (SnowflakeGenerator().next_id() >> 12) & 1023
    assert worker_id == 0


@pytest.mark.kiwi_id(30)
def test_demo_model_and_generator_inherit_base_object() -> None:
    """demo 示例模型继承 BaseModel；雪花生成器纳入 L0 继承体系。"""
    assert issubclass(Demo, BaseModel)
    assert issubclass(SnowflakeGenerator, BaseObject)


@pytest.mark.kiwi_id(30)
def test_soft_delete_and_restore(session: Session) -> None:
    """软删除辅助：`soft_delete` 置 deleted_at、`restore` 清空。"""
    widget = Widget(name="a")
    session.add(widget)
    session.commit()
    assert widget.deleted_at is None

    widget.soft_delete()
    session.commit()
    assert widget.deleted_at is not None

    widget.restore()
    session.commit()
    assert widget.deleted_at is None
