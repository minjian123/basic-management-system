"""日志基座测试（Kiwi 34 结构回归 + Kiwi 63 日志体系）。"""

import json
import logging
import threading
from typing import Literal

import pytest
import structlog

from bms_core.core.base import BaseObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
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


def _records(capsys: pytest.CaptureFixture[str]) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """读取 stdout 并按 JSON 行解析（忽略空行）。"""
    return ConcurrentStableList(
        ConcurrentStableDict(json.loads(line)) for line in capsys.readouterr().out.splitlines() if line.strip()
    )


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


@pytest.mark.kiwi_id(2225)
def test_redaction_config_extends_builtin_lists(capsys: pytest.CaptureFixture[str]) -> None:
    """配置追加键名与后缀生效（值整体 `***`）；内置名单恒生效（配置只可追加不可移除）。"""
    configure_logging(
        Settings(
            log=LogSettings(
                level="INFO",
                format="json",
                redact_keys=ConcurrentStableList(["device_sn"]),
                redact_suffixes=ConcurrentStableList(["__key"]),
            )
        )
    )
    get_logger("app.test").info(
        "custom_redact",
        device_sn="SN-VALUE",
        api__key="KEY-VALUE",
        password="PWD-VALUE",
        keep="ok",
    )
    out = capsys.readouterr().out
    for leaked in ("SN-VALUE", "KEY-VALUE", "PWD-VALUE"):
        assert leaked not in out
    record = json.loads(out.strip())
    assert record["device_sn"] == "***"
    assert record["api__key"] == "***"
    assert record["password"] == "***"
    assert record["keep"] == "ok"


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
    from bms_core.core.logging import (  # pyright: ignore[reportPrivateUsage]
        _MAX_REDACT_DEPTH,  # pyright: ignore[reportPrivateUsage]
        _SENSITIVE_KEYS,  # pyright: ignore[reportPrivateUsage]
        _SENSITIVE_SUFFIXES,  # pyright: ignore[reportPrivateUsage]
        _redact_value,  # pyright: ignore[reportPrivateUsage]
    )

    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict({"inner": "postgresql://u:p@h/db"})
    assert (
        _redact_value(
            payload,
            _MAX_REDACT_DEPTH,
            ConcurrentStableSet(_SENSITIVE_KEYS),
            _SENSITIVE_SUFFIXES,  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定
        )
        is payload
    )


@pytest.mark.kiwi_id(63)
def test_render_switch_not_sticky_for_used_logger(capsys: pytest.CaptureFixture[str]) -> None:
    """重配渲染形态**即时生效**：已使用过的 logger 不得粘滞旧形态（首用缓存回归）。

    `cache_logger_on_first_use=True` 会把首次使用时的配置粘在 logger 上——先 `console` 用一次、
    再改 `json`，后续日志仍按 console 渲染；本用例锁定「关缓存」口径（顺序敏感的偶发失败根因）。
    """
    configure_logging(_settings("console"))
    get_logger("sticky_render").info("first")
    configure_logging(_settings("json"))
    get_logger("sticky_render").info("second")
    lines = capsys.readouterr().out.splitlines()
    assert any(line.lstrip().startswith("{") for line in lines), lines


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


@pytest.mark.kiwi_id(63)
def test_foreign_pre_chain_is_immutable_snapshot() -> None:
    """日志格式化热路径零锁：`foreign_pre_chain` 必须为不可变快照（挂起缺陷回归）。

    原实现把并发集合（处理器链）直接挂到 `ProcessorFormatter.foreign_pre_chain`——
    每条第三方 stdlib 日志格式化都要取该集合的全局锁；持锁线程内的同步回调（如 GC
    终结器嵌套打日志）再入同一把锁即自锁死（2026-10-16 偶发挂起）。快照化后不再触碰。
    """
    configure_logging(_settings("json"))
    handler = next(h for h in logging.getLogger().handlers if getattr(h, "_bms_structlog", False))
    formatter = handler.formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    # structlog 的 `foreign_pre_chain` 元素类型不可解析（pyright partially unknown），经 `__getattribute__` 规避
    chain = object.__getattribute__(formatter, "foreign_pre_chain")
    assert type(chain) is tuple and chain  # 不可变快照且非空


@pytest.mark.kiwi_id(63)
def test_redact_suffix_snapshot_detached_from_source() -> None:
    """脱敏后缀名单在构建时快照：构建后追加源集合不影响生效名单（热路径不读取源集合）。"""
    from bms_core.core.logging import (  # pyright: ignore[reportPrivateUsage]
        _SENSITIVE_KEYS,  # pyright: ignore[reportPrivateUsage]
        _build_redact_processor,  # pyright: ignore[reportPrivateUsage]
    )

    suffixes = ConcurrentStableList(["__secret"])
    redact = _build_redact_processor(ConcurrentStableSet(_SENSITIVE_KEYS), suffixes)
    suffixes.add("__late")  # 构建后追加：快照语义下不参与脱敏
    event = {"event": "login", "field__secret": "A", "field__late": "B"}
    redacted = redact(None, "bms", event)
    assert redacted["field__secret"] == "***"
    assert redacted["field__late"] == "B"


@pytest.mark.kiwi_id(63)
def test_redact_processor_does_not_acquire_source_collection_lock() -> None:
    """脱敏处理器与源集合锁解耦：源集合持写锁期间处理器仍即时完成（同线程再入挂起回归）。

    模拟「同线程在源集合锁内触发 GC → 终结器嵌套打日志 → 再入该锁」场景：处理器若仍
    读取源集合（原实现每次格式化都遍历 `ConcurrentStableList`、取全局写锁）将被阻塞。
    """
    from bms_core.core.logging import (  # pyright: ignore[reportPrivateUsage]
        _SENSITIVE_KEYS,  # pyright: ignore[reportPrivateUsage]
        _build_redact_processor,  # pyright: ignore[reportPrivateUsage]
    )

    suffixes = ConcurrentStableList(["__secret"])
    redact = _build_redact_processor(ConcurrentStableSet(_SENSITIVE_KEYS), suffixes)
    done = threading.Event()

    def run_redact() -> None:
        redacted = redact(None, "bms", {"event": "login", "field__secret": "v"})
        assert redacted["field__secret"] == "***"
        done.set()

    thread = threading.Thread(target=run_redact, daemon=True)
    with suffixes._global.write():  # pyright: ignore[reportPrivateUsage]  # 源集合进入「持写锁」状态
        thread.start()
        assert done.wait(5)
    thread.join(5)
