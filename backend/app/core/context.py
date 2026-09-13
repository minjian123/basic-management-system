"""core 层请求上下文占位：跨切面的上下文变量。

- 当前仅 `current_user_id` 供审计字段（created_by / updated_by）使用，占位默认 None。
- 认证 / 日志 / 多租户阶段接入后设置对应变量。
"""

from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
