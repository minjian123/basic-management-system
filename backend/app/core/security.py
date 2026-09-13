"""core 层安全基座（结构占位）：统一安全原语落点。

- `BaseSecurity`：安全原语**中间层基类**（占位基，统一安全约定与 `_not_implemented`）。
- 原语类：`PasswordHasher` / `TokenCodec` / `SessionSecurity`——方法为接口签名，
  占位实现抛 `NotImplementedError`，真实实现随认证阶段。
- 密钥只走环境变量，不入库、不入镜像、不写日志。
"""

from abc import ABC

from app.core.capability import BaseStub


class BaseSecurity(BaseStub, ABC):
    """安全原语中间层基类：统一安全约定与入口。"""


class PasswordHasher(BaseSecurity):
    """密码哈希 / 校验（bcrypt / argon2；占位）。"""

    def hash(self, password: str) -> str:
        """生成密码哈希。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("密码哈希")

    def verify(self, password: str, hashed: str) -> bool:
        """校验密码。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("密码校验")


class TokenCodec(BaseSecurity):
    """令牌签名 / 校验（双 token；占位）。"""

    def encode(self, claims: dict[str, object], *, expires_in: int | None = None) -> str:
        """签发令牌。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("令牌签发")

    def decode(self, token: str) -> dict[str, object]:
        """校验并解析令牌。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("令牌解析")


class SessionSecurity(BaseSecurity):
    """会话安全原语（占位）。"""

    def new_session_id(self) -> str:
        """生成会话 id。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("会话 id 生成")

    def fingerprint(self, *, ip: str | None, user_agent: str | None) -> str:
        """生成会话指纹。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("会话指纹")

    def blacklist_key(self, session_id: str) -> str:
        """会话黑名单 Redis 键（登出 / 强踢）。

        Raises:
            NotImplementedError: 占位（随认证阶段实现）。
        """
        raise self._not_implemented("会话黑名单键")
