"""core 层安全基座：统一安全原语落点。

- `BaseSecurity`：安全原语**中间层基类**（统一安全约定与 `_not_implemented`）。
- 原语类：`PasswordHasher` / `TokenCodec` / `SessionSecurity`——方法为接口签名，
  占位实现抛 `NotImplementedError`，真实实现随认证阶段。
- `SignatureCodec`：请求签名原语（HMAC-SHA256）——**真实实现**（纯计算、无密钥托管与外部依赖），
  供防重放域与出站集成（Webhook）复用；串料口径见类文档。
- 密钥只走环境变量，不入库、不入镜像、不写日志。
"""

import hashlib
import hmac
from abc import ABC

from bms_core.core.capability import BaseStub

SIGNATURE_HEADER = "X-Signature"
"""请求签名头（入站验签与调用方计算签名的头部口径）。"""

SIGNATURE_ALGORITHM = "sha256"
"""签名算法（HMAC-SHA256，摘要以 hex 小写输出）。"""


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


class SignatureCodec(BaseSecurity):
    """请求签名原语：HMAC-SHA256（**真实实现**，标准库 `hmac` / `hashlib`）。

    串料规范（开放接口对接契约，换行符分隔，行序固定）：

    ```text
    {method}\\n{path}\\n{timestamp}\\n{nonce}\\n{body}
    ```

    - `method`：HTTP 方法（统一大写）；
    - `path`：请求路径（不含查询串）；
    - `timestamp`：Unix 秒（与服务器时间窗口比对，窗口口径见 `app/replay/base.py`）；
    - `nonce`：随机唯一串（窗口内去重）；
    - `body`：原始请求体（无体传空串，**不重新序列化**）。

    密钥由调用方传入（开放接口为 `sys_client` secret），本原语不读库、不落日志。
    """

    def build_payload(self, *, method: str, path: str, timestamp: int, nonce: str, body: str = "") -> str:
        """构建待签串料。

        Args:
            method: HTTP 方法（统一大写）。
            path: 请求路径（不含查询串）。
            timestamp: Unix 秒时间戳。
            nonce: 随机唯一串。
            body: 原始请求体（无体传空串）。

        Returns:
            str: 待签串料。
        """
        return "\n".join((method.upper(), path, str(timestamp), nonce, body))

    def sign(
        self,
        *,
        secret: str,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        body: str = "",
    ) -> str:
        """计算请求签名（HMAC-SHA256，hex 小写）。

        Args:
            secret: 签名密钥。
            method: HTTP 方法。
            path: 请求路径（不含查询串）。
            timestamp: Unix 秒时间戳。
            nonce: 随机唯一串。
            body: 原始请求体（无体传空串）。

        Returns:
            str: 签名摘要（hex 小写）。
        """
        payload = self.build_payload(method=method, path=path, timestamp=timestamp, nonce=nonce, body=body)
        return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(
        self,
        *,
        secret: str,
        signature: str,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        body: str = "",
    ) -> bool:
        """校验请求签名（恒定时间比对）。

        Args:
            secret: 签名密钥。
            signature: 待校验签名（`X-Signature`，hex）。
            method: HTTP 方法。
            path: 请求路径（不含查询串）。
            timestamp: Unix 秒时间戳。
            nonce: 随机唯一串。
            body: 原始请求体（无体传空串）。

        Returns:
            bool: 签名一致为 True。
        """
        expected = self.sign(
            secret=secret,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        return hmac.compare_digest(expected, signature.strip().lower())
