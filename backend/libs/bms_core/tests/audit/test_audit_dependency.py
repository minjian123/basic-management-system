"""审计捕获依赖提供者（`get_audit_capturer`）：按装配配置解析插件实例。

覆盖 `audit/base.py::get_audit_capturer` 的两条路径：装配 provider 已配置（透传 provider + 契约版本）、
provider 未配置（透传 None ⇒ 由插件族回落 `null` 实现）。07C `04_03` 起审计事件要求 `payload.domain_key`，
本用例只锁定依赖解析口径（域标注由 `tests/audit/test_hashchain.py` 覆盖）。
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from bms_core.audit import base as audit_base
from bms_core.audit.null import NullAuditCapturer
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION


def _request(provider: str | None) -> Request:
    """构造只带装配配置的最小请求（依赖函数只读 `request.app.state.settings`）。

    Args:
        provider: `[audit].provider` 取值（None 表示未配置）。

    Returns:
        Request: 请求对象（类型标注用，实质为最小替身）。
    """
    settings = SimpleNamespace(audit=SimpleNamespace(provider=provider))
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return cast("Request", SimpleNamespace(app=app))


@pytest.mark.parametrize("provider", ["hashchain", None])
def test_get_audit_capturer_passes_provider_and_contract_version(
    monkeypatch: pytest.MonkeyPatch, provider: str | None
) -> None:
    """依赖提供者：按装配 provider 与契约版本解析，并原样返回实现实例。"""
    captured: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    sentinel = NullAuditCapturer()

    def _fake_resolve(key: str, provider_name: str | None = None, *, expected_version: str | None = None) -> object:
        """替身：记录解析入参并返回固定实现。

        Args:
            key: 能力域键。
            provider_name: 实现名。
            expected_version: 期望契约版本。

        Returns:
            object: 固定实现（空审计捕获器）。
        """
        captured.set("key", key)
        captured.set("provider", provider_name)
        captured.set("version", expected_version)
        return sentinel

    monkeypatch.setattr(audit_base, "resolve_plugin", _fake_resolve)

    assert audit_base.get_audit_capturer(_request(provider)) is sentinel
    assert dict(captured) == {
        "key": "audit",
        "provider": provider,
        "version": DEFAULT_CONTRACT_VERSION,
    }
