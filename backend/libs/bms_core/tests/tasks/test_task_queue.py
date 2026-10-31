"""任务队列护栏：载荷编解码 / 三态出队 / 先进先出 / 脏消息不抛错。"""

import json

import pytest
from redis.asyncio import Redis

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.models.platform.task import TASK_TRIGGER_MANUAL
from bms_core.tasks.queue import DEFAULT_QUEUE_KEY, TaskPopOutcome, TaskQueue, decode_spec, encode_spec
from bms_core.tasks.spec import TaskRunSpec

pytestmark = pytest.mark.kiwi_id(2371)


def _spec(**overrides: object) -> TaskRunSpec:
    """构造运行规格（可按需覆盖字段）。

    Args:
        **overrides: 字段覆盖。

    Returns:
        TaskRunSpec: 运行规格。
    """
    base: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "db_key": "platform_platform",
            "task_id": 11,
            "log_id": 22,
            "run_id": "run-abc",
            "code": "cleanup_orphan_parts",
            "handler": "bms_core.tasks.builtin:run_cleanup_orphan_parts",
            "args_json": '{"keep_days": 7}',
            "trigger_source": TASK_TRIGGER_MANUAL,
        }
    )
    base.update(overrides)
    return TaskRunSpec(**dict(base))  # pyright: ignore[reportArgumentType]


def test_encode_decode_roundtrip() -> None:
    """编码后解码字段完全保真（含参数原文与触发来源）。"""
    spec = _spec()
    decoded, error = decode_spec(encode_spec(spec))
    assert error is None
    assert decoded == spec


def test_decode_accepts_bytes_payload() -> None:
    """Redis 默认返回 bytes，解码路径兼容。"""
    decoded, error = decode_spec(encode_spec(_spec()).encode("utf-8"))
    assert error is None
    assert decoded is not None
    assert decoded.task_id == 11


def test_decode_rejects_non_json() -> None:
    """非 JSON 载荷 → 错误（不抛异常）。"""
    decoded, error = decode_spec("not-json")
    assert decoded is None
    assert error == "队列载荷不是合法 JSON"


def test_decode_rejects_non_object() -> None:
    """顶层非对象 → 错误。"""
    decoded, error = decode_spec("[1, 2]")
    assert decoded is None
    assert error == "队列载荷不是 JSON 对象"


@pytest.mark.parametrize("missing", ["db_key", "log_id", "run_id", "code", "handler", "task_id"])
def test_decode_rejects_missing_field(missing: str) -> None:
    """缺必填字段 → 错误（报出字段名）。"""
    payload = json.loads(encode_spec(_spec()))
    payload.pop(missing)
    decoded, error = decode_spec(json.dumps(payload))
    assert decoded is None
    assert error == f"队列载荷缺字段：{missing}"


@pytest.mark.parametrize("field", ["task_id", "log_id"])
def test_decode_rejects_non_integer_ids(field: str) -> None:
    """id 字段须为整数（字符串 id 会污染主键查询）。"""
    payload = json.loads(encode_spec(_spec()))
    payload[field] = "11"
    decoded, error = decode_spec(json.dumps(payload))
    assert decoded is None
    assert error is not None
    assert "整数" in error


def test_decode_normalizes_unknown_trigger_source() -> None:
    """未知触发来源回落 `schedule`（不因脏值丢弃整条任务）。"""
    payload = json.loads(encode_spec(_spec()))
    payload["trigger_source"] = "unknown"
    decoded, error = decode_spec(json.dumps(payload))
    assert error is None
    assert decoded is not None
    assert decoded.trigger_source == "schedule"


def test_decode_drops_non_string_args() -> None:
    """参数原文非字符串时按无参处理（不抛错）。"""
    payload = json.loads(encode_spec(_spec()))
    payload["args_json"] = {"nested": True}
    decoded, error = decode_spec(json.dumps(payload))
    assert error is None
    assert decoded is not None
    assert decoded.args_json is None


async def test_push_pop_fifo(fake_redis: Redis) -> None:
    """入队出队先进先出，规格保真。"""
    queue = TaskQueue(client=fake_redis)
    assert queue.key == DEFAULT_QUEUE_KEY
    await queue.push(_spec(task_id=1))
    await queue.push(_spec(task_id=2))
    first = await queue.pop()
    second = await queue.pop()
    assert first.spec is not None and first.spec.task_id == 1
    assert second.spec is not None and second.spec.task_id == 2


async def test_pop_reports_timeout_when_empty(fake_redis: Redis) -> None:
    """空队列 → 超时三态（非错误）。"""
    outcome = await TaskQueue(client=fake_redis, key="custom").pop(timeout=1)
    assert outcome.spec is None
    assert outcome.error is None
    assert outcome.timed_out is True


async def test_pop_reports_dirty_message(fake_redis: Redis) -> None:
    """脏消息 → 错误三态（执行器据此记日志并丢弃）。"""
    queue = TaskQueue(client=fake_redis)
    await fake_redis.lpush(queue.key, "broken")
    outcome = await queue.pop(timeout=1)
    assert outcome.spec is None
    assert outcome.error == "队列载荷不是合法 JSON"
    assert outcome.timed_out is False


def test_pop_outcome_defaults() -> None:
    """无参构造即「超时」态（值对象语义）。"""
    outcome = TaskPopOutcome()
    assert outcome.timed_out is True


async def test_queue_propagates_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入客户端且共享客户端不可用时抛 `10012`（fail-closed）。"""

    def _boom() -> Redis:
        raise RedisUnavailableError("redis down")

    monkeypatch.setattr("bms_core.tasks.queue.shared_async_client", _boom)
    queue = TaskQueue()
    with pytest.raises(RedisUnavailableError):
        await queue.push(_spec())
