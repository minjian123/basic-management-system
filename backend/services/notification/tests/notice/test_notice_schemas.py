"""公告契约校验（Kiwi 2518）：类型 / 优先级非空、状态闭集、标题长度、过期请求边界。"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from bms_core.core.concurrent import ConcurrentStableDict
from bms_notification.domains.notification.schemas.notice import (
    NoticeCreateRequest,
    NoticeExpireRequest,
    NoticeListItem,
    NoticeTextInput,
    NoticeUpdateRequest,
)

pytestmark = pytest.mark.kiwi_id(2518)


def _item(**overrides: object) -> NoticeListItem:
    """构造合法列表行。

    Args:
        **overrides: 覆盖字段。

    Returns:
        NoticeListItem: 列表行。
    """
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "id": 1,
            "title": "t",
            "type": "system",
            "priority": "normal",
            "is_top": False,
            "status": "published",
            "publish_at": datetime(2026, 1, 1),
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }
    )
    data.update(overrides)  # pyright: ignore[reportArgumentType]
    return NoticeListItem(**data)  # pyright: ignore[reportArgumentType]


def test_type_and_priority_not_blank() -> None:
    """编辑请求：类型 / 优先级显式空串被拒。"""
    with pytest.raises(ValidationError):
        NoticeUpdateRequest(type="  ")
    with pytest.raises(ValidationError):
        NoticeUpdateRequest(priority="")
    assert NoticeUpdateRequest(type="policy", priority="high").type == "policy"


def test_status_must_be_closed_set() -> None:
    """列表行状态必须在 draft / published / offline 内。"""
    assert _item(status="offline").status == "offline"
    with pytest.raises(ValidationError):
        _item(status="archived")


def test_title_length_and_content_default() -> None:
    """标题 1..256；正文缺省空串。"""
    assert NoticeTextInput(title="x").content == ""
    with pytest.raises(ValidationError):
        NoticeTextInput(title="")
    with pytest.raises(ValidationError):
        NoticeTextInput(title="x" * 257)


def test_expire_request_bounds() -> None:
    """批量上限 1..1000；缺省 200。"""
    assert NoticeExpireRequest().limit == 200
    with pytest.raises(ValidationError):
        NoticeExpireRequest(limit=0)
    with pytest.raises(ValidationError):
        NoticeExpireRequest(limit=1001)


def test_create_defaults() -> None:
    """新建默认：system / normal / 不置顶 / 直接发布。"""
    req = NoticeCreateRequest(i18n=ConcurrentStableDict({"zh-CN": NoticeTextInput(title="x")}))
    assert (req.type, req.priority, req.is_top, req.publish) == ("system", "normal", False, True)
