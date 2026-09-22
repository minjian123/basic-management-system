"""多租户上下文与解析编排测试（Kiwi 1019）：键助手 / 解析链 / 豁免 / 上下文。"""

import pytest

from bms_core.core.context import (
    reset_current_tenant,
    reset_tenant_context,
    set_current_tenant,
    set_tenant_context,
)
from bms_core.core.exceptions import ConfigError, TenantNotFoundError
from bms_core.db.tenant import (
    DEMO_TENANT,
    TenantContext,
    build_tenant_db_key,
    current_tenant_context,
    is_exempt_path,
    parse_tenant_db_key,
    resolve_request_tenant,
    tenant_hostname,
)


class _RecordingSource:
    """记账租户源（断言解析链取数与来源类型）。"""

    def __init__(self, tenants: dict[str, TenantContext] | None = None) -> None:
        self.tenants = tenants or {}
        self.calls: list[tuple[str, str]] = []

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户（记账）。"""
        self.calls.append(("code", code))
        tenant = self.tenants.get(code)
        if tenant is None:
            raise TenantNotFoundError(f"未知租户：{code}")
        return tenant

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户（记账）。"""
        self.calls.append(("domain", domain))
        for tenant in self.tenants.values():
            if tenant.domain == domain:
                return tenant
        raise TenantNotFoundError(f"未知租户域名：{domain}")


@pytest.mark.kiwi_id(1019)
def test_tenant_db_key_round_trip() -> None:
    """数据源键派生与反解往返一致；非法键快速失败。"""
    assert build_tenant_db_key("demo") == "tenant_demo"
    assert parse_tenant_db_key("tenant_demo") == "demo"
    with pytest.raises(ConfigError):
        parse_tenant_db_key("platform")
    with pytest.raises(ConfigError):
        parse_tenant_db_key("tenant_")


@pytest.mark.kiwi_id(1019)
def test_tenant_hostname_and_exempt() -> None:
    """带租户前缀主机名提取（≥三段域名、去端口）与豁免路径（精确匹配、可覆盖）。"""
    assert tenant_hostname("demo.bms.example.com") == "demo.bms.example.com"
    assert tenant_hostname("demo.bms.example.com:8000") == "demo.bms.example.com"
    assert tenant_hostname("example.com") is None
    assert tenant_hostname("test") is None
    assert tenant_hostname(None) is None

    assert is_exempt_path("/healthz") is True
    assert is_exempt_path("/api/v1/modules") is False
    assert is_exempt_path("/healthz", ("/health",)) is False


@pytest.mark.kiwi_id(1019)
async def test_resolve_chain_priority_and_kinds() -> None:
    """解析链次序：子域名（按 domain）→ 请求头（按 code）→ token 位（按 code）。"""
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", domain="demo.bms.example.com")
    acme = TenantContext(tenant_code="acme", db_key="tenant_acme", name="示例租户", domain="acme.bms.example.com")
    source = _RecordingSource({"demo": demo, "acme": acme})

    hit = await resolve_request_tenant(
        path="/api/v1/x", host="demo.bms.example.com", header="acme", token_tenant="acme", source=source
    )
    assert hit == demo
    assert source.calls == [("domain", "demo.bms.example.com")]

    hit = await resolve_request_tenant(path="/api/v1/x", header="acme", token_tenant="acme", source=source)
    assert hit == acme
    assert source.calls[-1] == ("code", "acme")

    hit = await resolve_request_tenant(path="/api/v1/x", token_tenant="acme", source=source)
    assert hit == acme
    assert source.calls[-1] == ("code", "acme")

    assert await resolve_request_tenant(path="/healthz", host="demo.bms.example.com", source=source) is None


@pytest.mark.kiwi_id(1019)
async def test_resolve_fallback_and_rejection() -> None:
    """无来源：dev 经租户源取演示租户 / 源不可用回落内置；prod（关闭回落）拒绝。"""
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")
    source = _RecordingSource({"demo": demo})
    hit = await resolve_request_tenant(path="/api/v1/x", source=source)
    assert hit == demo
    assert source.calls == [("code", "demo")]

    builtin = await resolve_request_tenant(path="/api/v1/x", source=None)
    assert builtin == DEMO_TENANT

    empty = _RecordingSource({})
    assert await resolve_request_tenant(path="/api/v1/x", source=empty) == DEMO_TENANT  # 源无 demo 回落内置

    with pytest.raises(TenantNotFoundError):
        await resolve_request_tenant(path="/api/v1/x", source=source, allow_demo_fallback=False)
    with pytest.raises(TenantNotFoundError):
        await resolve_request_tenant(path="/api/v1/x", header="nope", source=source)
    with pytest.raises(TenantNotFoundError):
        await resolve_request_tenant(path="/api/v1/x", header="nope", source=None)


@pytest.mark.kiwi_id(1019)
def test_current_tenant_context_prefers_full_context() -> None:
    """上下文取值：完整上下文优先（含主键）；仅有编码时按编码派生库键；无上下文回落演示租户。"""
    full = TenantContext(tenant_code="acme", db_key="tenant_acme", name="示例租户", tenant_id=7)
    token = set_tenant_context(full)
    assert current_tenant_context() is full
    reset_tenant_context(token)

    code_token = set_current_tenant("acme")
    context = current_tenant_context()
    assert context.tenant_code == "acme"
    assert context.db_key == "tenant_acme"
    assert context.tenant_id is None
    reset_current_tenant(code_token)

    assert current_tenant_context() == DEMO_TENANT
