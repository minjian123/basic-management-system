"""`bms_file` 服务入口用例：ASGI 模块级应用、`python -m` 启动入口与常规导入分流。"""

from __future__ import annotations

import runpy
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_file.main import ApplicationFactory
from tests_support.service_entrypoints import load_entrypoint_source


def test_asgi_module_exposes_application() -> None:
    """ASGI 入口：`uvicorn bms_file.asgi:app` 所需模块级应用实例就位。"""
    from bms_file.asgi import app

    assert app.title


def test_module_source_does_not_run_service() -> None:
    """以非 `__main__` 名字执行入口模块：不触发启动（`__name__ != "__main__"` 分支）。"""
    assert load_entrypoint_source("bms_file") == "bms_file_entrypoint_probe"


def test_module_entrypoint_runs_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动入口：`python -m bms_file` 经 `run_service` 拉起应用工厂。"""
    calls: ConcurrentStableList[Any] = ConcurrentStableList()

    def _stub(factory: Any) -> None:
        calls.add(factory)

    monkeypatch.setattr("bms_core.core.run.run_service", _stub)
    runpy.run_module("bms_file", run_name="__main__", alter_sys=True)

    assert list(calls) == [ApplicationFactory]
