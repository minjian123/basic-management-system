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
    is_local_hostname,
    is_tenant_code,
    is_tenant_domain,
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
    """带租户前缀主机名提取（≥三段合法域名、去端口；IP / 本机名不入解析）与豁免路径。"""
    assert tenant_hostname("demo.bms.example.com") == "demo.bms.example.com"
    assert tenant_hostname("demo.bms.example.com:8000") == "demo.bms.example.com"
    assert tenant_hostname("example.com") is None
    assert tenant_hostname("test") is None
    assert tenant_hostname(None) is None

    # IP 字面量 / 本机名不是租户域名（06_04：dev / CI / Compose 直连一律为 IP 或 localhost）
    assert tenant_hostname("127.0.0.1:8000") is None
    assert tenant_hostname("10.0.0.5") is None
    assert tenant_hostname("[::1]:8000") is None
    assert tenant_hostname("localhost:8000") is None
    assert tenant_hostname("localhost.localdomain") is None
    # 形态非法的域名同样不入解析（避免派生非法库名）
    assert tenant_hostname("demo..bms.example.com") is None
    assert tenant_hostname("-demo.bms.example.com") is None
    assert tenant_hostname("demo_bms_example_com") is None

    assert is_exempt_path("/healthz") is True
    assert is_exempt_path("/api/v1/modules") is False
    assert is_exempt_path("/healthz", ("/health",)) is False


@pytest.mark.kiwi_id(1019)
def test_source_value_shape_validation() -> None:
    """来源值形态校验：编码 / 域名 / 本机名判定（形态非法一律视为未命中）。"""
    assert is_tenant_code("demo") is True
    assert is_tenant_code("acme_corp") is True
    assert is_tenant_code("127.0.0.1") is False
    assert is_tenant_code("demo.example.com") is False
    assert is_tenant_code("1demo") is False
    assert is_tenant_code("-demo") is False
    assert is_tenant_code("") is False
    assert is_tenant_code("x" * 65) is False

    assert is_tenant_domain("demo.bms.example.com") is True
    assert is_tenant_domain("example.com") is True
    assert is_tenant_domain("localhost") is False
    assert is_tenant_domain("127.0.0.1") is True  # 形态像域名，但由 is_local_hostname 排除
    assert is_tenant_domain("demo..example.com") is False

    assert is_local_hostname("127.0.0.1") is True
    assert is_local_hostname("::1") is True
    assert is_local_hostname("localhost") is True
    assert is_local_hostname("") is True
    assert is_local_hostname("demo.bms.example.com") is False

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
async def test_malformed_sources_treated_as_absent() -> None:
    """形态非法的来源值等同未提供（不送入租户源）：dev 回落演示租户、prod 拒绝 4xx。

    回归护栏（06_04）：`Host` 为 IP（dev / CI / Compose 直连形态）与非法 `X-Tenant-ID` 均不得
    触发取数与库键派生，从而不产生「库名形态非法」类 5xx。
    """
    demo = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")
    source = _RecordingSource({"demo": demo})

    hit = await resolve_request_tenant(path="/api/v1/x", host="127.0.0.1:8000", source=source)
    assert hit == demo
    assert source.calls == [("code", "demo")]  # 仅兜底取演示租户；IP 未进子域名解析

    hit = await resolve_request_tenant(path="/api/v1/x", host="localhost:8000", header="127.0.0.1", source=source)
    assert hit == demo
    assert source.calls[-1] == ("code", "demo")

    # prod 口径（关闭回落）：形态非法来源等同无来源 → 4xx（不冒泡 5xx）
    calls = len(source.calls)
    with pytest.raises(TenantNotFoundError):
        await resolve_request_tenant(
            path="/api/v1/x",
            host="127.0.0.1:8000",
            token_tenant="demo.example.com",
            source=source,
            allow_demo_fallback=False,
        )
    assert len(source.calls) == calls  # 非法来源未送入取数


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
