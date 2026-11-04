"""作业库键清单用例：平台链 + 租户链、TTL 缓存、关闭平台链。"""

from __future__ import annotations

from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.jobs import keys as job_keys
from bms_core.jobs.keys import JobDbKeys

pytestmark = pytest.mark.kiwi_id(2381)


class _Factory:
    """引擎工厂替身：固定返回注册库连接串。"""

    def resolved_url(self, db_key: str) -> str:
        """返回固定连接串（替身，永不建连；内存库形态避免被读成自建库）。"""
        del db_key
        return "sqlite+aiosqlite://"


class _Ref:
    """租户引用替身。"""

    def __init__(self, basis: str) -> None:
        self.db_basis = basis


async def test_keys_platform_first_then_tenants(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次取清单：平台链在前，租户链按 `db_basis` 派生。"""
    refs = ConcurrentStableList([_Ref("acme"), _Ref("beta")])

    async def fake_refs(url: str) -> ConcurrentStableList[_Ref]:
        del url
        return refs

    monkeypatch.setattr(job_keys, "tenant_refs", fake_refs)
    keys = JobDbKeys(registry_factory=cast("Any", _Factory()), service_key="file", ttl_seconds=60)
    result = await keys()
    assert result[0] == "platform_file"
    assert result[1:] == ["tenant_file_acme", "tenant_file_beta"]


async def test_keys_use_registry_factory_for_tenant_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """租户注册库解析走 `registry_factory`，键为 tenant 单元的平台库（跨读豁免只作用于该工厂）。"""
    seen = ConcurrentStableList[str]()

    class _Recording:
        """记录被解析的库键。"""

        def resolved_url(self, db_key: str) -> str:
            seen.add(db_key)
            return "sqlite+aiosqlite://"

    async def fake_refs(url: str) -> ConcurrentStableList[_Ref]:
        del url
        return ConcurrentStableList([_Ref("acme")])

    monkeypatch.setattr(job_keys, "tenant_refs", fake_refs)
    keys = JobDbKeys(registry_factory=cast("Any", _Recording()), service_key="file", ttl_seconds=60)
    assert await keys() == ["platform_file", "tenant_file_acme"]
    assert seen == ["platform_tenant"]


async def test_keys_cache_hit_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    """TTL 内命中缓存；过期后重新解析。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def fake_refs(url: str) -> ConcurrentStableList[_Ref]:
        calls.append(url)
        return ConcurrentStableList([_Ref("acme")])

    monkeypatch.setattr(job_keys, "tenant_refs", fake_refs)
    keys = JobDbKeys(registry_factory=cast("Any", _Factory()), service_key="file", ttl_seconds=60)
    first = await keys()
    second = await keys()
    assert first == second and len(calls) == 1

    keys._expires_at = 0.0  # pyright: ignore[reportPrivateUsage]  # 模拟过期
    await keys()
    assert len(calls) == 2


async def test_keys_without_platform_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭平台链：清单只含租户链。"""

    async def fake_refs(url: str) -> ConcurrentStableList[_Ref]:
        del url
        return ConcurrentStableList([_Ref("acme")])

    monkeypatch.setattr(job_keys, "tenant_refs", fake_refs)
    keys = JobDbKeys(
        registry_factory=cast("Any", _Factory()), service_key="file", ttl_seconds=60, include_platform_chain=False
    )
    assert await keys() == ["tenant_file_acme"]
