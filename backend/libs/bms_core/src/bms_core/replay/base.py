"""防重放能力域：开放接口入站防重放编排契约（nonce 去重随性能与安全 / 开放接口阶段回补）。

- `REPLAY_WINDOW`：服务器时间窗口（秒，架构「对外 API」节 ±5 分钟）；nonce TTL 与之对齐。
- `ReplayReason` / `ReplayDecision`：拒绝原因（`expired` 超窗 / `bad_signature` 签名不符 / `replayed` 重复 nonce）
  与判定结果。
- `BaseReplayGuard`：能力域中间层契约（`key = "replay_guard"`）——`verify` 为**模板方法**，
  固定按「时间窗 → HMAC 签名 → nonce 去重」编排（短路）；`require` 供接口层一行接入（失败抛 `AuthError`）。
  `claim_nonce` 恒定 True（不连 Redis＝不拦截重复 nonce）。
- `get_replay_guard`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

签名口径（开放接口对接契约，串料见 `SignatureCodec`）：请求头
`X-Timestamp`（Unix 秒）+ `X-Nonce`（随机唯一串）+ `X-Signature`（HMAC-SHA256 hex 小写）；
密钥取调用方凭证（开放接口为 `sys_client` secret），基座不读库、不落日志。
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.core.security import SIGNATURE_HEADER, SignatureCodec

__all__ = [
    "NONCE_HEADER",
    "REPLAY_WINDOW",
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "BaseReplayGuard",
    "ReplayDecision",
    "ReplayReason",
    "get_replay_guard",
]

TIMESTAMP_HEADER = "X-Timestamp"
"""请求时间戳头（Unix 秒；与服务器时间窗口比对）。"""

NONCE_HEADER = "X-Nonce"
"""请求随机串头（唯一随机串；窗口内去重）。"""

REPLAY_WINDOW = 300
"""时间窗（秒）：服务器时间 ±5 分钟，超窗拒绝；nonce 去重 TTL 与之对齐。"""


class ReplayReason(StrEnum):
    """防重放拒绝原因。"""

    EXPIRED = "expired"
    """时间戳超窗（服务器时间 ±`REPLAY_WINDOW` 之外）。"""

    BAD_SIGNATURE = "bad_signature"
    """签名不符（串料重建后 HMAC 比对失败）。"""

    REPLAYED = "replayed"
    """nonce 重复（窗口内已被占用）。"""


@dataclass(frozen=True)
class ReplayDecision(BaseObject):
    """防重放判定结果。"""

    allowed: bool
    """是否放行。"""

    reason: ReplayReason | None = None
    """拒绝原因；放行为 None。"""


class BaseReplayGuard(BasePluggable, ABC):
    """防重放契约：时间窗 + 签名 + nonce 去重的固定编排。"""

    key: str = "replay_guard"
    plugin_key: str = "replay_guard"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, codec: SignatureCodec | None = None) -> None:
        """初始化防重放守卫。

        Args:
            codec: 签名原语（缺省使用标准库 HMAC-SHA256 实现；可注入测试替身）。
        """
        self._codec = codec or SignatureCodec()

    async def verify(
        self,
        *,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        signature: str,
        secret: str,
        body: str = "",
        window: int = REPLAY_WINDOW,
        now: int | None = None,
    ) -> ReplayDecision:
        """校验请求（短路顺序：时间窗 → 签名 → nonce 去重）。

        Args:
            method: HTTP 方法。
            path: 请求路径（不含查询串）。
            timestamp: 请求时间戳（Unix 秒）。
            nonce: 随机唯一串。
            signature: 请求签名（`X-Signature`）。
            secret: 签名密钥（调用方凭证）。
            body: 原始请求体（无体传空串）。
            window: 时间窗（秒）。
            now: 当前服务器时间（Unix 秒）；缺省取系统时间（供测试注入）。

        Returns:
            ReplayDecision: 判定结果（不抛错）。
        """
        current = int(time.time()) if now is None else now
        if abs(current - timestamp) > window:
            return ReplayDecision(allowed=False, reason=ReplayReason.EXPIRED)
        verified = self._codec.verify(
            secret=secret,
            signature=signature,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        if not verified:
            return ReplayDecision(allowed=False, reason=ReplayReason.BAD_SIGNATURE)
        if not await self.claim_nonce(nonce, ttl=window):
            return ReplayDecision(allowed=False, reason=ReplayReason.REPLAYED)
        return ReplayDecision(allowed=True)

    @abstractmethod
    async def claim_nonce(self, nonce: str, *, ttl: int = REPLAY_WINDOW) -> bool:
        """占用 nonce（窗口内去重）。

        Args:
            nonce: 随机唯一串。
            ttl: 占用有效期（秒），与时间窗对齐。

        Returns:
            bool: 首次占用为 True；窗口内重复为 False。
        """

    async def require(
        self,
        *,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        signature: str,
        secret: str,
        body: str = "",
        window: int = REPLAY_WINDOW,
        now: int | None = None,
    ) -> ReplayDecision:
        """强制校验（接口层一行接入）。

        Args:
            method: HTTP 方法。
            path: 请求路径（不含查询串）。
            timestamp: 请求时间戳（Unix 秒）。
            nonce: 随机唯一串。
            signature: 请求签名（`X-Signature`）。
            secret: 签名密钥（调用方凭证）。
            body: 原始请求体（无体传空串）。
            window: 时间窗（秒）。
            now: 当前服务器时间（Unix 秒）；缺省取系统时间。

        Returns:
            ReplayDecision: 判定结果（放行）。

        Raises:
            AuthError: 校验失败（超窗 / 签名不符 / nonce 重复；20001 / 401）。
        """
        decision = await self.verify(
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            secret=secret,
            body=body,
            window=window,
            now=now,
        )
        if not decision.allowed:
            raise AuthError(f"防重放校验失败：{decision.reason}")
        return decision


def get_replay_guard(request: Request) -> BaseReplayGuard:
    """取应用级防重放守卫（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseReplayGuard: 应用装配的防重放守卫实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseReplayGuard",
        resolve_plugin(
            "replay_guard",
            settings.replay_guard.provider,
            expected_version=BaseReplayGuard.contract_version,
        ),
    )
