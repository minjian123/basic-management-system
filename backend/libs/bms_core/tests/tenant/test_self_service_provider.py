"""租户自助依赖提供者护栏（Kiwi 2557）：优先取应用装配实例，无则回退插件解析。

背景（13_11 / 13_10 §14.6）：插件注册表是进程级「最后登记者生效」，多服务同进程装配时
`resolve_plugin` 会返回别家应用绑定的实例（租户请求用到 txn 的关系数据源 → 远端契约 401）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.tenant import base as tenant_base
from bms_core.tenant.null import NullTenantSelfService

pytestmark = pytest.mark.kiwi_id(2557)


def _request(app: object) -> Request:
    """构造只带 `app` 的最小请求（提供者只读应用状态）。"""
    return Request({"type": "http", "app": app, "headers": []})


def test_prefers_assembled_instance_and_skips_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用状态上有装配实例时直接返回，不再走进程级插件解析。"""
    assembled = NullTenantSelfService()
    app = cast("FastAPI", SimpleNamespace(state=SimpleNamespace(settings=Settings(), tenant_self_service=assembled)))
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def _should_not_call(*args: object, **kwargs: object) -> object:
        """记录误调用（不应发生）。"""
        del args, kwargs
        seen.add("called")
        return assembled

    monkeypatch.setattr(tenant_base, "resolve_plugin", _should_not_call)
    assert tenant_base.get_tenant_self_service(_request(app)) is assembled
    assert list(seen) == []


def test_falls_back_to_plugin_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用状态上没有实例（单测自带壳 / 未装配）时回退插件解析。"""
    sentinel = NullTenantSelfService()
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    app = cast("FastAPI", SimpleNamespace(state=SimpleNamespace(settings=Settings())))

    def _fake_resolve(key: str, name: str, *, expected_version: str | None = None) -> object:
        """替身解析：记录 key 与实现名。"""
        del expected_version
        seen.add(f"{key}:{name}")
        return sentinel

    monkeypatch.setattr(tenant_base, "resolve_plugin", _fake_resolve)
    assert tenant_base.get_tenant_self_service(_request(app)) is sentinel
    assert list(seen) == [f"tenant_self_service:{Settings().tenant_self_service.provider}"]
