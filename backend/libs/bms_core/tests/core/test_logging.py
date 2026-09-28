"""日志基座测试（Kiwi 34 结构回归 + Kiwi 63 日志体系）。"""

import json
import logging
from typing import Literal

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.config import LogSettings, Settings
from bms_core.core.context import (
    current_user_id,
    set_current_client_ip,
    set_current_request_id,
    set_current_tenant,
    set_current_trace_id,
)
from bms_core.core.logging import BaseLogger, StdoutLogger, configure_logging, get_logger


def _settings(fmt: Literal["console", "json"], *, level: str = "INFO", slow_ms: int = 1000) -> Settings:
    """构造指定日志形态的配置（其余取基线文件）。"""
    return Settings(log=LogSettings(level=level, format=fmt, slow_request_ms=slow_ms))


def _records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """读取 stdout 并按 JSON 行解析（忽略空行）。"""
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


@pytest.mark.kiwi_id(34)
def test_inheritance_and_factory() -> None:
    """门面纳入 L0；get_logger 返回门面。"""
    assert issubclass(BaseLogger, BaseObject)
    assert issubclass(StdoutLogger, BaseLogger)
    assert isinstance(get_logger(), BaseLogger)


@pytest.mark.kiwi_id(34)
def test_configure_logging_idempotent_and_level() -> None:
    """初始化幂等；级别取自 settings.log.level。"""
    configure_logging(Settings())
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handler_count = len(root.handlers)
    configure_logging(Settings())
    assert len(root.handlers) == handler_count


@pytest.mark.kiwi_id(34)
def test_methods_output_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """各日志方法输出到 stdout、不落文件。"""
    configure_logging(Settings())
    logger = get_logger("app.test")
    logger.debug("event_debug")
    logger.info("event_info")
    logger.warning("event_warning")
    logger.error("event_error")
    logger.critical("event_critical")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("event_exception")
    out = capsys.readouterr().out
    for token in ("event_debug", "event_info", "event_warning", "event_error", "event_critical", "event_exception"):
        assert token in out


@pytest.mark.kiwi_id(34)
def test_bind_context(capsys: pytest.CaptureFixture[str]) -> None:
    """bind 返回新门面，绑定字段只影响新实例。"""
    configure_logging(Settings())
    logger = get_logger("app.test")
    bound = logger.bind(trace_id="t1")
    bound.info("bound_event")
    assert "trace_id" in capsys.readouterr().out

    logger.info("plain_event")
    assert "trace_id" not in capsys.readouterr().out


@pytest.mark.kiwi_id(63)
def test_json_render_single_line_and_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON 渲染：物理单行、字段齐备、中文不转义。"""
    configure_logging(_settings("json"))
    get_logger("app.test").info("user_created", user="张三", count=2)
    out = capsys.readouterr().out
    assert "张三" in out
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "user_created"
    assert record["level"] == "info"
    assert record["logger"] == "app.test"
    ts = str(record["ts"])
    assert "T" in ts and ("+" in ts or ts.endswith("Z"))
    assert record["user"] == "张三"
    assert record["count"] == 2


@pytest.mark.kiwi_id(63)
def test_json_exception_stack_is_single_line(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON 渲染：异常堆栈物理单行（换行转义）。"""
    configure_logging(_settings("json"))
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("app.test").exception("failed")
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "failed"
    assert "ValueError: boom" in str(record["exception"])


@pytest.mark.kiwi_id(63)
def test_console_render(capsys: pytest.CaptureFixture[str]) -> None:
    """console 渲染：可读输出含事件与字段。"""
    configure_logging(_settings("console"))
    get_logger("app.test").info("console_event", k=1)
    out = capsys.readouterr().out
    assert "console_event" in out
    assert "k=1" in out


@pytest.mark.kiwi_id(63)
def test_context_fields_injected(capsys: pytest.CaptureFixture[str]) -> None:
    """上下文字段注入：trace_id / request_id / tenant / user_id / client_ip。"""
    configure_logging(_settings("json"))
    set_current_trace_id("t" * 32)
    set_current_request_id("r" * 32)
    set_current_tenant("demo")
    current_user_id.set(42)
    set_current_client_ip("10.0.0.1")
    get_logger("app.test").info("ctx_event")
    record = _records(capsys)[0]
    assert record["trace_id"] == "t" * 32
    assert record["request_id"] == "r" * 32
    assert record["tenant"] == "demo"
    assert record["user_id"] == 42
    assert record["client_ip"] == "10.0.0.1"


@pytest.mark.kiwi_id(63)
def test_explicit_field_wins_over_context(capsys: pytest.CaptureFixture[str]) -> None:
    """显式字段优先于上下文注入。"""
    configure_logging(_settings("json"))
    set_current_trace_id("t" * 32)
    get_logger("app.test").info("explicit_event", trace_id="explicit-trace")
    record = _records(capsys)[0]
    assert record["trace_id"] == "explicit-trace"


@pytest.mark.kiwi_id(63)
def test_redaction_sensitive_keys(capsys: pytest.CaptureFixture[str]) -> None:
    """脱敏：敏感键名与后缀命中（含嵌套结构），原值不落日志。"""
    configure_logging(_settings("json"))
    get_logger("app.test").info(
        "login",
        password="PWD-VALUE",
        authorization="AUTH-VALUE",
        db_password="DBPWD-VALUE",
        jwt_token="JWT-VALUE",
        payload={"client_secret": "CS-VALUE", "keep": "ok"},
    )
    out = capsys.readouterr().out
    for leaked in ("PWD-VALUE", "AUTH-VALUE", "DBPWD-VALUE", "JWT-VALUE", "CS-VALUE"):
        assert leaked not in out
    record = json.loads(out.strip())
    assert record["password"] == "***"
    assert record["authorization"] == "***"
    assert record["db_password"] == "***"
    assert record["jwt_token"] == "***"
    assert record["payload"] == {"client_secret": "***", "keep": "ok"}


@pytest.mark.kiwi_id(63)
def test_redaction_connection_string(capsys: pytest.CaptureFixture[str]) -> None:
    """脱敏：连接串密码正则（含嵌套值），用户名保留。"""
    configure_logging(_settings("json"))
    get_logger("app.test").info(
        "db_connect",
        url="mysql+aiomysql://bms:CONN-SECRET@10.0.0.1:3306/bms",
        nested={"dsn": "postgresql://user:NESTED-SECRET@db:5432/x"},
    )
    out = capsys.readouterr().out
    assert "CONN-SECRET" not in out
    assert "NESTED-SECRET" not in out
    record = json.loads(out.strip())
    assert record["url"] == "mysql+aiomysql://bms:***@10.0.0.1:3306/bms"
    assert record["nested"] == {"dsn": "postgresql://user:***@db:5432/x"}


@pytest.mark.kiwi_id(63)
def test_redaction_depth_limit_keeps_value() -> None:
    """超深嵌套（达到限深）原样返回，避免递归放大。"""
    from bms_core.core.logging import _MAX_REDACT_DEPTH, _redact_value  # pyright: ignore[reportPrivateUsage]

    payload: dict[str, object] = {"inner": "postgresql://u:p@h/db"}
    assert _redact_value(payload, depth=_MAX_REDACT_DEPTH) is payload


@pytest.mark.kiwi_id(63)
def test_stdlib_logger_rendered_and_access_disabled(capsys: pytest.CaptureFixture[str]) -> None:
    """stdlib 日志统一渲染；uvicorn.access 关闭。"""
    configure_logging(_settings("json"))
    logging.getLogger("sqlalchemy.engine").warning("db slow")
    record = _records(capsys)[0]
    assert record["event"] == "db slow"
    assert record["level"] == "warning"
    assert record["logger"] == "sqlalchemy.engine"
    assert logging.getLogger("uvicorn.access").disabled is True
