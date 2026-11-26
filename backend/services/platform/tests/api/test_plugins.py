"""插件清单接口测试（Kiwi 566 / 2190，装配态口径）。

重写口径（13_11）：一律复用会话级装配实例，不再自建应用壳——自建壳会重新登记插件工厂，
把进程级注册表翻成本壳的（工厂持有本壳的 `app.state`），后继用例解析即读不到槽位。
需要改配置的用例走 `monkeypatch` 就地改写装配态 `settings`，由还原夹具逐例复位。
"""

from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

PLUGINS = "/api/v1/plugins"


@pytest.mark.kiwi_id(566)
async def test_list_contract(client: AsyncClient) -> None:
    """分组清单：`plugin_key` 唯一且升序、provider / 实现 / 版本 / 状态齐备。"""
    resp = await client.get(PLUGINS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    groups = cast("list[dict[str, object]]", body["data"])
    assert isinstance(groups, list)
    keys = [str(group["plugin_key"]) for group in groups]
    assert keys, "分组清单为空（注册表构建可能失败）"
    assert len(keys) == len(set(keys)), "plugin_key 重复"
    assert keys == sorted(keys)

    all_names = [
        str(item["plugin_name"])
        for group in groups
        for item in cast("list[dict[str, object]]", group["implementations"])
    ]
    # 测试替身（`_StubXxx`）继承真实基类时须声明 `auto_register = False`，漏标会污染清单。
    assert "stub" not in all_names, all_names

    by_key = {str(group["plugin_key"]): group for group in groups}
    # 审计捕获在平台装配期显式启用 DB 实现（06_01 / 06_02）；任务执行体仍为 null 占位。
    assert by_key["audit"]["provider"] == "db"
    assert by_key["audit"]["implementations"] == [
        {"plugin_name": "db", "contract_version": "0.1.0", "status": "active"},
        {"plugin_name": "null", "contract_version": "0.1.0", "status": "registered"},
    ]
    assert by_key["task"]["provider"] == "null"
    assert by_key["task"]["implementations"] == [
        {"plugin_name": "null", "contract_version": "0.1.0", "status": "active"}
    ]
    # 事件发布：dev 配置启用 msg（`[event].provider = "msg"`，01_04），null 保留为占位实现
    assert by_key["event"]["provider"] == "msg"
    assert by_key["event"]["implementations"] == [
        {"plugin_name": "msg", "contract_version": "0.1.0", "status": "active"},
        {"plugin_name": "null", "contract_version": "0.1.0", "status": "registered"},
    ]
    # dev 覆盖启用进程内缓存（租户解析缓存，01_02）；02-4-27 起 cache 域含真实 redis 实现
    assert by_key["cache"]["provider"] == "memory"
    assert [item["plugin_name"] for item in cast("list[dict[str, str]]", by_key["cache"]["implementations"])] == [
        "memory",
        "null",
        "redis",
    ]
    assert by_key["object_storage"]["provider"] == "local"
    assert by_key["object_storage"]["implementations"] == [
        {"plugin_name": "local", "contract_version": "0.1.0", "status": "active"},
        {"plugin_name": "minio", "contract_version": "0.1.0", "status": "registered"},
        {"plugin_name": "null", "contract_version": "0.1.0", "status": "registered"},
    ]
    assert by_key["health_check_registry"]["provider"] == "local"
    assert [
        (item["plugin_name"], item["status"])
        for item in cast("list[dict[str, str]]", by_key["health_check_registry"]["implementations"])
    ] == [("local", "active"), ("null", "registered")]


@pytest.mark.kiwi_id(566)
async def test_detail_contract(client: AsyncClient) -> None:
    """单能力明细：字段与列表分组一致。"""
    resp = await client.get(f"{PLUGINS}/health_check_registry")
    assert resp.status_code == 200
    group = resp.json()["data"]
    assert group["plugin_key"] == "health_check_registry"
    assert group["provider"] == "local"
    assert {item["plugin_name"] for item in group["implementations"]} == {"local", "null"}


@pytest.mark.kiwi_id(566)
async def test_unknown_plugin_returns_404(client: AsyncClient) -> None:
    """未登记能力：404 + 统一响应体（code 10002）。"""
    resp = await client.get(f"{PLUGINS}/ghost_capability")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 10002
    assert "ghost_capability" in str(body["message"])


@pytest.mark.kiwi_id(566)
async def test_response_excludes_options_secrets(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """响应不含 `options` 密钥：就地改装配态配置后，敏感值不出现在响应文本。"""
    monkeypatch.setitem(service_app.state.settings.storage.options, "secret_key", "top-secret")
    resp = await client.get(PLUGINS)
    assert resp.status_code == 200
    assert "top-secret" not in resp.text
    assert "secret_key" not in resp.text


@pytest.mark.kiwi_id(566)
async def test_readonly_no_write_methods(client: AsyncClient) -> None:
    """只读接口：写方法一律 405 Method Not Allowed。"""
    for method in ("post", "put", "delete"):
        resp = await getattr(client, method)(PLUGINS)
        assert resp.status_code == 405, method


@pytest.mark.kiwi_id(2190)
async def test_aggregate_placeholder_contract(client: AsyncClient) -> None:
    """跨服务聚合占位契约：固定空聚合 + 占位标记，且未被 `/{plugin_key}` 明细路由吞掉。"""
    resp = await client.get(f"{PLUGINS}/aggregate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"placeholder": True, "services": []}


@pytest.mark.kiwi_id(2190)
async def test_aggregate_path_in_openapi(service_app: FastAPI) -> None:
    """公开契约含聚合端点（应用可启动、路由已挂载）。"""
    paths = service_app.openapi()["paths"]
    assert f"{PLUGINS}/aggregate" in paths


@pytest.mark.kiwi_id(2190)
async def test_aggregate_excludes_options_secrets(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """聚合占位响应不含 `options` 密钥。"""
    monkeypatch.setitem(service_app.state.settings.storage.options, "secret_key", "top-secret")
    resp = await client.get(f"{PLUGINS}/aggregate")
    assert resp.status_code == 200
    assert "top-secret" not in resp.text
    assert "secret_key" not in resp.text


@pytest.mark.kiwi_id(2190)
async def test_aggregate_readonly_no_write_methods(client: AsyncClient) -> None:
    """聚合端点只读：写方法一律 405 Method Not Allowed。"""
    for method in ("post", "put", "delete"):
        resp = await getattr(client, method)(f"{PLUGINS}/aggregate")
        assert resp.status_code == 405, method
