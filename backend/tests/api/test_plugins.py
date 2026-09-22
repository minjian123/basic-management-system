"""插件清单接口测试（Kiwi 566）：分组清单 / 明细 / 404 / 不含密钥 / 只读。"""

from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import PluginSelection, Settings
from app.main import ApplicationFactory, lifespan


@pytest.mark.kiwi_id(566)
async def test_list_contract(client: AsyncClient) -> None:
    """分组清单（不写死组数）：`plugin_key` 唯一且升序、provider / 实现 / 版本 / 状态齐备。"""
    resp = await client.get("/api/v1/plugins")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    groups = cast("list[dict[str, object]]", body["data"])
    assert isinstance(groups, list)
    keys = [str(group["plugin_key"]) for group in groups]
    assert keys, "分组清单为空（注册表构建可能失败）"
    assert len(keys) == len(set(keys)), "plugin_key 重复"
    assert keys == sorted(keys)
    by_key = {str(group["plugin_key"]): group for group in groups}
    for plugin_key in ("audit", "event", "task"):
        group = by_key[plugin_key]
        assert group["provider"] == "null"
        assert group["implementations"] == [{"plugin_name": "null", "contract_version": "0.1.0", "status": "active"}]
    cache = by_key["cache"]
    assert cache["provider"] == "memory"  # dev 覆盖启用进程内缓存（租户解析缓存，01_02）
    # 02-4-27：cache 域新增真实实现（memory / redis）
    cache_items = cast("list[dict[str, str]]", cache["implementations"])
    assert [item["plugin_name"] for item in cache_items] == ["memory", "null", "redis"]
    storage = by_key["object_storage"]
    assert storage["provider"] == "local"
    assert storage["implementations"] == [
        {"plugin_name": "local", "contract_version": "0.1.0", "status": "active"},
        {"plugin_name": "minio", "contract_version": "0.1.0", "status": "registered"},
        {"plugin_name": "null", "contract_version": "0.1.0", "status": "registered"},
    ]
    health = by_key["health_check_registry"]
    assert health["provider"] == "local"
    items = cast("list[dict[str, str]]", health["implementations"])
    assert [(item["plugin_name"], item["status"]) for item in items] == [
        ("local", "active"),
        ("null", "registered"),
    ]


@pytest.mark.kiwi_id(566)
async def test_detail_contract(client: AsyncClient) -> None:
    """单能力明细：字段与列表分组一致。"""
    resp = await client.get("/api/v1/plugins/health_check_registry")
    assert resp.status_code == 200
    group = resp.json()["data"]
    assert group["plugin_key"] == "health_check_registry"
    assert group["provider"] == "local"
    assert {item["plugin_name"] for item in group["implementations"]} == {"local", "null"}


@pytest.mark.kiwi_id(566)
async def test_unknown_plugin_returns_404(client: AsyncClient) -> None:
    """未登记能力：404 + 统一响应体（code 10002）。"""
    resp = await client.get("/api/v1/plugins/ghost_capability")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 10002
    assert "ghost_capability" in str(body["message"])


@pytest.mark.kiwi_id(566)
async def test_response_excludes_options_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应不含 `options` 密钥：配置中的敏感选项值不出现在响应文本。"""
    settings = Settings(storage=PluginSelection(provider="", options={"secret_key": "top-secret"}))
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/plugins")
    assert resp.status_code == 200
    assert "top-secret" not in resp.text
    assert "secret_key" not in resp.text


@pytest.mark.kiwi_id(566)
async def test_readonly_no_write_methods(client: AsyncClient) -> None:
    """只读接口：写方法一律 405 Method Not Allowed。"""
    for method in ("post", "put", "delete"):
        resp = await getattr(client, method)("/api/v1/plugins")
        assert resp.status_code == 405, method
