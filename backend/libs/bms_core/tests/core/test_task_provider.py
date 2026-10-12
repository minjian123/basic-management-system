"""任务调度依赖注入提供者用例（`tasks/base.py`）：经 `app.state.settings` 解析任务实现。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.tasks.base import BaseTask, get_task
from bms_core.tasks.null import NullTask


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身（仅 `app.state.settings` 被读取）。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))


@pytest.mark.kiwi_id(677)
def test_get_task_resolves_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """提供者：按 `settings.task.provider` 解析任务实现，并把契约版本一并校验。"""
    captured: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    def _resolve(plugin_key: str, provider: str | None = None, *, expected_version: str | None = None) -> object:
        captured.set("plugin_key", plugin_key)
        captured.set("provider", provider)
        captured.set("expected_version", expected_version)
        return NullTask()

    monkeypatch.setattr("bms_core.tasks.base.resolve_plugin", _resolve)
    task = get_task(_request(Settings()))

    assert isinstance(task, NullTask)
    assert captured.get("plugin_key") == "task"
    assert captured.get("expected_version") == BaseTask.contract_version
