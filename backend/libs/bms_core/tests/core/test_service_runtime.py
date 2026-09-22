"""服务运行时基座测试：身份解析 / 日志绑定 / 停机摘流（Kiwi 1205）。"""

from typing import cast

import pytest
import structlog
from fastapi import FastAPI
from structlog.typing import WrappedLogger

from bms_core.core.config import Settings
from bms_core.core.logging import _build_processors  # pyright: ignore[reportPrivateUsage]
from bms_core.core.service import (
    ServiceIdentity,
    ServiceRuntime,
    attach_service,
    bind_service_identity,
)


@pytest.mark.kiwi_id(1205)
def test_identity_resolves_declared_and_writes_back() -> None:
    """配置为空：身份取服务包声明并回写 `settings.app.service`。"""
    settings = Settings()
    assert settings.app.service == ""
    app = FastAPI()
    runtime = attach_service(app, declared_name="payment", version="1.2.3", title="收付款", settings=settings)
    assert runtime.identity == ServiceIdentity(name="payment", version="1.2.3", title="收付款")
    assert settings.app.service == "payment"
    assert app.state.service_identity.name == "payment"
    assert app.state.draining is False
    structlog.contextvars.clear_contextvars()


@pytest.mark.kiwi_id(1205)
def test_identity_config_overrides_declared() -> None:
    """配置非空：以配置为准，不回写。"""
    settings = Settings()
    settings.app.service = "custom"
    app = FastAPI()
    runtime = attach_service(app, declared_name="payment", version="1.2.3", settings=settings)
    assert runtime.identity.name == "custom"
    assert settings.app.service == "custom"
    structlog.contextvars.clear_contextvars()


@pytest.mark.kiwi_id(1205)
def test_bind_service_identity_feeds_log_processors() -> None:
    """身份写入 structlog 上下文，处理器链 `merge_contextvars` 将其并入事件字典。"""
    bind_service_identity(ServiceIdentity(name="platform", version="0.1.0"))
    assert structlog.contextvars.get_contextvars()["service"] == "platform"
    assert structlog.contextvars.get_contextvars()["service_version"] == "0.1.0"
    processors = _build_processors()
    assert structlog.contextvars.merge_contextvars in processors
    event = structlog.contextvars.merge_contextvars(cast(WrappedLogger, None), "info", {"event": "x"})
    assert event["service"] == "platform"
    assert event["service_version"] == "0.1.0"
    structlog.contextvars.clear_contextvars()


@pytest.mark.kiwi_id(1205)
def test_start_drain_idempotent() -> None:
    """停机摘流：置 draining 与取消就绪，重复调用幂等。"""
    app = FastAPI()
    app.state.startup_complete = True
    runtime = ServiceRuntime(app, ServiceIdentity(name="platform", version="0.1.0"))
    assert runtime.draining is False
    runtime.start_drain()
    assert runtime.draining is True
    assert app.state.startup_complete is False
    runtime.start_drain()
    assert runtime.draining is True
