"""core 层安全原语：请求签名（HMAC-SHA256，**真实实现**）。

- `SignatureCodec`：请求签名原语（HMAC-SHA256）——供防重放域与出站集成（Webhook）复用；
  串料口径见类文档。
- **安全原语（口令哈希 / 令牌编解码 / 会话安全）已迁入 `bms_core/security/` 能力域**（阶段六 01_01）：
  契约见 `security/base.py`、真实实现见 `security/{pbkdf2,jwt,session}.py`、缺省实现见 `security/null.py`
  （fail-closed）、装配见 `core/assembly.py` 与 `[password_hasher]` / `[token_codec]` / `[session_security]`。
- 密钥只走环境变量，不入库、不入镜像、不写日志。
"""

import hashlib
import hmac

from bms_core.security.base import BaseSecurity

SIGNATURE_HEADER = "X-Signature"
"""请求签名头（入站验签与调用方计算签名的头部口径）。"""

SIGNATURE_ALGORITHM = "sha256"
"""签名算法（HMAC-SHA256，摘要以 hex 小写输出）。"""


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
