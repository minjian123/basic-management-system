"""密码策略能力域：密码复杂度 / 有效期 / 历史重复契约（真实 sys_config 策略随四 认证与安全阶段回补）。

- `BasePasswordPolicy`：能力域中间层契约（`key = "password_policy"`）——`validate`（复杂度校验，返回违规
  原因码元组）/ `expired`（是否超有效期）/ `reused`（是否命中历史密码）。
- `get_password_policy`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

与安全原语（`app/core/security.py`）分工：密码**哈希**走 `PasswordHasher`（PBKDF2，随认证阶段填实现）；
本基座只做**策略判定**（复杂度 / 有效期 / 历史重复），不重复哈希、不直连库（历史由调用方传入）。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

PASSWORD_VIOLATIONS: tuple[str, ...] = (
    "too_short",
    "too_long",
    "need_upper",
    "need_lower",
    "need_digit",
    "need_symbol",
    "username_included",
)
"""密码违规原因码（占位期仅登记；上层据此映射提示文案，如 `error.password.too_short`）。"""


class BasePasswordPolicy(BasePluggable, ABC):
    """密码策略契约：复杂度校验 + 有效期 + 历史重复判定。"""

    key: str = "password_policy"
    plugin_key: str = "password_policy"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def validate(self, password: str, *, username: str | None = None) -> tuple[str, ...]:
        """校验密码复杂度。

        Args:
            password: 待校验的密码明文。
            username: 账号名（用于「密码不得包含用户名」判定）。

        Returns:
            tuple[str, ...]: 违规原因码元组（取值见 `PASSWORD_VIOLATIONS`）；空元组表示通过。
        """

    @abstractmethod
    async def expired(self, pwd_changed_at: datetime, *, now: datetime | None = None) -> bool:
        """密码是否已过有效期。

        Args:
            pwd_changed_at: 上次改密时间（`pwd_changed_at`）。
            now: 当前时间；None 表示取当前时间（便于测试注入）。

        Returns:
            bool: 已过期为 True。
        """

    @abstractmethod
    async def reused(self, password: str, *, history: Sequence[str]) -> bool:
        """密码是否命中历史密码。

        Args:
            password: 待校验的密码明文。
            history: 历史密码（哈希或明文）序列，由调用方从 `pwd_history` 取。

        Returns:
            bool: 命中历史为 True。
        """


def get_password_policy(request: Request) -> BasePasswordPolicy:
    """取应用级密码策略基座（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePasswordPolicy: 应用装配的密码策略实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePasswordPolicy",
        resolve_plugin(
            "password_policy",
            settings.password_policy.provider,
            expected_version=BasePasswordPolicy.contract_version,
        ),
    )
