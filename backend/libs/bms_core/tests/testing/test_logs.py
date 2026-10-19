"""测试公共基座：日志事件解析与断言（Kiwi 2317）。"""

import json
import logging

import pytest

from bms_core.testing import assert_logged, log_events


@pytest.mark.kiwi_id(2317)
def test_log_events_parses_structlog_json(capsys: pytest.CaptureFixture[str]) -> None:
    """解析：只收带 `event` 的 JSON 行，非 JSON 行自动跳过，保序。"""
    print("pytest 进度点 ...")
    print(json.dumps({"event": "db.query", "level": "info", "table": "sys_user"}, ensure_ascii=False))
    print(json.dumps({"event": "cache.miss", "level": "warning"}, ensure_ascii=False))
    print("[not-json]")
    print("{bad json")
    print(json.dumps({"no_event": 1}))
    print(json.dumps([1, 2]))

    events = log_events(capsys)

    assert [event.get("event") for event in events] == ["db.query", "cache.miss"]
    assert events[0].get("table") == "sys_user"


@pytest.mark.kiwi_id(2317)
def test_log_events_accepts_text_and_caplog(caplog: pytest.LogCaptureFixture) -> None:
    """兼容：文本原样解析；`caplog` 记录按下标解析。"""
    text = json.dumps({"event": "app.start", "level": "info"})
    assert [event.get("event") for event in log_events(text)] == ["app.start"]

    with caplog.at_level(logging.INFO):
        logging.getLogger("bms.test").info(json.dumps({"event": "legacy.event", "level": "info"}))
    assert [event.get("event") for event in log_events(caplog)] == ["legacy.event"]


@pytest.mark.kiwi_id(2317)
def test_assert_logged_matches_event_level_and_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """断言：事件名 + 级别 + 字段子集匹配。"""
    print(json.dumps({"event": "audit.write", "level": "WARNING", "table": "sys_role"}, ensure_ascii=False))

    assert_logged(capsys, event="audit.write", level="warning", table="sys_role")


@pytest.mark.kiwi_id(2317)
def test_assert_logged_failure_lists_candidates(capsys: pytest.CaptureFixture[str]) -> None:
    """失败：无匹配事件时列出候选事件名。"""
    print(json.dumps({"event": "other.event", "level": "info"}))

    with pytest.raises(AssertionError) as exc:
        assert_logged(capsys, event="missing.event")

    assert "other.event" in str(exc.value)


@pytest.mark.kiwi_id(2317)
def test_assert_logged_rejects_wrong_level_and_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """失败：级别不同、字段不同都判不匹配。"""
    print(json.dumps({"event": "audit.write", "level": "info", "table": "sys_user"}))
    with pytest.raises(AssertionError):
        assert_logged(capsys, event="audit.write", level="warning")

    print(json.dumps({"event": "audit.write", "level": "info", "table": "sys_user"}))
    with pytest.raises(AssertionError):
        assert_logged(capsys, event="audit.write", table="sys_role")
