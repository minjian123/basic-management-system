"""富文本白名单清洗（Kiwi 2518）：标签 / 属性 / URL 协议 / style / 空内容与长度。"""

from __future__ import annotations

import pytest

from bms_core.richtext.sanitize import html_text_length, sanitize_html

pytestmark = pytest.mark.kiwi_id(2518)


def test_sanitize_keeps_allowed_tags_and_text() -> None:
    """允许标签与文本保留；段落 / 列表 / 表格 / 代码块不被剥离。"""
    raw = "<p>公告</p><ul><li>一</li></ul><table><tr><td>格</td></tr></table><pre><code>a</code></pre>"
    cleaned = sanitize_html(raw)
    assert "<p>" in cleaned and "<ul>" in cleaned and "<table>" in cleaned and "<pre>" in cleaned
    assert "公告" in cleaned and "格" in cleaned


def test_sanitize_strips_dangerous_tags_and_handlers() -> None:
    """脚本 / 事件属性 / 内嵌对象一律剥离。"""
    raw = (
        '<script>alert(1)</script><p onclick="alert(1)">a</p>'
        '<iframe src="https://x"></iframe><svg onload="alert(1)"></svg>'
    )
    cleaned = sanitize_html(raw)
    assert "script" not in cleaned.lower()
    assert "onclick" not in cleaned.lower()
    assert "iframe" not in cleaned.lower()
    assert "svg" not in cleaned.lower()


def test_sanitize_url_protocols() -> None:
    """http / https / mailto / 相对路径保留；javascript / data 剥离。"""
    raw = (
        '<a href="https://example.com">h</a>'
        '<a href="mailto:a@example.com">m</a>'
        '<a href="/files/1">r</a>'
        '<a href="javascript:alert(1)">j</a>'
        '<img src="data:image/png;base64,xx">'
    )
    cleaned = sanitize_html(raw)
    assert 'href="https://example.com"' in cleaned
    assert 'href="mailto:a@example.com"' in cleaned
    assert 'href="/files/1"' in cleaned
    assert "javascript:" not in cleaned
    assert "data:" not in cleaned
    assert "<img" in cleaned and "src=" not in cleaned


def test_sanitize_style_whitelist() -> None:
    """style 仅保留属性级白名单，剥离背景图 / 表达式。"""
    raw = '<p style="text-align:center;background:url(x);width:10px;position:fixed">t</p>'
    cleaned = sanitize_html(raw)
    assert "text-align" in cleaned
    assert "width" in cleaned
    assert "background" not in cleaned
    assert "position" not in cleaned
    assert "url(" not in cleaned


def test_sanitize_empty_and_comment() -> None:
    """空输入返回空串；注释剥离。"""
    assert sanitize_html("") == ""
    assert sanitize_html("   ") == ""
    assert sanitize_html("<p>a</p><!-- secret -->") == "<p>a</p>"


def test_html_text_length() -> None:
    """去标签后的可见文本长度（`&nbsp;` 视为空白）。"""
    assert html_text_length("") == 0
    assert html_text_length("<p></p>") == 0
    assert html_text_length("<p>abc</p>") == 3
    assert html_text_length("<p>&nbsp;</p>") == 0
    assert html_text_length("<p>a&nbsp;b</p>") == 3
