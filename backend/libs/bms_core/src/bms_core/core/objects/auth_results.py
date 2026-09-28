"""值对象体系 · 认证结果链层：登录 / 刷新结果与授权跳转结果。

**链结构（按公共段成层，本次 2 层平级）**：

- `BaseLoginResultContract`（公共段 `result` + `refresh_token` + `refresh_expires_in`）——登录 / 刷新一次性结果；
- `BaseAuthorizeUrlResultContract`（**不变式**：跳转地址 + 一次性凭据；以 `URL_FIELD` + `url` 统一读取地址）
  ——授权跳转结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseAuthorizeUrlResultContract", "BaseLoginResultContract"]


@dataclass(frozen=True)
class BaseLoginResultContract(BaseValueObject):
    """登录结果契约（角色链层）：登录 / 刷新接口返回的一次性结果。

    公共段：`result` + `refresh_token` + `refresh_expires_in`（结果载体 + 刷新令牌位）。

    说明：`result` 的**具体类型由成员各自声明**（登录为 `LoginResult`、刷新为 `RefreshResult`），
    故本层不约束其类型，只约定字段存在与语义。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("result", "refresh_token", "refresh_expires_in")


@dataclass(frozen=True)
class BaseAuthorizeUrlResultContract(BaseValueObject):
    """授权跳转结果契约（角色链层）：跳转地址与一次性凭据。

    **公共段为不变式**：承载跳转地址 + 一次性凭据（OIDC 侧为 `code`、SSO 侧为 `state`，
    语义不同故**不统一字段名**）；地址字段名历史不统一（`AuthorizeResult.redirect_url`
    / `SsoAuthorizeResult.authorize_url`）——本层以 `URL_FIELD` 声明承载字段，并以 `url`
    属性提供**统一读取名**（不重命名字段，避免消费方返工）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ()
    URL_FIELD: ClassVar[str] = ""
    """本类承载授权跳转地址的字段名（成员声明；`url` 属性按此读取）。"""

    @property
    def url(self) -> str:
        """授权跳转地址（按 `URL_FIELD` 统一读取）。

        Returns:
            str: 授权跳转地址。
        """
        return getattr(self, type(self).URL_FIELD)
