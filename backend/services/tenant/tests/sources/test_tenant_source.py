"""租户源测试（Kiwi 1019）：平台库取数 / 缓存命中与失效 / 未知与停用 / 强制回收。"""

from types import SimpleNamespace

import pytest

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import MultipleActiveTenantsError, TenantNotFoundError, TenantSuspendedError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.tenant_registry import snapshot_cache_key
from bms_core.db.tenant_source import build_tenant_lookup, registered_tenant_sources
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.sources.tenant_source import (
    LOCAL_TENANT_SOURCE,
    LocalTenantSource,
    register_local_tenant_source,
)
from tests_support.tenant_base import TenantBase

pytestmark = pytest.mark.kiwi_id(1019)


@pytest.fixture
def platform_url(tenant_base: TenantBase) -> str:
    """共享平台库连接串（基础租户集合由 `tenant_base` 提交入库，两个文件共用）。

    Args:
        tenant_base: 共享平台库上的基础数据集。

    Returns:
        str: 共享平台库连接串。
    """
    return tenant_base.url


def _source(url: str, *, cache: CacheRegion | None = None) -> tuple[LocalTenantSource, EngineRegistry]:
    """构造租户源与引擎注册表（平台库指向临时文件）。"""
    settings = Settings()
    settings.database.platform.url = url
    registry = EngineRegistry(EngineFactory(settings))
    return LocalTenantSource(registry, cache=cache, cache_ttl=60), registry


@pytest.mark.kiwi_id(1019)
async def test_lookup_by_code_and_domain(platform_url: str) -> None:
    """按编码 / 子域名命中注册记录；上下文携带主键 / 状态 / 域名。"""
    source, registry = _source(platform_url)
    try:
        demo = await source.by_code("demo")
        assert demo.code == "demo"
        assert demo.db_key == "tenant_demo"
        assert demo.name == "演示租户"
        assert demo.tenant_id is not None
        assert demo.status == "active"

        acme = await source.by_domain("acme.bms.example.com")
        assert acme.code == "acme"
        assert acme.domain == "acme.bms.example.com"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
@pytest.mark.kiwi_id(2219)
async def test_db_basis_from_ledger_keeps_db_key_stable(platform_url: str) -> None:
    """库名基取对照表 `db_basis`：租户改名后库键不变（code 变更不断链）。"""
    source, registry = _source(platform_url)
    try:
        renamed = await source.by_code("renamed")
        assert renamed.code == "renamed"
        assert renamed.db_key == "tenant_orig"

        acme = await source.by_code("acme")  # 无对照行：回落当前 code
        assert acme.db_key == "tenant_acme"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_unknown_and_soft_deleted_rejected(platform_url: str) -> None:
    """未知租户 / 软删除租户：404 / 80001。"""
    source, registry = _source(platform_url)
    try:
        with pytest.raises(TenantNotFoundError) as unknown:
            await source.by_code("nope")
        assert unknown.value.http_status == 404
        assert unknown.value.code == 80001

        with pytest.raises(TenantNotFoundError):
            await source.by_code("gone")
        with pytest.raises(TenantNotFoundError):
            await source.by_domain("nope.bms.example.com")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_suspended_tenant_released_and_rejected(platform_url: str) -> None:
    """停用租户：403 / 80002 且该租户引擎被强制回收。"""
    source, registry = _source(platform_url)
    try:
        assert await registry.get("tenant_sosp") is not None
        assert "tenant_sosp" in registry.active_keys()
        with pytest.raises(TenantSuspendedError) as suspended:
            await source.by_code("sosp")
        assert suspended.value.http_status == 403
        assert suspended.value.code == 80002
        assert "tenant_sosp" not in registry.active_keys()
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_cache_hit_and_invalidate(platform_url: str, tenant_base: TenantBase) -> None:
    """缓存命中减少平台库查询；`invalidate` 后重查。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    try:
        await tenant_base.seed(code="cache-hit", name="缓存用例租户", domain="cachehit.bms.example.com")
        await tenant_base.session.commit()
        first = await source.by_code("cache-hit")
        assert first.tenant_id is not None

        await tenant_base.delete_row("cache-hit")
        await tenant_base.session.commit()

        cached = await source.by_code("cache-hit")
        assert cached.tenant_id == first.tenant_id

        await source.invalidate(code="cache-hit")
        with pytest.raises(TenantNotFoundError):
            await source.by_code("cache-hit")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_multiple_raises(platform_url: str) -> None:
    """唯一启用租户：≥ 2 个启用租户 → `80004`（不返回清单）。"""
    source, registry = _source(platform_url)
    try:
        with pytest.raises(MultipleActiveTenantsError) as exc:
            await source.single_active()
        assert exc.value.code == 80004 and exc.value.http_status == 409
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_exactly_one(platform_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """唯一启用租户：恰 1 个启用行 → 返回其上下文（含库名基 / 主键）。

    共享平台库里本来就有多个启用租户（业务现实），「恰 1 个」不可能真实存在；在共享库上
    人为造这个态等于篡改业务数据，故用仓储替身只验 resolver 的分支语义。
    """
    row = SimpleNamespace(
        id=1,
        code="demo",
        name="演示租户",
        domain="demo.bms.example.com",
        db_key="tenant_demo",
        status="active",
        expire_at=None,
    )
    monkeypatch.setattr(TenantRegistryRepository, "active_rows", _rows_of(row))
    monkeypatch.setattr(TenantRegistryRepository, "db_basis", _basis_of("demo"))
    source, registry = _source(platform_url)
    try:
        single = await source.single_active()
        assert single is not None
        assert single.code == "demo" and single.db_key == "tenant_demo" and single.tenant_id is not None
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_none(platform_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """唯一启用租户：0 个启用行 → `None`（沿用既有失败语义由调用方映射）。

    同「恰 1 个」：共享库上不存在「全平台零启用租户」的真实态，用仓储替身验分支。
    """
    monkeypatch.setattr(TenantRegistryRepository, "active_rows", _rows_of())
    source, registry = _source(platform_url)
    try:
        assert await source.single_active() is None
    finally:
        await registry.aclose()


def _rows_of(*rows: object) -> object:
    """构造 `active_rows` 的替身（返回固定行集合）。

    Args:
        *rows: 行对象。

    Returns:
        object: 可调用替身（签名与仓储方法一致）。
    """

    async def _call(self: object) -> object:
        del self
        return list(rows)

    return _call


def _basis_of(basis: str | None) -> object:
    """构造 `db_basis` 的替身（返回固定库名基）。

    Args:
        basis: 库名基。

    Returns:
        object: 可调用替身。
    """

    async def _call(self: object, tenant_id: int) -> str | None:
        del self, tenant_id
        return basis

    return _call


@pytest.mark.kiwi_id(1019)
async def test_no_cache_direct_query(platform_url: str) -> None:
    """无缓存实现（null / 未装配）时直查平台库，不阻断。"""
    source, registry = _source(platform_url)
    try:
        assert (await source.by_code("acme")).code == "acme"
        await source.invalidate(code="acme", domain="acme.bms.example.com")
        await source.invalidate()  # 无键失效：空操作
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
@pytest.mark.kiwi_id(2176)
async def test_bump_version_invalidates_cache(platform_url: str) -> None:
    """写路径递增版本号：缓存陈旧重载（内存域经 `bump_version`，Redis 域经域内版本键）。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    try:
        await source.by_code("demo")
        assert cache.get(snapshot_cache_key("code", "demo")) is not None
        version_before = cache.get_global_version()

        source.bump_version()
        assert cache.get_global_version() == version_before + 1
        await source.by_code("demo")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2176)
async def test_invalidate_by_domain(platform_url: str) -> None:
    """按域名单键失效覆盖 `if domain` 分支（缓存实现缺省 null 时空操作）。"""
    source, registry = _source(platform_url)
    try:
        await source.by_code("demo")
        await source.invalidate(domain="demo.bms.example.com")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_lookup_by_id_and_invalid_id(platform_url: str) -> None:
    """按主键取上下文：十进制字符串命中；非数字主键直接判未知（不走库查询）。"""
    source, registry = _source(platform_url)
    try:
        demo = await source.by_code("demo")
        assert demo.tenant_id is not None

        by_id = await source.by_id(str(demo.tenant_id))
        assert by_id.code == "demo" and by_id.tenant_id == demo.tenant_id

        with pytest.raises(TenantNotFoundError):
            await source.by_id("not-a-number")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_cache_get_ignores_payload_without_code(platform_url: str) -> None:
    """缓存载荷缺 `code`（形态非法）：视为未命中并回源平台库，不抛错。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    try:
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        payload.set("version", cache.get_global_version())
        cache.set(snapshot_cache_key("code", "demo"), payload, 60)

        demo = await source.by_code("demo")
        assert demo.code == "demo"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2176)
async def test_bump_version_without_cache_is_noop(platform_url: str) -> None:
    """无缓存实现时递增版本号为空操作（不阻断写路径）。"""
    source, registry = _source(platform_url)
    try:
        source.bump_version()
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2176)
async def test_bump_version_falls_back_to_version_key(platform_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """缓存实现无 `bump_version` 时经域内版本键写回「当前值 + 1」。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    monkeypatch.delattr(MemoryCacheRegion, "bump_version")
    try:
        source.bump_version()
        assert cache.get(cache.build_key("version")) == 1
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
def test_register_local_tenant_source_factory(platform_url: str) -> None:
    """登记工厂：`local` 已登记且按 `[tenant].resolve_cache_ttl` 装配缓存 TTL。"""
    settings = Settings()
    settings.database.platform.url = platform_url
    settings.tenant.resolve_cache_ttl = 77
    registry = EngineRegistry(EngineFactory(settings))
    cache = MemoryCacheRegion(domain="tenant")
    register_local_tenant_source()

    assert LOCAL_TENANT_SOURCE in registered_tenant_sources()
    built = build_tenant_lookup(
        LOCAL_TENANT_SOURCE,
        settings=settings,
        registry=registry,
        cache=cache,
        session_factory=None,
    )
    assert isinstance(built, LocalTenantSource)
    assert built.cache is cache
    assert built._cache_ttl == 77  # pyright: ignore[reportPrivateUsage]
