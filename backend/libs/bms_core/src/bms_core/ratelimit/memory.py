"""限流能力域：进程内固定窗口限流实现（Redis 不可用时的降级 / 测试）。

- `MemoryRateLimiter`（插件名 `memory`）：进程内字典 + 窗口到期时间，单副本口径。
- 与 `RedisRateLimiter` 同契约：`check` 返回决策，`require` 超限抛 `RateLimitError`（10005 / 429）。
"""

from __future__ import annotations

import time

from bms_core.ratelimit.base import BaseRateLimiter, RateLimitDecision, RateLimitRule

__all__ = ["MemoryRateLimiter"]


class MemoryRateLimiter(BaseRateLimiter):
    """进程内固定窗口限流（单副本口径）。"""

    def __init__(self) -> None:
        """初始化（空计数）。"""
        self._windows: dict[str, tuple[int, float]] = {}

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """判定配额（固定窗口计数）。

        Args:
            key: 限流 key。
            rule: 限流规则（次数 / 窗口）。

        Returns:
            RateLimitDecision: 判定结果。
        """
        now = time.monotonic()
        window = max(1, rule.window)
        count, expires_at = self._windows.get(key, (0, now + window))
        if expires_at <= now:
            count, expires_at = 0, now + window
        count += 1
        self._windows[key] = (count, expires_at)
        reset_after = max(0, int(expires_at - now))
        return RateLimitDecision(
            allowed=count <= rule.limit,
            limit=rule.limit,
            remaining=max(0, rule.limit - count),
            reset_after=reset_after,
        )

    def clear(self) -> None:
        """清空计数（测试 / 调试用）。"""
        self._windows.clear()

    async def reset(self, key: str) -> None:
        """重置配额计数（成功路径清零）。

        Args:
            key: 限流 key。
        """
        self._windows.pop(key, None)
