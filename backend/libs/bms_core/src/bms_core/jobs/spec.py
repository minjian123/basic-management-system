"""作业数据契约：提交规格 / 只读快照 / 负载编解码 / 时间与截断工具（值对象，不含 IO）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import JobPayloadInvalidError
from bms_core.core.roots import BaseValueObject
from bms_core.core.serialization import normalize_collections
from bms_core.models.base import to_stable_value
from bms_core.models.job import DEFAULT_PAYLOAD_VERSION

__all__ = [
    "JobSnapshot",
    "JobSubmission",
    "JobTypeSpec",
    "dump_payload",
    "now_utc",
    "parse_job_payload",
    "truncate_text",
]


def now_utc() -> datetime:
    """当前 UTC 时间（naive，与表列同形）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def parse_job_payload(raw: str | None) -> ConcurrentStableDict[str, object]:
    """解析作业负载（JSON 对象）。

    Args:
        raw: 负载原文（`sys_job.payload`）。

    Returns:
        ConcurrentStableDict[str, object]: 解析结果（插入序集合类）。

    Raises:
        JobPayloadInvalidError: 空、非 JSON、或顶层不是对象（`71005`）。
    """
    if raw is None or not raw.strip():
        return ConcurrentStableDict[str, object]()
    try:
        loaded: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JobPayloadInvalidError(f"作业负载不是合法 JSON：{exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise JobPayloadInvalidError("作业负载顶层须为 JSON 对象")
    mapping = cast("dict[object, object]", loaded)
    return ConcurrentStableDict({str(key): to_stable_value(item) for key, item in mapping.items()})


def dump_payload(payload: ConcurrentStableDict[str, object]) -> str:
    """序列化作业负载 / 结果（稳定键序、保留中文）。

    Args:
        payload: 负载或结果对象。

    Returns:
        str: JSON 文本。
    """
    return json.dumps(normalize_collections(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def truncate_text(text: str | None, limit: int) -> str | None:
    """按上限截断文本（保留尾部省略号）。

    Args:
        text: 文本。
        limit: 上限字符数。

    Returns:
        str | None: 截断结果；入参为 None 返回 None。
    """
    if text is None:
        return None
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


@dataclass(frozen=True)
class JobSubmission(BaseValueObject):
    """作业提交规格（`JobRunner.submit` 的入参）。"""

    job_type: str
    """作业类型（必须属于本服务已注册 handler）。"""

    payload: ConcurrentStableDict[str, object] = field(default_factory=ConcurrentStableDict[str, object])
    """负载（JSON 对象）。"""

    priority: int = 0
    """租户内优先级（大者先）。"""

    idempotency_key: str | None = None
    """提交幂等键（同类型内唯一；None 不去重）。"""

    max_attempts: int | None = None
    """最大执行次数（None 取类型声明 / 默认）。"""

    payload_version: str = DEFAULT_PAYLOAD_VERSION
    """负载版本。"""


@dataclass(frozen=True)
class JobTypeSpec(BaseValueObject):
    """作业类型声明要素（服务侧持有一份，平台侧落 `sys_job_type`）。"""

    job_type: str
    """作业类型（全局唯一）。"""

    service_key: str
    """提供方服务键（执行者所在服务）。"""

    domain_key: str
    """提供方业务域。"""

    handler: str = ""
    """执行者点分路径（`module:attr`；代码侧注册时可为空）。"""

    description: str = ""
    """说明。"""

    timeout_seconds: int = 1800
    """单次执行超时（提示 / 监控）。"""

    max_attempts: int = 3
    """最大执行次数。"""

    backoff_seconds: int = 30
    """退避基数（秒）。"""

    concurrency: int = 4
    """单租户该类型并发上限。"""

    payload_version: str = DEFAULT_PAYLOAD_VERSION
    """负载版本。"""


@dataclass(frozen=True)
class JobSnapshot(BaseValueObject):
    """作业只读快照（抢占后交给消费者执行，避免跨会话持有 ORM 实体）。"""

    id: int
    job_type: str
    service_key: str
    domain_key: str
    status: str
    payload: ConcurrentStableDict[str, object]
    payload_version: str
    priority: int = 0
    tenant_id: int | None = None
    progress_done: int = 0
    progress_total: int | None = None
    attempts: int = 0
    max_attempts: int = 1
    cancel_requested: bool = False
    error: str | None = None
    idempotency_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    db_key: str = ""
    """作业所在库键（执行体取会话与心跳用）。"""

    lease_owner: str = ""
    """当前租约持有者（worker 实例标识）。"""
