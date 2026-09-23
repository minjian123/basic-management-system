"""oauth 能力域服务 JWT 密钥工具：`TokenKey`（kid → 密钥材料）+ JWKS 文档 / JWK Set 构建。

- `TokenKey`：kid / 算法（白名单 RS256 / ES256）/ 公钥 PEM / 私钥 PEM（**私钥只经环境变量 / Secret 注入**）。
- `build_jwks`：标准 JWKS 文档（只含公钥、按 kid 排序，确定性输出）。
- `to_key_set`：构造 joserfc `KeySet`（供本地验签，含全部公钥）。

口径：签验引擎统一取 **joserfc**（authlib 官方 JOSE 拆分包）；仅接受非对称算法白名单，禁对称算法防签名绕过。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from joserfc.jwk import ECKey, KeyParameters, KeySet, RSAKey

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ConfigError
from bms_core.idp.jwks import DEFAULT_ALGORITHMS

__all__ = [
    "ALLOWED_ALGORITHMS",
    "JWK_USE_SIGNATURE",
    "TokenKey",
    "build_jwks",
    "to_key_set",
]

ALLOWED_ALGORITHMS: tuple[str, ...] = tuple(DEFAULT_ALGORITHMS)
"""签名算法白名单（仅非对称；与 idp 验签同一口径）。"""

JWK_USE_SIGNATURE = "sig"
"""JWK `use` 取值（签名用途）。"""

_RSA_PREFIX = "RS"


@dataclass(frozen=True)
class TokenKey(BaseObject):
    """服务 JWT 签名 / 验签密钥（kid 为映射键，公私钥 PEM 均由配置注入）。"""

    kid: str
    """密钥标识（JWKS 与 JOSE header 的 `kid`，验签按此命中）。"""

    algorithm: str = "RS256"
    """签名算法（白名单 RS256 / ES256）。"""

    public_key: str = ""
    """公钥 PEM（非敏感，可入配置；供验签与 JWKS 输出）。"""

    private_key: str = ""
    """私钥 PEM（**只经环境变量 / Secret 注入**，不入库 / 不入镜像 / 不落日志）。"""

    def __post_init__(self) -> None:
        """校验算法白名单与密钥材料齐备。

        Raises:
            ConfigError: 算法不在白名单 / 公私钥均缺失（40001）。
        """
        if self.algorithm not in ALLOWED_ALGORITHMS:
            raise ConfigError(f"服务令牌签名算法不在白名单：{self.algorithm}（允许 {'/'.join(ALLOWED_ALGORITHMS)}）")
        if not self.public_key and not self.private_key:
            raise ConfigError(f"服务令牌密钥缺少公钥 / 私钥：{self.kid}")

    @property
    def can_sign(self) -> bool:
        """是否持有私钥（可用于签发）。

        Returns:
            bool: 有私钥为 True。
        """
        return bool(self.private_key)

    def signing_key(self) -> RSAKey | ECKey:
        """导入私钥对象（签发用）。

        Returns:
            RSAKey | ECKey: joserfc 私钥对象（含 kid / alg / use）。

        Raises:
            ConfigError: 未配置私钥（40001）。
        """
        if not self.private_key:
            raise ConfigError(f"服务令牌密钥未配置私钥，无法签发：{self.kid}")
        return self._import(self.private_key)

    def verify_key(self) -> RSAKey | ECKey:
        """导入公钥对象（验签 / JWKS 用）。

        Returns:
            RSAKey | ECKey: joserfc 公钥对象（含 kid / alg / use）。

        Raises:
            ConfigError: 未配置公钥（40001）。
        """
        if not self.public_key:
            raise ConfigError(f"服务令牌密钥未配置公钥：{self.kid}")
        return self._import(self.public_key)

    def public_jwk(self) -> Mapping[str, object]:
        """导出公钥 JWK（只含公有参数 + kid / alg / use）。

        Returns:
            Mapping[str, object]: JWK 字典。

        Raises:
            ConfigError: 未配置公钥（40001）。
        """
        return cast("Mapping[str, object]", self.verify_key().as_dict(private=False))

    def _import(self, pem: str) -> RSAKey | ECKey:
        """按算法族导入 PEM 密钥。

        Args:
            pem: PEM 文本。

        Returns:
            RSAKey | ECKey: joserfc 密钥对象。

        Raises:
            ConfigError: PEM 非法 / 类型不匹配（40001）。
        """
        parameters: KeyParameters = {"kid": self.kid, "alg": self.algorithm, "use": JWK_USE_SIGNATURE}
        loader = RSAKey if self.algorithm.startswith(_RSA_PREFIX) else ECKey
        try:
            return loader.import_key(pem, parameters=parameters)
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"服务令牌密钥 PEM 非法或不匹配算法：{self.kid}") from exc


def build_jwks(keys: Iterable[TokenKey]) -> dict[str, object]:
    """构建标准 JWKS 文档（只含公钥，按 kid 排序）。

    Args:
        keys: 密钥集（只需公钥即可输出）。

    Returns:
        dict[str, object]: `{"keys": [公钥 JWK, ...]}`（确定性输出）。
    """
    return {"keys": [dict(key.public_jwk()) for key in sorted(keys, key=lambda item: item.kid)]}


def to_key_set(keys: Iterable[TokenKey]) -> KeySet:
    """把密钥集导入为 joserfc `KeySet`（本地验签用，含全部公钥）。

    Args:
        keys: 密钥集。

    Returns:
        KeySet: joserfc 密钥集。

    Raises:
        ConfigError: 任一密钥缺公钥（40001）。
    """
    return KeySet([key.verify_key() for key in keys])
