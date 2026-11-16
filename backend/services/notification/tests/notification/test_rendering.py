"""模板沙箱：语法 / 危险结构 / 输出上限 / 超时 / 严格参数。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import (
    ChannelConfigInvalidError,
    SendRateLimitedError,
    TemplateRenderError,
    TemplateSyntaxInvalidError,
)
from bms_notification.domains.notification.rendering import render_template, validate_template

pytestmark = pytest.mark.kiwi_id(2519)


def test_syntax_error_rejected() -> None:
    """语法错误保存即拒（70302）。"""
    with pytest.raises(TemplateSyntaxInvalidError):
        validate_template("{% if x %}", max_bytes=1000)
    with pytest.raises(TemplateSyntaxInvalidError):
        validate_template("{{ x ", max_bytes=1000)


def test_forbidden_structures_rejected() -> None:
    """禁止 include / extends / import / macro / 下划线属性。"""
    for source in (
        "{% include 'x.html' %}",
        "{% extends 'base.html' %}",
        "{% import 'x' as m %}",
        "{% from 'x' import y %}",
        "{% macro m() %}{% endmacro %}",
        "{{ user.__class__ }}",
        "{{ user['__globals__'] }}",
    ):
        with pytest.raises(TemplateSyntaxInvalidError):
            validate_template(source, max_bytes=1000)


def test_lenient_save_and_strict_render() -> None:
    """保存期允许空参数；发送期缺参失败。"""
    validate_template("Hi {{ name }}", max_bytes=1000)
    with pytest.raises(TemplateRenderError):
        validate_template("Hi {{ name }}", max_bytes=1000, sample_params=ConcurrentStableDict({"other": "x"}))
    with pytest.raises(TemplateRenderError):
        validate_template("{{ 1 | bad_filter }}", max_bytes=1000)


async def test_render_strict_and_output_cap() -> None:
    """严格渲染成功；输出超限即失败。"""
    assert (
        await render_template("Hi {{ name }}", ConcurrentStableDict({"name": "A"}), max_bytes=100, timeout_seconds=3)
        == "Hi A"
    )
    with pytest.raises(TemplateRenderError):
        await render_template("{{ 'x' * 200 }}", None, max_bytes=100, timeout_seconds=3)


async def test_render_param_validation() -> None:
    """参数键非法 / 值非标量 / 数量超限。"""
    with pytest.raises(TemplateRenderError):
        await render_template("x", ConcurrentStableDict({"1bad": "x"}), max_bytes=100, timeout_seconds=3)
    with pytest.raises(TemplateRenderError):
        await render_template("x", ConcurrentStableDict({"bad": object()}), max_bytes=100, timeout_seconds=3)
    with pytest.raises(TemplateRenderError):
        await render_template(
            "x", ConcurrentStableDict({f"k{i}": "v" for i in range(51)}), max_bytes=100, timeout_seconds=3
        )


def test_channel_and_rate_limit_errors() -> None:
    """渠道未配置 / 限流预留码的错误码与状态。"""
    assert ChannelConfigInvalidError("x").code == 70305
    assert ChannelConfigInvalidError("x").http_status == 503
    assert SendRateLimitedError("x").code == 70306
    assert SendRateLimitedError("x").http_status == 429


async def test_render_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """渲染超时按失败处理。"""
    import bms_notification.domains.notification.rendering as module

    original = module._render_sync
    monkeypatch.setattr(
        module,
        "_render_sync",
        lambda *args, **kwargs: __import__("time").sleep(0.05) or original(*args, **kwargs),
    )
    with pytest.raises(TemplateRenderError):
        await render_template("x", None, max_bytes=100, timeout_seconds=0.01)
