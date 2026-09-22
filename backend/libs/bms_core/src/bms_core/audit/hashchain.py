"""审计哈希链能力域：链计算与校验契约（真实 SHA256 链计算随审计哈希链阶段回补）。

- `GENESIS_HASH`：首月链头约定初始值（64 位零 hex）；`HASH_ALGORITHM`：哈希算法（`sha256`）。
- `HashChainEntry` / `ChainVerifyResult`：链上记录与校验结果数据契约（frozen）。
- `BaseHashChain`：能力域中间层契约（`key = "hash_chain"`）——同步 `compute`（prev + 记录 → 哈希）/ `verify`（链校验）。
- `get_hash_chain`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：`record_hash = SHA256(prev_hash + 规范化记录内容)`、分片表内成链、跨月表首尾衔接（归实现）；
本域与既有 `AuditCapturer`（`app/audit/base.py`）协作——捕获归 AuditCapturer、链计算与校验归本域。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "GENESIS_HASH",
    "HASH_ALGORITHM",
    "BaseHashChain",
    "ChainVerifyResult",
    "HashChainEntry",
    "get_hash_chain",
]

GENESIS_HASH = "0" * 64
"""首月链头约定初始值（64 位零 hex；首条记录 `prev_hash`）。"""

HASH_ALGORITHM = "sha256"
"""哈希算法。"""


@dataclass(frozen=True)
class HashChainEntry(BaseObject):
    """链上一条记录。"""

    prev_hash: str
    """前一条记录哈希（链头取 `GENESIS_HASH` 或上月末条）。"""

    record: Mapping[str, object]
    """规范化记录内容。"""

    record_hash: str
    """本条记录哈希。"""


@dataclass(frozen=True)
class ChainVerifyResult(BaseObject):
    """链校验结果。"""

    valid: bool
    """链是否完整。"""

    broken_index: int | None = None
    """断裂位置（从 0 起的记录序号）；完整为 None。"""


class BaseHashChain(BasePluggable, ABC):
    """哈希链契约：单条计算 + 链校验。"""

    key: str = "hash_chain"
    plugin_key: str = "hash_chain"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def compute(self, prev_hash: str, record: Mapping[str, object]) -> str:
        """计算单条记录哈希（`SHA256(prev_hash + 规范化记录内容)`）。

        Args:
            prev_hash: 前一条记录哈希。
            record: 记录内容。

        Returns:
            str: 本条记录哈希。
        """

    @abstractmethod
    def verify(self, entries: Sequence[HashChainEntry]) -> ChainVerifyResult:
        """逐条重算校验链完整性。

        Args:
            entries: 链上记录序列（分片内成链）。

        Returns:
            ChainVerifyResult: 校验结果（含断裂位置）。
        """


def get_hash_chain(request: Request) -> BaseHashChain:
    """取应用级哈希链（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseHashChain: 应用装配的哈希链实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseHashChain",
        resolve_plugin(
            "hash_chain",
            settings.hash_chain.provider,
            expected_version=BaseHashChain.contract_version,
        ),
    )
