"""冷化文件：NDJSON + gzip、清单与对象存取。"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.storage.base import BaseObjectStorage

__all__ = ["ColdFile", "build_cold_file", "delete_cold_file", "encode_value"]

MANIFEST_SUFFIX = ".manifest.json"
"""清单对象 key 后缀（与数据对象同前缀）。"""


def encode_value(value: object) -> object:
    """把源行列值归一为 JSON 可序列化形态（时间 / 金额）。

    Args:
        value: 源行列值。

    Returns:
        object: JSON 可序列化值。
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _normalize_row(values: ConcurrentStableDict[str, object]) -> ConcurrentStableDict[str, object]:
    """归一化一行（递归处理嵌套集合）。

    Args:
        values: 源行字段。

    Returns:
        ConcurrentStableDict[str, object]: JSON 可序列化字典。
    """
    normalized: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in values.items():
        if isinstance(value, dict):
            normalized[key] = _normalize_row(ConcurrentStableDict(cast("dict[str, object]", value)))
        elif isinstance(value, list):
            normalized[key] = [_normalize_value(item) for item in cast("list[object]", value)]
        else:
            normalized[key] = encode_value(value)
    return normalized


def _normalize_value(value: object) -> object:
    """归一化嵌套值。"""
    if isinstance(value, dict):
        return _normalize_row(ConcurrentStableDict(cast("dict[str, object]", value)))
    if isinstance(value, list):
        return [_normalize_value(item) for item in cast("list[object]", value)]
    return encode_value(value)


@dataclass(frozen=True)
class ColdFile(BaseValueObject):
    """冷化文件产物。"""

    data_key: str
    """数据对象 key。"""

    manifest_key: str
    """清单对象 key。"""

    row_count: int
    """行数。"""

    sha256: str
    """数据文件 SHA256。"""


def _manifest(
    *,
    source_table: str,
    tenant_key: str,
    log_id: int,
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    sha256: str,
) -> ConcurrentStableDict[str, object]:
    """构造清单内容（行数 / sha256 / 审计链头尾）。"""
    months: ConcurrentStableDict[str, ConcurrentStableDict[str, object]] = ConcurrentStableDict()
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        data = ConcurrentStableDict(cast("dict[str, object]", payload))
        month = row.get("source_month")
        key = str(month) if month else "plain"
        stats = months.get(key)
        prev_hash = data.get("prev_hash")
        record_hash = data.get("record_hash")
        if stats is None:
            stats = ConcurrentStableDict[str, object](
                {
                    "first_prev_hash": prev_hash,
                    "last_record_hash": record_hash,
                    "record_count": 0,
                }
            )
            months[key] = stats
        stats["last_record_hash"] = record_hash
        stats["record_count"] = int(str(stats["record_count"])) + 1
    return ConcurrentStableDict(
        {
            "version": 1,
            "source_table": source_table,
            "tenant_key": tenant_key,
            "archive_log_id": str(log_id),
            "row_count": len(rows),
            "sha256": sha256,
            "chain": months,
        }
    )


def _json_default(value: object) -> object:
    """JSON 兜底序列化（稳定集合类 → 普通容器）。

    Args:
        value: 不可直接序列化的对象。

    Returns:
        object: 普通容器或字符串。
    """
    items = getattr(value, "items", None)
    if callable(items):
        return dict(cast("dict[str, object]", value))
    return str(value)


def build_cold_file(
    *,
    prefix: str,
    tenant_key: str,
    source_table: str,
    log_id: int,
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> tuple[ColdFile, bytes, bytes]:
    """生成冷化数据与清单字节（NDJSON + gzip）。

    Args:
        prefix: 对象 key 前缀（`[archive].file_prefix`）。
        tenant_key: 租户键（`global` 或雪花 id 字符串）。
        source_table: 源逻辑表名。
        log_id: 归档批次主键。
        rows: 待冷化行（含 `payload` / `archived_at` / `source_month`）。

    Returns:
        tuple[ColdFile, bytes, bytes]: （产物元数据, 数据字节, 清单字节）。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    for row in rows:
        payload = row.get("payload")
        decoded = json.loads(str(payload)) if isinstance(payload, str) else payload
        record = ConcurrentStableDict(
            {
                "id": str(row.get("id")),
                "archived_at": encode_value(row.get("archived_at")),
                "payload": _normalize_value(decoded),
            }
        )
        lines.add(json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"), default=_json_default))
    raw = ("\n".join(str(line) for line in lines) + "\n").encode("utf-8")
    data_bytes = gzip.compress(raw, mtime=0)
    digest = hashlib.sha256(data_bytes).hexdigest()
    month = datetime.now().strftime("%Y%m")
    data_key = f"{prefix}/{tenant_key}/{source_table}/{month}/{log_id}.ndjson.gz"
    manifest_key = f"{data_key}{MANIFEST_SUFFIX}"
    manifest = _manifest(source_table=source_table, tenant_key=tenant_key, log_id=log_id, rows=rows, sha256=digest)
    manifest_bytes = json.dumps(
        dict(manifest), ensure_ascii=False, separators=(",", ":"), default=_json_default
    ).encode("utf-8")
    return (
        ColdFile(data_key=data_key, manifest_key=manifest_key, row_count=len(rows), sha256=digest),
        data_bytes,
        manifest_bytes,
    )


async def delete_cold_file(storage: BaseObjectStorage, file_key: str) -> None:
    """删除冷化数据与清单对象（幂等；清单缺失不阻断）。

    Args:
        storage: 对象存储。
        file_key: 数据对象 key。
    """
    await storage.delete(file_key)
    await storage.delete(f"{file_key}{MANIFEST_SUFFIX}")
