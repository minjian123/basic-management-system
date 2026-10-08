"""请求契约严格模式用例（Kiwi 2267，02_03 追加子任务「角色码可改与内置判定脱钩」）。

`BaseSchema` 置 `extra="forbid"` 后：**请求体未知字段即拒**（不再静默忽略），
已知字段照常校验；`from_attributes` 响应侧不受影响（额外属性不参与校验）。
"""

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from bms_core.schemas.base import BaseSchema


class _SampleRequest(BaseSchema):
    """示例请求模型（仅一个已知字段，用于未知字段判定）。"""

    name: str


@dataclass
class _SampleEntity:
    """示例实体（模拟 ORM 行：多出 `extra` 属性）。"""

    name: str
    extra: str = "ignored"


def test_unknown_field_rejected() -> None:
    """未知字段即拒（杜绝「带只读字段更新被静默忽略」）。"""
    with pytest.raises(ValidationError):
        _SampleRequest.model_validate({"name": "a", "code": "b"})


def test_known_field_accepted() -> None:
    """已知字段正常校验。"""
    assert _SampleRequest.model_validate({"name": "a"}).name == "a"


def test_entity_extra_attributes_ignored() -> None:
    """`from_attributes` 响应侧不受严格模式影响（实体多余属性被忽略）。"""
    assert _SampleRequest.model_validate(_SampleEntity(name="a")).name == "a"
