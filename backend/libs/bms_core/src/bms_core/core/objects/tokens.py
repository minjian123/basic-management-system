"""值对象体系 · 令牌链层：令牌承载、令牌声明、声明读取结果与敏感材料。

**链结构（按公共段成层，链长 4 段）**：

- `BaseTokenContract`（公共段 `token_type`）——签出 / 校验后的令牌承载；
  - `BaseRefreshableTokenContract`（公共段 `access_token` + `refresh_token`）——可刷新令牌对；
- `BaseTokenSpecContract`（公共段 `ttl`）——待签令牌声明；
  - `BaseOidcTokenSpecContract`（公共段 `client_id` + `issuer`）——OIDC 侧令牌声明；
- `BaseTokenClaimsContract`（公共段 `subject` + `expires_at` + `issued_at` + `payload`）——令牌声明读取结果；
- `BaseSecretMaterialContract`（**不变式**公共段：`SECRET_FIELDS` 声明的敏感字段统一遮蔽输出）。

**公共段口径**：各层以 `COMMON_FIELDS` 声明**本层自身承接**的公共段（父层公共段沿继承链累加，校验时按 MRO 汇总）；
公共段对应的字段仍由**成员自身**声明——不在层上声明字段，避免改变 dataclass 字段顺序与 `__init__` 位置参数序。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = [
    "BaseOidcTokenSpecContract",
    "BaseRefreshableTokenContract",
    "BaseSecretMaterialContract",
    "BaseTokenClaimsContract",
    "BaseTokenContract",
    "BaseTokenSpecContract",
]


@dataclass(frozen=True)
class BaseTokenContract(BaseValueObject):
    """令牌契约（角色链层）：签出 / 校验后的令牌承载。

    公共段：`token_type`（令牌类型标识）；成员为携带令牌串的签出结果或校验结果。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("token_type",)


@dataclass(frozen=True)
class BaseRefreshableTokenContract(BaseTokenContract):
    """可刷新令牌契约（角色链层）：同时携带访问令牌与刷新令牌的令牌对。

    公共段：`access_token` + `refresh_token`（刷新令牌**可为空**——外部身份源未返回时无刷新位）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("access_token", "refresh_token")


@dataclass(frozen=True)
class BaseTokenSpecContract(BaseValueObject):
    """令牌声明契约（角色链层）：待签发的令牌声明。

    公共段：`ttl`（可空——不指定时用实现缺省寿命）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("ttl",)


@dataclass(frozen=True)
class BaseOidcTokenSpecContract(BaseTokenSpecContract):
    """OIDC 令牌声明契约（角色链层）：面向 OIDC 客户端签发的令牌声明。

    公共段：`client_id` + `issuer`（声明归属的客户端与签发方）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("client_id", "issuer")


@dataclass(frozen=True)
class BaseTokenClaimsContract(BaseValueObject):
    """令牌声明读取结果契约（角色链层）：票据校验 / 解析后回读的声明集合。

    公共段：`subject` + `expires_at` + `issued_at` + `payload`（主体、有效期、签发时刻与原始声明）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("subject", "expires_at", "issued_at", "payload")


@dataclass(frozen=True)
class BaseSecretMaterialContract(BaseValueObject):
    """敏感材料契约（角色链层）：类内含私密材料（密钥 / 口令）的不可变数据类。

    **公共段为不变式**（不是字段）：成员以 `SECRET_FIELDS` 声明本类的敏感字段，并在
    `@dataclass(frozen=True, repr=False)` 下由本层统一生成**遮蔽后**的表示——避免明文密钥 /
    口令进入日志与报错信息（`frozen=True` 仍由 dataclass 强制，值语义不变）。
    """

    SECRET_FIELDS: ClassVar[tuple[str, ...]] = ()
    """本类敏感字段名（子类声明；`repr` 中一律以 `***` 呈现）。"""

    def __repr__(self) -> str:
        """生成遮蔽敏感字段后的表示（`SECRET_FIELDS` 命中的字段值一律替换为 `***`）。

        Returns:
            str: `类名(字段=值, …)` 形态；敏感字段值为 `***`。
        """
        rendered = ", ".join(
            f"{field.name}={'***' if field.name in self.SECRET_FIELDS else getattr(self, field.name)!r}"
            for field in fields(self)
        )
        return f"{type(self).__name__}({rendered})"
