"""日志基座接入点测试（Kiwi 23）。"""

import logging

import pytest

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.logging import BaseLogger, StdoutLogger, configure_logging, get_logger


@pytest.mark.kiwi_id(23)
def test_inheritance_and_factory() -> None:
    """门面纳入 L0；get_logger 返回门面。"""
    assert issubclass(BaseLogger, BaseObject)
    assert issubclass(StdoutLogger, BaseLogger)
    assert isinstance(get_logger(), BaseLogger)


@pytest.mark.kiwi_id(23)
def test_configure_logging_idempotent_and_level() -> None:
    """初始化幂等；级别取自 settings.log.level。"""
    configure_logging(Settings())
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handler_count = len(root.handlers)
    configure_logging(Settings())
    assert len(root.handlers) == handler_count


@pytest.mark.kiwi_id(23)
def test_methods_output_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """各日志方法输出到 stdout、不落文件。"""
    configure_logging(Settings())
    logger = get_logger("app.test")
    logger.debug("event_debug")
    logger.info("event_info")
    logger.warning("event_warning")
    logger.error("event_error")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("event_exception")
    out = capsys.readouterr().out
    for token in ("event_debug", "event_info", "event_warning", "event_error", "event_exception"):
        assert token in out


@pytest.mark.kiwi_id(23)
def test_bind_context(capsys: pytest.CaptureFixture[str]) -> None:
    """bind 返回新门面，绑定字段只影响新实例。"""
    configure_logging(Settings())
    logger = get_logger("app.test")
    bound = logger.bind(trace_id="t1")
    bound.info("bound_event")
    assert "trace_id" in capsys.readouterr().out

    logger.info("plain_event")
    assert "trace_id" not in capsys.readouterr().out
