"""`bms_tenant` 服务入口用例：ASGI 模块级应用、`python -m` 启动入口、常规导入分流与配置钩子。"""

from __future__ import annotations

import runpy
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.tenant.base import TENANT_SELF_SERVICE_DB_PROVIDER
from bms_tenant.main import ApplicationFactory
from tests_support.service_entrypoints import load_entrypoint_source


def test_asgi_module_exposes_application() -> None:
    """ASGI 入口：`uvicorn bms_tenant.asgi:app` 所需模块级应用实例就位。"""
    from bms_tenant.asgi import app

    assert app.title


def test_module_source_does_not_run_service() -> None:
    """以非 `__main__` 名字执行入口模块：不触发启动（`__name__ != "__main__"` 分支）。"""
    assert load_entrypoint_source("bms_tenant") == "bms_tenant._entrypoint_probe"


def test_module_entrypoint_runs_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动入口：`python -m bms_tenant` 经 `run_service` 拉起应用工厂。"""
    calls: ConcurrentStableList[Any] = ConcurrentStableList()

    def _stub(factory: Any) -> None:
        calls.add(factory)

    monkeypatch.setattr("bms_core.core.run.run_service", _stub)
    runpy.run_module("bms_tenant", run_name="__main__", alter_sys=True)

    assert list(calls) == [ApplicationFactory]


def test_prepare_settings_skips_when_service_name_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置钩子：`service_name` 非本服务时不改写租户自助实现。"""
    factory = ApplicationFactory()
    monkeypatch.setattr(factory, "service_name", "other-service")
    settings = Settings()

    factory.prepare_settings(settings)

    assert settings.tenant_self_service.provider != TENANT_SELF_SERVICE_DB_PROVIDER
