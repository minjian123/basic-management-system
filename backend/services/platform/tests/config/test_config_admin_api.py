"""系统参数管理接口契约测试（Kiwi 2373）：七个端点 · 校验分支 · 重置 / 删除保护 / 恢复 · 乐观锁。

鉴权口径：默认 `NullPermissionChecker` 恒放行（`assign_system_admin` 置内置系统管理员命中豁免层级）；
「权限拒绝」分支待真实检查器注入后由安全专项补齐（本文件不断言 403 越权，避免用假用例凑数）。
"""

from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.base import Base
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.task import SysTask, SysTaskLog
from tests_support.permission_admin import assign_system_admin

pytestmark = pytest.mark.kiwi_id(2373)

_ENABLED = "enabled"

TENANT_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysRole.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysIcon.__table__),
        cast("Table", SysIconI18n.__table__),
        cast("Table", SysTask.__table__),
        cast("Table", SysTaskLog.__table__),
        cast("Table", SysConfig.__table__),
    ]
)


@pytest_asyncio.fixture(autouse=True)
async def tenant_db(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """最小租户库（权限引擎读表 + `sys_config`）并把测试主体置内置系统管理员。

    Args:
        tmp_path_factory: pytest 临时目录工厂。
        monkeypatch: 环境变量覆盖夹具。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('config_api_tenant') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(TENANT_TABLES)))
    await engine.dispose()
    await assign_system_admin()
    get_settings.cache_clear()


async def _seed_row(
    keyword: str,
    *,
    value: str,
    is_overridden: bool,
    status: str = _ENABLED,
    remark: str | None = None,
) -> int:
    """直接落一行参数（模拟种子下发或历史覆盖态）。

    Args:
        keyword: 参数键。
        value: 参数值。
        is_overridden: 是否覆盖态。
        status: 状态。
        remark: 备注。

    Returns:
        int: 参数主键。
    """
    settings = get_settings()
    url = settings.database.tenants.url
    engine = create_async_engine(str(url))
    factory: async_sessionmaker[Any] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysConfig(
                config_key=keyword,
                value=value,
                is_overridden=is_overridden,
                status=status,
                remark=remark,
            )
            session.add(row)
            await session.commit()
            return int(row.id)
    finally:
        await engine.dispose()


async def _create(client: AsyncClient, keyword: str, value: str, **extra: object) -> Any:
    """新增参数（成功路径的简写）。

    Args:
        client: 测试客户端。
        keyword: 参数键。
        value: 参数值。
        **extra: 额外字段。

    Returns:
        Any: 响应 data（JSON 对象，用例内按键直取）。
    """
    payload = dict({"config_key": keyword, "value": value, **extra})
    resp = await client.post("/api/v1/configs", json=payload)
    assert resp.status_code == 200, resp.text
    return cast("dict[str, Any]", resp.json()["data"])


async def test_list_empty_and_filters(client: AsyncClient) -> None:
    """列表：空库分页结构正确；关键字 / 分组 / 状态筛选生效。"""
    empty = (await client.get("/api/v1/configs")).json()["data"]
    assert empty["total"] == 0
    assert empty["list"] == []

    await _create(client, "password.max_age_days", "60", remark="密码有效期")
    await _create(client, "session.max_active", "3")

    by_keyword = (await client.get("/api/v1/configs", params={"keyword": "max_age"})).json()["data"]
    assert by_keyword["total"] == 1
    assert by_keyword["list"][0]["config_key"] == "password.max_age_days"

    by_group = (await client.get("/api/v1/configs", params={"group": "session"})).json()["data"]
    assert by_group["total"] == 1
    assert by_group["list"][0]["group"] == "session"

    disabled = (await client.get("/api/v1/configs", params={"status": "disabled"})).json()["data"]
    assert disabled["total"] == 0


async def test_create_item_derives_group_and_sensitive(client: AsyncClient) -> None:
    """新增：派生分组 / 来源 / 敏感标记，覆盖态为 tenant。"""
    data = await _create(client, "password.min_length", "10", name="密码最小长度")
    assert data["group"] == "password"
    assert data["source"] == "tenant"
    assert data["is_sensitive"] is True
    assert data["name"] == "密码最小长度"
    assert data["version"] == 1

    plain = await _create(client, "file.upload.max_size", "1024")
    assert plain["is_sensitive"] is False
    assert plain["group"] == "file"
    assert plain["name"] == "file.upload.max_size"


async def test_create_rejects_duplicate_invalid_key_and_value(client: AsyncClient) -> None:
    """新增拒绝分支：重复键 `40502` / 非法键 `40503` / 非法值 `40504` / 非法状态 `40504`。"""
    await _create(client, "password.max_age_days", "90")

    dup = await client.post("/api/v1/configs", json={"config_key": "password.max_age_days", "value": "30"})
    assert dup.json()["code"] == 40502

    bad_key = await client.post("/api/v1/configs", json={"config_key": "Password.Bad", "value": "1"})
    assert bad_key.json()["code"] == 40503

    bad_value = await client.post("/api/v1/configs", json={"config_key": "password.require_upper", "value": "yes"})
    assert bad_value.json()["code"] == 40504

    bad_status = await client.post(
        "/api/v1/configs", json={"config_key": "custom.flag", "value": "1", "status": "archived"}
    )
    assert bad_status.json()["code"] == 40504


async def test_dependency_both_directions(client: AsyncClient) -> None:
    """依赖：开启 `ai.auto_approve` 需先开 `ai.auto_execute`；关闭被依赖项前须先关依赖项。"""
    denied = await client.post("/api/v1/configs", json={"config_key": "ai.auto_approve", "value": "true"})
    assert denied.json()["code"] == 40505

    execute = await _create(client, "ai.auto_execute", "true")
    approve = await _create(client, "ai.auto_approve", "true")
    assert approve["value"] == "true"

    blocked = await client.put(
        f"/api/v1/configs/{execute['id']}", json={"value": "false", "version": execute["version"]}
    )
    assert blocked.json()["code"] == 40505

    await client.put(f"/api/v1/configs/{approve['id']}", json={"value": "false", "version": approve["version"]})
    allowed = await client.put(
        f"/api/v1/configs/{execute['id']}", json={"value": "false", "version": execute["version"]}
    )
    assert allowed.json()["code"] == 0


async def test_detail_and_not_found(client: AsyncClient) -> None:
    """详情：按键取回；不存在返回 `40501`。"""
    await _create(client, "captcha.scene.login.ttl", "300")
    detail = await client.get("/api/v1/configs/captcha.scene.login.ttl")
    assert detail.status_code == 200
    assert detail.json()["data"]["config_key"] == "captcha.scene.login.ttl"

    missing = await client.get("/api/v1/configs/not.exists")
    assert missing.json()["code"] == 40501


async def test_update_conflicts_on_stale_version(client: AsyncClient) -> None:
    """修改：乐观锁冲突返回 `10004`，成功则版本递增。"""
    created = await _create(client, "session.max_active", "5")
    ok = await client.put(f"/api/v1/configs/{created['id']}", json={"value": "8", "version": created["version"]})
    assert ok.json()["data"]["value"] == "8"
    assert ok.json()["data"]["version"] == created["version"] + 1

    stale = await client.put(f"/api/v1/configs/{created['id']}", json={"value": "9", "version": created["version"]})
    assert stale.json()["code"] == 10004


async def test_reset_restores_platform_default(client: AsyncClient) -> None:
    """重置：覆盖项回填平台默认值并置回平台来源；无默认的租户自建键返回 `40507`。"""
    item_id = await _seed_row("password.max_length", value="128", is_overridden=True)
    reset = await client.post(f"/api/v1/configs/{item_id}/reset")
    assert reset.status_code == 200
    assert reset.json()["data"]["value"] == "128"
    assert reset.json()["data"]["source"] == "platform"

    again = await client.post(f"/api/v1/configs/{item_id}/reset")
    assert again.json()["data"]["source"] == "platform"

    custom = await _create(client, "custom.timeout", "30")
    no_default = await client.post(f"/api/v1/configs/{custom['id']}/reset")
    assert no_default.json()["code"] == 40507


async def test_delete_protects_default_and_supports_recycle_bin(client: AsyncClient) -> None:
    """删除：平台默认项拒绝 `40506`；覆盖项软删进回收站并可恢复；同键活行冲突 `40502`。"""
    default_id = await _seed_row("menu.tree_cache_ttl", value="300", is_overridden=False)
    blocked = await client.delete(f"/api/v1/configs/{default_id}")
    assert blocked.json()["code"] == 40506

    override_id = await _seed_row("role.code_pattern", value="^[a-z]+$", is_overridden=True)
    deleted = await client.delete(f"/api/v1/configs/{override_id}")
    assert deleted.json()["code"] == 0

    alive = (await client.get("/api/v1/configs")).json()["data"]
    assert alive["total"] == 1

    recycled = (await client.get("/api/v1/configs", params={"include_deleted": True})).json()["data"]
    assert recycled["total"] == 2
    assert any(item["deleted_at"] for item in recycled["list"])

    restored = await client.post(f"/api/v1/configs/{override_id}/restore")
    assert restored.json()["data"]["deleted_at"] is None

    again = await client.post(f"/api/v1/configs/{override_id}/restore")
    assert again.json()["code"] == 0


async def test_restore_conflicts_with_live_row(client: AsyncClient) -> None:
    """恢复：同键已有未删除行时返回 `40502`。"""
    item_id = await _seed_row("audit.archive.operation_log_days", value="90", is_overridden=True)
    await client.delete(f"/api/v1/configs/{item_id}")
    await _create(client, "audit.archive.operation_log_days", "120")
    conflict = await client.post(f"/api/v1/configs/{item_id}/restore")
    assert conflict.json()["code"] == 40502


async def test_delete_missing_returns_not_found(client: AsyncClient) -> None:
    """删除 / 详情 / 重置 / 恢复的不存在分支统一 `40501`。"""
    assert (await client.delete("/api/v1/configs/999999")).json()["code"] == 40501
    assert (await client.post("/api/v1/configs/999999/reset")).json()["code"] == 40501
    assert (await client.post("/api/v1/configs/999999/restore")).json()["code"] == 40501
    assert (await client.put("/api/v1/configs/999999", json={"value": "1", "version": 1})).json()["code"] == 40501
