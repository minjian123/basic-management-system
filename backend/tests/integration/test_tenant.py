"""集成测试：租户解析（X-Tenant-ID 请求头、非法租户拒绝、平台请求免解析）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_tenant_header_routes_request(client: TestClient) -> None:
    """携带 X-Tenant-ID 的请求正常通过（租户级请求）。"""
    response = client.get("/api/v1/system/info", headers={"X-Tenant-ID": "demo"})
    assert response.status_code == 200
    assert response.json()["code"] == 0


def test_invalid_tenant_rejected(client: TestClient) -> None:
    """非法租户标识返回 400 + 统一错误响应（80001）。"""
    response = client.get("/api/v1/system/info", headers={"X-Tenant-ID": "BAD NAME"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == 80001
    assert body["data"] is None


def test_platform_request_without_tenant(client: TestClient) -> None:
    """平台级请求（无 X-Tenant-ID）正常通过，不强制租户。"""
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200


def test_healthz_skips_tenant_parse(client: TestClient) -> None:
    """健康检查路径不经过租户解析（非法租户头也不影响探针）。"""
    response = client.get("/healthz", headers={"X-Tenant-ID": "BAD NAME"})
    assert response.status_code == 200


def test_unknown_route_returns_unified_404(client: TestClient) -> None:
    """未注册路由返回统一错误响应（10003）。"""
    response = client.get("/api/v1/not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == 10003


def test_request_id_header_echoed(client: TestClient) -> None:
    """响应回带 X-Request-ID（沿用客户端值）。"""
    response = client.get("/healthz", headers={"X-Request-ID": "req-abc"})
    assert response.headers.get("X-Request-ID") == "req-abc"
