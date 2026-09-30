"""密码策略能力域：真实实现（复杂度 / 有效期 / 历史重复）。

- `DefaultPasswordPolicy`（插件名 `default`）：按租户读 `sys_config`（经 `BaseConfigSource`）判定——
  - `validate`：长度（`password.min_length` / `password.max_length`）/ 大小写（`require_upper` / `require_lower`）/
    数字（`require_digit`）/ 符号（`require_symbol`）/ 不得含用户名（`forbid_username`）；返回违规原因码元组。
  - `expired`：`password.max_age_days`（缺省 90）驱动，`pwd_changed_at` 早于阈值即过期。
  - `reused`：对历史哈希逐条经 `BasePasswordHasher.verify` 比对（常量时间），命中即重复。
  - `history_count`：`password.history_count`（缺省 5），供调用方决定历史保留 / 比对条数。
- 容错解析：配置值缺失 / 非法回落代码默认（`true/false/1/0/yes/no/on/off`、整数串），不抛错。
- 装配：`DefaultPasswordPolicyFactory` 注入 `config_source` 与 `password_hasher`；`config.toml` 置
  `[password_policy].provider = "default"` 即真实启用，空串仍回落 `NullPasswordPolicy`（恒定通过）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.password.base import (
    PASSWORD_HISTORY_COUNT,
    BasePasswordPolicy,
)
from bms_core.security.base import BasePasswordHasher

__all__ = [
    "ACCOUNT_INACTIVE_LOCK_DAYS",
    "DEFAULT_MAX_AGE_DAYS",
    "DEFAULT_MAX_LENGTH",
    "DEFAULT_MIN_LENGTH",
    "PASSWORD_HISTORY_COUNT_KEY",
    "PASSWORD_MAX_AGE_DAYS_KEY",
    "DefaultPasswordPolicy",
    "resolve_inactive_lock_days",
]

DEFAULT_MIN_LENGTH = 8
"""密码最小长度（平台默认；`password.min_length` 覆盖）。"""

DEFAULT_MAX_LENGTH = 128
"""密码最大长度（平台默认；`password.max_length` 覆盖）。"""

DEFAULT_MAX_AGE_DAYS = 90
"""密码有效期天数（平台默认；`password.max_age_days` 覆盖）。"""

ACCOUNT_INACTIVE_LOCK_DAYS = 180
"""未登录自动锁定天数（平台默认；`account.inactive_lock_days` 覆盖；供 org 扫描消费）。"""

PASSWORD_HISTORY_COUNT_KEY = "password.history_count"
"""历史密码条数配置键。"""

PASSWORD_MAX_AGE_DAYS_KEY = "password.max_age_days"
"""密码有效期天数配置键（供 org 登录判定 / 扫描共享）。"""

_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SYMBOL_RE = re.compile(r"[^A-Za-z0-9]")


def _parse_bool(raw: object, default: bool) -> bool:
    """宽松解析布尔配置值（`true/false/1/0/yes/no/on/off`；非法回落默认）。

    Args:
        raw: 原始值。
        default: 默认值。

    Returns:
        bool: 解析结果。
    """
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _parse_int(raw: object, default: int, *, minimum: int = 0) -> int:
    """宽松解析整数配置值（非法 / 小于下限回落默认）。

    Args:
        raw: 原始值。
        default: 默认值。
        minimum: 允许下限。

    Returns:
        int: 解析结果。
    """
    if raw is None or isinstance(raw, bool):
        return default
    try:
        value = int(str(raw).strip())
    except TypeError, ValueError:
        return default
    return value if value >= minimum else default


class DefaultPasswordPolicy(BasePasswordPolicy):
    """真实密码策略：按租户读 `sys_config` 的复杂度 / 有效期 / 历史规则。"""

    plugin_name: str = "default"
    """实现名（配置 `[password_policy].provider = "default"` 命中）。"""

    def __init__(
        self,
        *,
        config: BaseConfigSource,
        hasher: BasePasswordHasher,
    ) -> None:
        """初始化（`config` / `hasher` 无缺省值以防被插件注册表自动收集，经工厂显式登记）。

        Args:
            config: 系统参数取数（按租户读 `sys_config`）。
            hasher: 口令哈希实现（历史比对用）。
        """
        self._config = config
        self._hasher = hasher

    async def validate(self, password: str, *, username: str | None = None) -> tuple[str, ...]:
        """校验密码复杂度（按租户规则；返回缺失项清单）。

        Args:
            password: 待校验的密码明文。
            username: 账号名（用于「密码不得包含用户名」判定）。

        Returns:
            tuple[str, ...]: 违规原因码元组（`PASSWORD_VIOLATIONS` 子集）；空元组通过。
        """
        values = await self._config.get_many(
            ConcurrentStableList(
                (
                    "password.min_length",
                    "password.max_length",
                    "password.require_upper",
                    "password.require_lower",
                    "password.require_digit",
                    "password.require_symbol",
                    "password.forbid_username",
                )
            )
        )
        violations: list[str] = []
        min_length = _parse_int(values.get("password.min_length"), DEFAULT_MIN_LENGTH, minimum=1)
        max_length = _parse_int(values.get("password.max_length"), DEFAULT_MAX_LENGTH, minimum=1)
        if len(password) < min_length:
            violations.append("too_short")
        if len(password) > max_length:
            violations.append("too_long")
        if _parse_bool(values.get("password.require_upper"), True) and not _UPPER_RE.search(password):
            violations.append("need_upper")
        if _parse_bool(values.get("password.require_lower"), True) and not _LOWER_RE.search(password):
            violations.append("need_lower")
        if _parse_bool(values.get("password.require_digit"), True) and not _DIGIT_RE.search(password):
            violations.append("need_digit")
        if _parse_bool(values.get("password.require_symbol"), True) and not _SYMBOL_RE.search(password):
            violations.append("need_symbol")
        if (
            _parse_bool(values.get("password.forbid_username"), True)
            and username
            and username.strip().lower() in password.lower()
        ):
            violations.append("username_included")
        return tuple(violations)

    async def expired(self, pwd_changed_at: datetime, *, now: datetime | None = None) -> bool:
        """密码是否已过有效期（按租户 `password.max_age_days`）。

        Args:
            pwd_changed_at: 上次改密时间（UTC naive；调用方对 NULL 不调用——视为未过期）。
            now: 当前时间；None 取当前 UTC（便于测试注入）。

        Returns:
            bool: 已过期为 True。
        """
        values = await self._config.get_many(ConcurrentStableList((PASSWORD_MAX_AGE_DAYS_KEY,)))
        days = _parse_int(values.get(PASSWORD_MAX_AGE_DAYS_KEY), DEFAULT_MAX_AGE_DAYS, minimum=1)
        current = now or datetime.now(UTC).replace(tzinfo=None)
        return current - pwd_changed_at > timedelta(days=days)

    async def reused(self, password: str, *, history: Sequence[str]) -> bool:
        """密码是否命中历史密码（逐条 PBKDF2 比对；常量时间）。

        Args:
            password: 待校验的密码明文。
            history: 历史密码哈希序列（调用方从 `pwd_history` 取）。

        Returns:
            bool: 命中任一历史为 True；空历史为 False。
        """
        return any(self._hasher.verify(password, hashed) for hashed in history if hashed)

    async def history_count(self) -> int:
        """历史密码不可重复比对条数（按租户 `password.history_count`）。

        Returns:
            int: 保留 / 比对条数（缺省平台默认 5）。
        """
        values = await self._config.get_many(ConcurrentStableList((PASSWORD_HISTORY_COUNT_KEY,)))
        return _parse_int(values.get(PASSWORD_HISTORY_COUNT_KEY), PASSWORD_HISTORY_COUNT, minimum=1)


async def resolve_inactive_lock_days(config: BaseConfigSource) -> int:
    """取未登录自动锁定天数（`account.inactive_lock_days`；缺省 180，非法回落默认）。

    Args:
        config: 系统参数取数（按租户）。

    Returns:
        int: 锁定阈值天数（≥1）。
    """
    values = await config.get_many(ConcurrentStableList(("account.inactive_lock_days",)))
    return _parse_int(values.get("account.inactive_lock_days"), ACCOUNT_INACTIVE_LOCK_DAYS, minimum=1)
