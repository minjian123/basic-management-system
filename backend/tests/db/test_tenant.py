"""多租户解析测试（Kiwi 27）：解析链 / 豁免 / 依赖 / 租户模型。"""

from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.errors import register_exception_handlers
from app.core.exceptions import OpenTenantError, TenantNotFoundError
from app.db.tenant import DEMO_TENANT, TenantContext, get_tenant, is_exempt_path, resolve_tenant
from app.models.base import Base
from app.models.platform import SysTenant


@pytest.mark.kiwi_id(27)
def test_resolve_chain_and_fallback() -> None:
    """解析链：子域名 / 请求头 / token 命中 demo；无来源回落 demo。"""
    assert resolve_tenant(host="demo.bms.example.com") == DEMO_TENANT
    assert resolve_tenant(header="demo") == DEMO_TENANT
    assert resolve_tenant(token_tenant="demo") == DEMO_TENANT
    assert resolve_tenant(host="demo.bms.example.com", header="other") == DEMO_TENANT
    assert resolve_tenant(host="test") == DEMO_TENANT
    assert resolve_tenant() == DEMO_TENANT


@pytest.mark.kiwi_id(27)
def test_resolve_unknown_tenant() -> None:
    """未知租户：404 / 80001，属 8xxxx 段位。"""
    with pytest.raises(TenantNotFoundError) as excinfo:
        resolve_tenant(header="nope")
    assert excinfo.value.http_status == 404
    assert excinfo.value.code == 80001
    assert isinstance(excinfo.value, OpenTenantError)


@pytest.mark.kiwi_id(27)
def test_is_exempt_path() -> None:
    """豁免路径判定。"""
    assert is_exempt_path("/healthz") is True
    assert is_exempt_path("/api/v1/modules") is False


@pytest.mark.kiwi_id(27)
async def test_get_tenant_dependency() -> None:
    """依赖：豁免路径放行；命中解析；未知 404 / 80001。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/who")
    async def who(tenant: Annotated[TenantContext | None, Depends(get_tenant)]) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"tenant": tenant.tenant_code if tenant else None}

    @app.get("/healthz")
    async def health(tenant: Annotated[TenantContext | None, Depends(get_tenant)]) -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        return {"tenant": tenant.tenant_code if tenant else None}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/who", headers={"X-Tenant-ID": "demo"})).json() == {"tenant": "demo"}
        assert (await client.get("/who")).json() == {"tenant": "demo"}
        assert (await client.get("/healthz")).json() == {"tenant": None}
        unknown = await client.get("/who", headers={"X-Tenant-ID": "nope"})
        assert unknown.status_code == 404
        assert unknown.json()["code"] == 80001


@pytest.mark.kiwi_id(27)
def test_sys_tenant_declared_and_persistable(tmp_path: Path) -> None:
    """`sys_tenant` 声明：建表 / 字段 / 唯一约束可用。"""
    assert "sys_tenant" in Base.metadata.tables
    engine = create_engine(f"sqlite:///{tmp_path / 'tenant.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tenant = SysTenant(
            code="demo",
            name="演示租户",
            domain="demo.bms.example.com",
            db_key="tenant_demo",
        )
        session.add(tenant)
        session.commit()
        assert tenant.id > 0
    engine.dispose()
