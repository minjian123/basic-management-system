"""集成测试：健康检查端点（/healthz、/readyz 依赖故障场景）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_healthz_returns_200(client: TestClient) -> None:
    """存活探针：进程存活即 200，不检查依赖。"""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_ok_when_dependencies_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """就绪探针：DB 与 Redis 均就绪时 200。"""
    monkeypatch.setattr("app.api.v1.health.db_check", _fake_db_ok)
    monkeypatch.setattr("app.api.v1.health.redis_ping", _fake_redis_ok)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}


def test_readyz_503_when_redis_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis 停止时 503，恢复后自动转 200（恢复场景由依赖恢复保证）。"""
    monkeypatch.setattr("app.api.v1.health.db_check", _fake_db_ok)
    monkeypatch.setattr("app.api.v1.health.redis_ping", _fake_redis_down)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["redis"] == "unavailable"


def test_readyz_503_when_db_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """平台库不可用时 503，DB 检查项标记 unavailable。"""
    monkeypatch.setattr("app.api.v1.health.db_check", _fake_db_down)
    monkeypatch.setattr("app.api.v1.health.redis_ping", _fake_redis_ok)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"


async def _fake_db_ok() -> bool:
    return True


async def _fake_db_down() -> bool:
    return False


async def _fake_redis_ok() -> bool:
    return True


async def _fake_redis_down() -> bool:
    return False
