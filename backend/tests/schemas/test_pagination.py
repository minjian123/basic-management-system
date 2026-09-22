"""分页契约测试（Kiwi 1078）：页码限深（配置可调）与游标请求契约。"""

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.pagination import BaseCursorQuery, BasePageQuery


@pytest.mark.kiwi_id(1078)
def test_page_depth_within_configured_limit() -> None:
    """页码在 `[pagination].max_page` 内通过（末页与首页均可）。"""
    max_page = get_settings().pagination.max_page
    assert max_page >= 1
    assert BasePageQuery(page=1).page == 1
    assert BasePageQuery(page=max_page).page == max_page


@pytest.mark.kiwi_id(1078)
def test_page_depth_exceeds_limit_rejected() -> None:
    """页码超出限深按参数非法拒绝（10001 口径；大数据量请用游标分页）。"""
    max_page = get_settings().pagination.max_page
    with pytest.raises(ValidationError):
        BasePageQuery(page=max_page + 1)


@pytest.mark.kiwi_id(1078)
def test_page_depth_follows_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """限深随配置调整（`BMS_PAGINATION__MAX_PAGE`）。"""
    monkeypatch.setenv("BMS_PAGINATION__MAX_PAGE", "3")
    get_settings.cache_clear()
    assert get_settings().pagination.max_page == 3
    assert BasePageQuery(page=3).page == 3
    with pytest.raises(ValidationError):
        BasePageQuery(page=4)


@pytest.mark.kiwi_id(1078)
def test_cursor_query_contract() -> None:
    """游标请求契约：首页游标为空、limit 上限 200、排序参数继承自排序契约。"""
    query = BaseCursorQuery(limit=200, order_by="created_at", order=["desc"])
    assert query.cursor is None
    assert query.limit == 200
    assert [spec.field for spec in query.specs()] == ["created_at"]
    with pytest.raises(ValidationError):
        BaseCursorQuery(limit=201)
