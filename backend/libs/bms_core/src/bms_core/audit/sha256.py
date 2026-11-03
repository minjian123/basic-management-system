"""审计哈希链真实实现：SHA256 规范化链（06_01）。

- `Sha256HashChain`：实现 `BaseHashChain` 契约（`key/plugin_key = hash_chain`，`plugin_name = sha256`）。
- **规范化**：记录内容按键排序、紧凑分隔符（`,` / `:`）、非 ASCII 直出做 JSON 序列化——同值同字节，
  保证「写入算一次、校验再算一次」结果一致（跨 Python 版本同样稳定）。
- **链序**：`record_hash = SHA256(prev_hash + 规范化记录)`；`prev_hash` 为空取 `GENESIS_HASH`。
- 校验：逐条重算并比对 `record_hash` 与下一条的 `prev_hash`，返回首个断裂位置（从 0 起）。

> 本实现只做**纯计算**（无 IO、无加锁）：写入顺序与跨月衔接由消费组（`audit-chain` 有序组）与
> 平台侧链写入器保证，见 `platform.domains.log.services.writer`。
"""

from __future__ import annotations

import hashlib
import json

from bms_core.audit.hashchain import (
    GENESIS_HASH,
    BaseHashChain,
    ChainVerifyResult,
    HashChainEntry,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.serialization import normalize_collections

__all__ = ["Sha256HashChain", "canonical_json"]


def canonical_json(record: ConcurrentStableDict[str, object]) -> str:
    """规范化记录内容（键排序 + 紧凑分隔符 + 非 ASCII 直出）。

    Args:
        record: 记录内容（插入序集合类 / 普通映射均可）。

    Returns:
        str: 规范化 JSON 文本。
    """
    normalized = normalize_collections(record)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Sha256HashChain(BaseHashChain):
    """SHA256 审计链：单条计算 + 逐条校验。"""

    plugin_name: str = "sha256"

    def compute(self, prev_hash: str, record: ConcurrentStableDict[str, object]) -> str:
        """计算单条记录哈希（`SHA256(prev_hash + 规范化记录内容)`）。

        Args:
            prev_hash: 前一条记录哈希；空串按链头 `GENESIS_HASH` 处理。
            record: 记录内容。

        Returns:
            str: 64 位小写十六进制哈希。
        """
        prefix = prev_hash or GENESIS_HASH
        return hashlib.sha256(f"{prefix}{canonical_json(record)}".encode()).hexdigest()

    def verify(self, entries: ConcurrentStableList[HashChainEntry]) -> ChainVerifyResult:
        """逐条重算校验链完整性。

        Args:
            entries: 链上记录（按写入顺序）。

        Returns:
            ChainVerifyResult: 校验结果（断裂位置从 0 起；完整为 None）。
        """
        previous = GENESIS_HASH
        for index, entry in enumerate(entries):
            if entry.prev_hash != previous:
                return ChainVerifyResult(valid=False, broken_index=index)
            expected = self.compute(entry.prev_hash, entry.record)
            if entry.record_hash != expected:
                return ChainVerifyResult(valid=False, broken_index=index)
            previous = entry.record_hash
        return ChainVerifyResult(valid=True)
