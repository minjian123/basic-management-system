"""dev 环境公开契约端点零 5xx 回归（Kiwi 2187，任务 06_04）。

复现 CI 契约冒烟的被测条件：服务以 `BMS_ENV=dev` 起容器（`config.dev.toml` 启用「每服务每租户」
URL 模板 ⇒ 库名由库键派生）、Schemathesis 经 `http://127.0.0.1:8000` 打真实服务——**Host 为 IP
字面量**。守护的缺陷（GitLab Issue #47）：租户解析曾把 IP 主机名（恰好四段）当带子域名的租户
域名，并在租户注册契约不可达时把该值原样当租户编码，派生库名 `bms_platform_127.0.0.1` 形态非法
→ `ConfigError` 冒泡 500，使 dev 环境 7 个只读端点全数报 5xx、契约冒烟只能保持非阻断。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.config import get_settings
from bms_core.db.migration import BACKEND_ROOT
from bms_core.db.tenant import resolve_request_tenant
from bms_core.services.service_contract import CONTRACTS_DIR, contract_file_name
from bms_platform.main import ApplicationFactory

SMOKE_BASE_URL = "http://127.0.0.1:8000"
"""与 CI 契约冒烟一致的服务地址（Host 为 IP 字面量，正是本回归要覆盖的解析条件）。"""

TENANT_PROBE_PATH = "/api/v1/outbox/dead-letters"
"""租户库只读端点（需租户上下文；dev 环境解析异常时即报 5xx 的典型端点）。"""

EXCLUDED_PATHS = ("/healthz", "/readyz", "/metrics")
"""与 `ops/contract_smoke.py` 一致排除的基础设施端点（探针 / 指标，非业务契约）。"""

PATH_PARAM_VALUE = "smoke1"
"""路径参数占位值（只求命中路由，不求命中业务数据；4xx 视为可达通过）。"""


def _contract_spec(service: str = "platform") -> dict[str, Any]:
    """读公开契约快照（仓库根 `deploy/contracts/<服务>.json`）。

    Args:
        service: 服务标识。

    Returns:
        dict[str, Any]: OpenAPI 文档。
    """
    path = BACKEND_ROOT.parent / CONTRACTS_DIR / contract_file_name(service)
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _fill_path(path: str) -> str:
    """把路径参数替换为占位值。

    Args:
        path: 契约路径模板。

    Returns:
        str: 可请求路径。
    """
    result = path
    while "{" in result:
        start = result.index("{")
        end = result.index("}", start)
        result = result[:start] + PATH_PARAM_VALUE + result[end + 1 :]
    return result


def _required_query(operation: dict[str, Any]) -> str:
    """构造必填查询参数（按 schema 类型取占位值）。

    Args:
        operation: 单个操作定义。

    Returns:
        str: `?a=1&b=x` 形态；无必填参数返回空串。
    """
    parts: list[str] = []
    parameters = cast("list[dict[str, Any]]", operation.get("parameters") or [])
    for parameter in parameters:
        if parameter.get("in") != "query" or not parameter.get("required"):
            continue
        name = str(parameter["name"])
        schema = cast("dict[str, Any]", parameter.get("schema") or {})
        kind = schema.get("type")
        if kind == "integer":
            parts.append(f"{name}=1")
        elif kind == "boolean":
            parts.append(f"{name}=true")
        else:
            parts.append(f"{name}={PATH_PARAM_VALUE}")
    return ("?" + "&".join(parts)) if parts else ""


def _read_operations(spec: dict[str, Any]) -> list[str]:
    """枚举只读（GET）操作的请求地址。

    Args:
        spec: OpenAPI 文档。

    Returns:
        list[str]: 请求地址（相对路径 + 必填查询参数），已剔除基础设施端点。
    """
    targets: list[str] = []
    paths = cast("dict[str, dict[str, Any]]", spec.get("paths") or {})
    for path, item in paths.items():
        operation = cast("dict[str, Any]", item.get("get") or {})
        if not operation or path in EXCLUDED_PATHS:
            continue
        targets.append(_fill_path(path) + _required_query(operation))
    return sorted(targets)


def _clear_tenant_cache(app: FastAPI) -> None:
    """清空应用租户源的进程内缓存（防跨用例残留）。

    Args:
        app: 应用实例。
    """
    cached = getattr(getattr(app.state, "tenant_source", None), "cache", None)
    if isinstance(cached, MemoryCacheRegion):
        cached.clear()


@pytest.fixture
async def dev_template_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[FastAPI]:
    """启用「每服务每租户」模板后的平台应用（复现 CI 镜像内 `config.dev.toml` 的库名派生条件）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        tmp_path: 临时目录（模板落库位置）。

    Yields:
        FastAPI: 经 lifespan 装配的应用实例。
    """
    base = tmp_path / "dev"
    base.mkdir()
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{base}/bms_{{service}}_{{tenant}}.db"
    )
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    get_settings.cache_clear()
    app = ApplicationFactory().create(None)
    _clear_tenant_cache(app)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        _clear_tenant_cache(app)
        get_settings.cache_clear()


@pytest.mark.kiwi_id(2187)
async def test_dev_contract_get_endpoints_have_no_server_error(dev_template_app: FastAPI) -> None:
    """Host 为 IP 字面量时，公开契约全 GET 端点不得出现 5xx（dev 环境契约冒烟口径）。"""
    targets = _read_operations(_contract_spec())
    assert targets, "契约快照未解析到任何 GET 操作"

    transport = ASGITransport(app=dev_template_app)
    async with AsyncClient(transport=transport, base_url=SMOKE_BASE_URL) as client:
        failures: list[str] = []
        for target in targets:
            response = await client.get(target)
            if response.status_code >= 500:
                failures.append(f"{target} → {response.status_code} {response.text[:200]}")
    assert not failures, "dev 环境契约端点出现 5xx：\n" + "\n".join(failures)


@pytest.mark.kiwi_id(2187)
async def test_ip_host_resolves_to_demo_tenant(dev_template_app: FastAPI) -> None:
    """Host 为 IP 字面量时不进子域名解析：租户回落演示租户，且其库键可派生合法库名。"""
    settings = get_settings()
    tenant = await resolve_request_tenant(
        path=TENANT_PROBE_PATH,
        host="127.0.0.1:8000",
        source=dev_template_app.state.tenant_source,
        exempt_paths=settings.tenant.exempt_paths,
        allow_demo_fallback=settings.tenant.allow_demo_fallback,
    )
    assert tenant is not None
    assert tenant.tenant_code == "demo"
    assert tenant.db_key == "tenant_demo"
