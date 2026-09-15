"""password 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.password.base.py 迁入）。"""

from collections.abc import Sequence
from datetime import datetime

from app.core.capability import BaseNullObject
from app.password.base import BasePasswordPolicy

__all__ = [
    "NullPasswordPolicy",
]


class NullPasswordPolicy(BasePasswordPolicy, BaseNullObject):
    """占位密码策略：**恒定允许**（不读 sys_config、不查历史，未接入真实实现时使用）。"""

    async def validate(self, password: str, *, username: str | None = None) -> tuple[str, ...]:
        """恒定通过（占位不校验复杂度）。

        Args:
            password: 待校验的密码明文（占位不校验）。
            username: 账号名（占位不校验）。

        Returns:
            tuple[str, ...]: 空元组（无违规）。
        """
        return ()

    async def expired(self, pwd_changed_at: datetime, *, now: datetime | None = None) -> bool:
        """恒定未过期（占位不校验有效期）。

        Args:
            pwd_changed_at: 上次改密时间（占位不校验）。
            now: 当前时间（占位不校验）。

        Returns:
            bool: False。
        """
        return False

    async def reused(self, password: str, *, history: Sequence[str]) -> bool:
        """恒定未命中（占位不比对历史）。

        Args:
            password: 待校验的密码明文（占位不比对）。
            history: 历史密码序列（占位不比对）。

        Returns:
            bool: False。
        """
        return False
