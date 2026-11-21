"""消费器框架对象归位与退化租户目录（基座体系 §3.1，Kiwi 2535）。"""

from __future__ import annotations

import pytest

from bms_core.core.objects import BaseFrameworkObject
from bms_core.events.msg_consumer import PlatformOnlyTenantDirectory

pytestmark = pytest.mark.kiwi_id(2535)


async def test_platform_only_directory_is_framework_object() -> None:
    """退化租户目录归位框架对象体系，只返回平台租户。"""
    directory = PlatformOnlyTenantDirectory("platform")
    assert isinstance(directory, BaseFrameworkObject)
    contexts = await directory.active_tenants()
    assert [context.code for context in contexts] == ["platform"]


async def test_platform_only_directory_falls_back_to_platform() -> None:
    """未给平台租户编码时回退 `platform`，库键按租户前缀派生。"""
    contexts = await PlatformOnlyTenantDirectory("").active_tenants()
    assert [(context.code, context.db_key) for context in contexts] == [("platform", "tenant_platform")]
