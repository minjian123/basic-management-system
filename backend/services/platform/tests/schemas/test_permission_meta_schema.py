"""业务码 / 动作码形态契约（snake_case，任务 `01_08` / Kiwi 2357）。

- 新规则：小写字母开头，仅小写字母 / 数字 / 下划线（`^[a-z][a-z0-9_]*$`）；
- 设计：项目骨架任务 `01_08`「登记标识二期」详细设计（`bms文档/项目/01_项目骨架/`）。
"""

import pytest
from pydantic import ValidationError

from bms_core.core.concurrent import ConcurrentStableDict
from bms_platform.domains.permission_meta.schemas.permission_meta import (
    ActionCreateRequest,
    BusinessCreateRequest,
)


def _names(text: str = "文案") -> ConcurrentStableDict[str, str]:
    """构造最小多语言名称映射。

    Args:
        text: 中文文案。

    Returns:
        ConcurrentStableDict[str, str]: 名称映射。
    """
    return ConcurrentStableDict({"zh-CN": text})


@pytest.mark.kiwi_id(2357)
def test_business_and_action_code_accept_snake_case() -> None:
    """snake_case 业务码 / 动作码通过校验（含数字与下划线）。"""
    assert BusinessCreateRequest(code="biz_a1", i18n=_names()).code == "biz_a1"
    assert ActionCreateRequest(code="act_x9", i18n=_names()).code == "act_x9"


@pytest.mark.kiwi_id(2357)
@pytest.mark.parametrize("code", ["biz-a", "biz_a-b", "Biz_a", "1biz", "_biz"])
def test_business_code_rejects_kebab_and_invalid(code: str) -> None:
    """业务码拒绝连字符与非法形态。"""
    with pytest.raises(ValidationError):
        BusinessCreateRequest(code=code, i18n=_names())


@pytest.mark.kiwi_id(2357)
@pytest.mark.parametrize("code", ["act-x", "act_x-y", "Act_x", "1act", "_act"])
def test_action_code_rejects_kebab_and_invalid(code: str) -> None:
    """动作码拒绝连字符与非法形态。"""
    with pytest.raises(ValidationError):
        ActionCreateRequest(code=code, i18n=_names())
