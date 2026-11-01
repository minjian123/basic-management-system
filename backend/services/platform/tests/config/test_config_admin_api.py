"""系统参数管理接口契约测试（Kiwi 2373）：七个端点 · 校验分支 · 重置 / 删除保护 / 恢复 · 乐观锁。

鉴权口径：默认 `NullPermissionChecker` 恒放行（`assign_system_admin` 置内置系统管理员命中豁免层级）；
「权限拒绝」分支待真实检查器注入后由安全专项补齐（本文件不断言 403 越权，避免用假用例凑数）。

单库叠加（04-6-2 §2.8，**真叠加**）：跑**共享租户库**（平台默认参数已由准备集播种），
不再每用例建临时库。断言语义绑定平台默认键（重置回填 `_PLATFORM_DEFAULTS` / 依赖成对校验 /
敏感标记）的用例，改为「用例前把这些键复位到平台默认态（值 / 未覆盖 / 未软删）→ 用例内读写 →
用例后复位」，并用与 `test_config_platform_defaults.py` **同名**的跨进程文件锁串行
（共享库里这些固定键是全局状态，SQLite 写锁不能拿来互斥）。
「全表总数 / 清单为空」类断言一律改为「按关键字限定本用例数据」——叠加下全表起点不存在。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.models import SysConfig
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from tests_support.locks import file_lock
from tests_support.permission_admin import assign_system_admin

pytestmark = [pytest.mark.kiwi_id(2373)]

_ENABLED = "enabled"

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((cast("Table", SysConfig.__table__),))
"""本文件涉及的表（幂等建表集）。"""

_DEFAULTS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    (item.config_key, item.value) for item in PLATFORM_CONFIG_DEFAULTS
)
"""参数键 → 平台默认值。"""

_KEYS: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "ai.auto_execute",
        "ai.auto_approve",
        "session.max_active",
        "password.max_length",
        "password.require_upper",
        "captcha.scene.login.ttl",
        "menu.tree_cache_ttl",
        "role.code_pattern",
        "audit.archive.operation_log_days",
    )
)
"""本文件读写的平台默认键（用例前后统一复位；与 `test_config_platform_defaults.py` 同锁串行）。"""

_LOCK_NAME = "config-platform-defaults"
"""跨进程锁名（与 `test_config_platform_defaults.py` 同值：两文件读写同一批全局键）。"""

_ROLE_CODE_PATTERN_OVERRIDE = "^[a-z][a-z0-9_-]{0,63}$"
"""`role.code_pattern` 的覆盖值（刻意比默认更宽松：并行中他人建角色不会被本用例收紧的口径打断）。"""


async def _reset(db: AsyncSession) -> None:
    """把本文件涉及的平台默认键复位到默认态，并清掉用例造出的同键副本。

    复位内容：保留种子行（最小主键）→ 值回落平台默认、`is_overridden=False`、状态启用、取消软删；
    同键的其余行（用例先软删种子行再新建的活行）直接硬删——它们是本用例的产物。

    Args:
        db: 租户库会话。
    """
    statement = (
        select(SysConfig).where(SysConfig.config_key.in_(list(_KEYS))).order_by(SysConfig.config_key, SysConfig.id)
    )
    rows = (await db.execute(statement)).scalars().all()
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    for row in rows:
        key = str(row.config_key)
        if key in seen:
            await db.delete(row)
            continue
        seen.add(key)
        row.deleted_at = None
        row.value = _DEFAULTS.get(key, row.value)
        row.is_overridden = False
        row.status = _ENABLED
    await db.commit()


async def _soft_delete(db: AsyncSession, config_key: str) -> None:
    """软删指定平台默认键的活行（构造「库中该键无活行」的起点）。

    Args:
        db: 租户库会话。
    """
    row = (
        (await db.execute(select(SysConfig).where(SysConfig.config_key == config_key, SysConfig.deleted_at.is_(None))))
        .scalars()
        .first()
    )
    assert row is not None, f"共享租户库缺少平台默认参数：{config_key}"
    row.soft_delete()
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def config_global_state(tenant_db: str, shared_tenant_engine: AsyncEngine) -> AsyncIterator[None]:
    """串行持有「平台默认键」跨进程锁，并在用例前后复位这批键。

    平台默认键在共享库里是**全局状态**（全 worker 共用一份 `tenant.db`），必须整体串行：
    键复位 → 用例读写 → 键再复位。

    Args:
        tenant_db: 共享租户库连接串（套件夹具已注入 `BMS_DATABASE__TENANTS__URL`）。
        shared_tenant_engine: 共享租户库引擎（基座夹具，不在此自建引擎）。

    Yields:
        None: 用例运行期。
    """
    del tenant_db
    with file_lock(_LOCK_NAME):
        await ensure_tables(shared_tenant_engine, _TABLES)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
        async with factory() as db:
            await _reset(db)
            await assign_system_admin()
            yield
            await _reset(db)


@pytest_asyncio.fixture
async def db(shared_tenant_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享租户库会话（用例直接改平台默认键行时用；清场与复位由 `config_global_state` 负责）。

    Args:
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        AsyncSession: 会话。
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


def _own_key(ns: Namespace, group: str, suffix: str) -> str:
    """本用例的参数键（首段即分组；点分小写口径见 `bms_core.config.rules`）。

    Args:
        ns: 用例命名空间。
        group: 首段分组（`password` / `file` / `custom`）。
        suffix: 键后缀。

    Returns:
        str: 形如 `password.w0a1b2c3d4_min`。
    """
    return f"{group}.{ns.prefix}_{suffix}"


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


async def _detail(client: AsyncClient, keyword: str) -> Any:
    """按参数键取详情（平台默认键的种子行）。

    Args:
        client: 测试客户端。
        keyword: 参数键。

    Returns:
        Any: 响应 data。
    """
    resp = await client.get(f"/api/v1/configs/{keyword}")
    assert resp.status_code == 200, resp.text
    return cast("dict[str, Any]", resp.json()["data"])


async def test_list_paging_and_filters(client: AsyncClient, ns: Namespace) -> None:
    """列表：无命中时分页结构正确；关键字 / 分组 / 状态筛选生效（叠加下按本用例键限定）。"""
    absent = (await client.get("/api/v1/configs", params={"keyword": f"{ns.prefix}_absent"})).json()["data"]
    assert absent["total"] == 0
    assert absent["list"] == []

    probe_key = _own_key(ns, "custom", "probe")
    active_key = _own_key(ns, "session", "active")
    await _create(client, probe_key, "60", remark="密码有效期")
    await _create(client, active_key, "3")

    by_keyword = (await client.get("/api/v1/configs", params={"keyword": probe_key})).json()["data"]
    assert by_keyword["total"] == 1
    assert by_keyword["list"][0]["config_key"] == probe_key

    by_group = (await client.get("/api/v1/configs", params={"group": "session", "keyword": ns.prefix})).json()["data"]
    assert by_group["total"] == 1
    assert by_group["list"][0]["group"] == "session"

    disabled = (await client.get("/api/v1/configs", params={"status": "disabled", "keyword": ns.prefix})).json()["data"]
    assert disabled["total"] == 0


async def test_create_item_derives_group_and_sensitive(client: AsyncClient, ns: Namespace) -> None:
    """新增：派生分组 / 来源 / 敏感标记，覆盖态为 tenant（键按命名空间派生，避开平台默认键）。"""
    data = await _create(client, _own_key(ns, "password", "min"), "10", name="密码最小长度")
    assert data["group"] == "password"
    assert data["source"] == "tenant"
    assert data["is_sensitive"] is True
    assert data["name"] == "密码最小长度"
    assert data["version"] == 1

    plain_key = _own_key(ns, "file", "max_size")
    plain = await _create(client, plain_key, "1024")
    assert plain["is_sensitive"] is False
    assert plain["group"] == "file"
    assert plain["name"] == plain_key


async def test_create_rejects_duplicate_invalid_key_and_value(client: AsyncClient, ns: Namespace) -> None:
    """新增拒绝分支：重复键 `40502` / 非法键 `40503` / 非法值 `40504` / 非法状态 `40504`。"""
    dup_key = _own_key(ns, "custom", "dup")
    await _create(client, dup_key, "90")

    dup = await client.post("/api/v1/configs", json={"config_key": dup_key, "value": "30"})
    assert dup.json()["code"] == 40502

    bad_key = await client.post("/api/v1/configs", json={"config_key": "Password.Bad", "value": "1"})
    assert bad_key.json()["code"] == 40503

    # 值类型按平台默认值推断：`password.require_upper` 是布尔键，故 "yes" 即拒
    # （值校验先于「键已存在」判重，故种子行存在不影响本分支）
    bad_value = await client.post("/api/v1/configs", json={"config_key": "password.require_upper", "value": "yes"})
    assert bad_value.json()["code"] == 40504

    bad_status = await client.post(
        "/api/v1/configs", json={"config_key": _own_key(ns, "custom", "flag"), "value": "1", "status": "archived"}
    )
    assert bad_status.json()["code"] == 40504


async def test_dependency_both_directions(client: AsyncClient, db: AsyncSession) -> None:
    """依赖：开启 `ai.auto_approve` 需先开 `ai.auto_execute`；关闭被依赖项前须先关依赖项。

    叠加口径：两个键由准备集播种为「未覆盖、值为 false」，故不再走「新增」——依赖不满足分支
    靠先软删 `ai.auto_approve` 的活行构造「新增首条覆盖」的起点，其余步骤用修改端点。
    """
    await _soft_delete(db, "ai.auto_approve")
    denied = await client.post("/api/v1/configs", json={"config_key": "ai.auto_approve", "value": "true"})
    assert denied.json()["code"] == 40505

    execute = await _detail(client, "ai.auto_execute")
    enabled = await client.put(
        f"/api/v1/configs/{execute['id']}", json={"value": "true", "version": execute["version"]}
    )
    assert enabled.json()["code"] == 0, enabled.text

    approve = await _create(client, "ai.auto_approve", "true")
    assert approve["value"] == "true"

    execute = await _detail(client, "ai.auto_execute")
    blocked = await client.put(
        f"/api/v1/configs/{execute['id']}", json={"value": "false", "version": execute["version"]}
    )
    assert blocked.json()["code"] == 40505

    await client.put(f"/api/v1/configs/{approve['id']}", json={"value": "false", "version": approve["version"]})
    execute = await _detail(client, "ai.auto_execute")
    allowed = await client.put(
        f"/api/v1/configs/{execute['id']}", json={"value": "false", "version": execute["version"]}
    )
    assert allowed.json()["code"] == 0


async def test_detail_and_not_found(client: AsyncClient) -> None:
    """详情：按键取回；不存在返回 `40501`。"""
    detail = await client.get("/api/v1/configs/captcha.scene.login.ttl")
    assert detail.status_code == 200
    assert detail.json()["data"]["config_key"] == "captcha.scene.login.ttl"

    missing = await client.get("/api/v1/configs/not.exists")
    assert missing.json()["code"] == 40501


async def test_update_conflicts_on_stale_version(client: AsyncClient) -> None:
    """修改：乐观锁冲突返回 `10004`，成功则版本递增。"""
    created = await _detail(client, "session.max_active")
    ok = await client.put(f"/api/v1/configs/{created['id']}", json={"value": "8", "version": created["version"]})
    assert ok.json()["data"]["value"] == "8"
    assert ok.json()["data"]["version"] == created["version"] + 1

    stale = await client.put(f"/api/v1/configs/{created['id']}", json={"value": "9", "version": created["version"]})
    assert stale.json()["code"] == 10004


async def test_reset_restores_platform_default(client: AsyncClient, ns: Namespace) -> None:
    """重置：覆盖项回填平台默认值并置回平台来源；无默认的租户自建键返回 `40507`。"""
    item = await _detail(client, "password.max_length")
    overridden = await client.put(f"/api/v1/configs/{item['id']}", json={"value": "200", "version": item["version"]})
    assert overridden.json()["data"]["source"] == "tenant"

    reset = await client.post(f"/api/v1/configs/{item['id']}/reset")
    assert reset.status_code == 200
    assert reset.json()["data"]["value"] == _DEFAULTS["password.max_length"]
    assert reset.json()["data"]["source"] == "platform"

    again = await client.post(f"/api/v1/configs/{item['id']}/reset")
    assert again.json()["data"]["source"] == "platform"

    custom = await _create(client, _own_key(ns, "custom", "timeout"), "30")
    no_default = await client.post(f"/api/v1/configs/{custom['id']}/reset")
    assert no_default.json()["code"] == 40507


async def test_delete_protects_default_and_supports_recycle_bin(client: AsyncClient) -> None:
    """删除：平台默认项拒绝 `40506`；覆盖项软删进回收站并可恢复。"""
    default = await _detail(client, "menu.tree_cache_ttl")
    blocked = await client.delete(f"/api/v1/configs/{default['id']}")
    assert blocked.json()["code"] == 40506

    override = await _detail(client, "role.code_pattern")
    overridden = await client.put(
        f"/api/v1/configs/{override['id']}",
        json={"value": _ROLE_CODE_PATTERN_OVERRIDE, "version": override["version"]},
    )
    assert overridden.json()["code"] == 0, overridden.text

    deleted = await client.delete(f"/api/v1/configs/{override['id']}")
    assert deleted.json()["code"] == 0

    alive = (await client.get("/api/v1/configs", params={"keyword": "role.code_pattern"})).json()["data"]
    assert alive["total"] == 0

    recycled = (
        await client.get("/api/v1/configs", params={"keyword": "role.code_pattern", "include_deleted": True})
    ).json()["data"]
    assert recycled["total"] == 1
    assert any(row["deleted_at"] for row in recycled["list"])

    restored = await client.post(f"/api/v1/configs/{override['id']}/restore")
    assert restored.json()["data"]["deleted_at"] is None

    again = await client.post(f"/api/v1/configs/{override['id']}/restore")
    assert again.json()["code"] == 0


async def test_restore_conflicts_with_live_row(client: AsyncClient) -> None:
    """恢复：同键已有未删除行时返回 `40502`。"""
    item = await _detail(client, "audit.archive.operation_log_days")
    overridden = await client.put(f"/api/v1/configs/{item['id']}", json={"value": "120", "version": item["version"]})
    assert overridden.json()["code"] == 0, overridden.text
    await client.delete(f"/api/v1/configs/{item['id']}")

    await _create(client, "audit.archive.operation_log_days", "120")
    conflict = await client.post(f"/api/v1/configs/{item['id']}/restore")
    assert conflict.json()["code"] == 40502


async def test_delete_missing_returns_not_found(client: AsyncClient) -> None:
    """删除 / 详情 / 重置 / 恢复的不存在分支统一 `40501`。"""
    assert (await client.delete("/api/v1/configs/999999")).json()["code"] == 40501
    assert (await client.post("/api/v1/configs/999999/reset")).json()["code"] == 40501
    assert (await client.post("/api/v1/configs/999999/restore")).json()["code"] == 40501
    assert (await client.put("/api/v1/configs/999999", json={"value": "1", "version": 1})).json()["code"] == 40501
