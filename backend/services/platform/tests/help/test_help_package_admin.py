"""帮助包管理面：列表 / 装载 / 卸载 / 路径越界 / 权限码（Kiwi 2529）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.session import DbSession
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help.repositories.maintenance import HelpArticleMaintenanceRepository
from tests_support.auth import auth_headers
from tests_support.help import delete_platform_action, platform_url, seed_package, seed_platform_action, tenant_url

from ._support import article_payload, prepare, write_package

pytestmark = pytest.mark.kiwi_id(2529)

_PACKAGES = "/api/v1/help/packages"


def _body(response: Any) -> Any:
    """取响应体。"""
    return response.json()


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备权限主体与帮助表。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()


async def test_package_list(client: AsyncClient, ns: Namespace) -> None:
    """已装载包列表按产品 / 状态筛选。"""
    await seed_package(tenant_url(), product_key=f"{ns.prefix}_list", status="loaded")
    page = _body(await client.get(_PACKAGES, params={"product_key": f"{ns.prefix}_list", "status": "loaded"}))
    assert page["code"] == 0
    assert page["data"]["total"] == 1
    row = page["data"]["list"][0]
    assert row["product_key"] == f"{ns.prefix}_list"
    assert row["status"] == "loaded"
    assert row["article_count"] == 1
    unfiltered = _body(await client.get(_PACKAGES))
    assert unfiltered["code"] == 0
    assert unfiltered["data"]["total"] >= 1


async def test_repo_empty_category_scope() -> None:
    """仓储空分类范围直接返回空清单（不发 SQL）。"""
    repo = HelpArticleMaintenanceRepository(cast("DbSession", object()))
    assert list(await repo.list_articles_in_categories(ConcurrentStableList())) == []


async def test_package_requires_permission(client: AsyncClient) -> None:
    """缺 `help:package` 返回 30001。"""
    denied = await client.get(_PACKAGES, headers=auth_headers("990002"))
    assert denied.json()["code"] == 30001


async def test_package_path_outside_root_rejected(
    client: AsyncClient, ns: Namespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """绝对路径 / 越界 / 不存在一律 40021。"""
    monkeypatch.setattr(get_settings().help_package, "root", str(tmp_path))
    absolute = _body(await client.post(f"{_PACKAGES}/load", json={"package_path": str(tmp_path / "pkg")}))
    assert absolute["code"] == 40021
    outside = _body(await client.post(f"{_PACKAGES}/load", json={"package_path": "../outside"}))
    assert outside["code"] == 40021
    missing = _body(await client.post(f"{_PACKAGES}/load", json={"package_path": "missing"}))
    assert missing["code"] == 40021
    assert ns.prefix


async def test_package_load_and_unload(
    client: AsyncClient, ns: Namespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dry-run 不写；实跑计数一致；卸载下线来源文章。"""
    monkeypatch.setattr(get_settings().help_package, "root", str(tmp_path))
    product_key = ns.prefix
    action_code = f"{ns.prefix}_pkg_anchor"
    await seed_platform_action(platform_url(), code=action_code, help_key=f"platform::::{action_code}")
    try:
        write_package(
            tmp_path / "pkg",
            product_key=product_key,
            prefix=ns.prefix,
            articles=ConcurrentStableList((article_payload(ns.prefix, product_key=product_key, target_type="global"),)),
        )

        dry_run = _body(await client.post(f"{_PACKAGES}/load", json={"package_path": "pkg"}))
        assert dry_run["code"] == 0
        assert dry_run["data"]["applied"] is False
        assert dry_run["data"]["package_action"] == "created"
        assert dry_run["data"]["counts"]["articles_new"] == 1
        assert _body(await client.get(_PACKAGES, params={"product_key": product_key}))["data"]["total"] == 0

        applied = _body(await client.post(f"{_PACKAGES}/load", json={"package_path": "pkg", "dry_run": False}))
        assert applied["code"] == 0
        assert applied["data"]["applied"] is True
        assert applied["data"]["counts"]["articles_new"] == 1
        listed = _body(await client.get(_PACKAGES, params={"product_key": product_key}))["data"]
        assert listed["total"] == 1
        assert listed["list"][0]["status"] == "loaded"

        preview = _body(await client.post(f"{_PACKAGES}/{product_key}/unload", json={"dry_run": True}))
        assert preview["code"] == 0
        assert preview["data"]["applied"] is False
        assert preview["data"]["counts"]["articles_offline"] == 1

        unloaded = _body(await client.post(f"{_PACKAGES}/{product_key}/unload", json={"dry_run": False}))
        assert unloaded["code"] == 0
        assert unloaded["data"]["applied"] is True
        assert unloaded["data"]["counts"]["articles_offline"] == 1
        after = _body(await client.get(_PACKAGES, params={"product_key": product_key}))["data"]
        assert after["list"][0]["status"] == "unloaded"
    finally:
        await delete_platform_action(platform_url(), action_code)


async def test_unload_blank_product_key_rejected(client: AsyncClient) -> None:
    """产品键为空（空格）返回 10001。"""
    response = _body(await client.post(f"{_PACKAGES}/%20/unload", json={}))
    assert response["code"] == 10001


async def test_unload_not_loaded_rejected(client: AsyncClient, ns: Namespace) -> None:
    """未装载产品卸载返回 40012。"""
    response = _body(await client.post(f"{_PACKAGES}/{ns.prefix}_none/unload", json={}))
    assert response["code"] == 40012
