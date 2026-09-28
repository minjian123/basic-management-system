"""值对象体系 · 验证码链层：挑战与凭据。

**链结构（按公共段成层，本次 1 层）**：

- `BaseCaptchaContract`（公共段 `captcha_id` + `kind` + `scene`）——挑战侧与凭据侧共用三元标识。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseCaptchaContract"]


@dataclass(frozen=True)
class BaseCaptchaContract(BaseValueObject):
    """验证码契约（角色链层）：挑战 / 凭据的**三元标识**统一读面。

    公共段：`captcha_id`（挑战标识）+ `kind`（形态：图形 / 滑块 / 短信）+ `scene`（场景）——
    出题（`CaptchaChallenge`）与验码（`CaptchaCredential`）两侧共用，校验按同一三元组定位挑战。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("captcha_id", "kind", "scene")
