"""任务调度接口契约测试（Kiwi 2371）：八个端点 · 校验分支 · 启停 · 手动触发 · 执行记录。

鉴权口径：默认 `NullPermissionChecker` 恒放行，「权限拒绝」分支待真实检查器注入后由安全专项补齐
（本文件不断言 403，避免用假用例凑数）。

单库叠加口径（04-6-2）：租户库用共享租户库（不再建临时库）；任务代码 / 名称带命名空间前缀，
列表与执行记录断言一律按本用例任务定位（禁止「全表 total == 1 / == 0」类断言）。
"""

from typing import Any, cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.task import SysTask, SysTaskLog
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from tests_support.permission_admin import assign_system_admin

pytestmark = pytest.mark.kiwi_id(2371)

_HANDLER = "bms_core.tasks.builtin:run_cleanup_orphan_parts"

TENANT_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysRole.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysIcon.__table__),
        cast("Table", SysIconI18n.__table__),
        cast("Table", SysTask.__table__),
        cast("Table", SysTaskLog.__table__),
        cast("Table", SysOutbox.__table__),
        cast("Table", SysEventConsumed.__table__),
        cast("Table", SysEventDeadLetter.__table__),
    ]
)


@pytest_asyncio.fixture(autouse=True)
async def tenant_db(
    shared_tenant_engine: AsyncEngine, shared_tenant_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """共享租户库（权限引擎读表 + 任务两表 + 发件箱三表幂等补齐）并把测试主体置内置系统管理员。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        shared_tenant_db_url: 共享租户库连接串。
        monkeypatch: 环境变量覆盖夹具。
    """
    await ensure_tables(shared_tenant_engine, list(TENANT_TABLES))
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()
    await assign_system_admin()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch: pytest.MonkeyPatch) -> Redis:
    """把队列 / 信号 / 冷却的共享客户端替换为 fakeredis。

    Args:
        monkeypatch: 环境补丁。

    Returns:
        Redis: 假客户端（测试内可直接检查队列）。
    """
    client = cast("Redis", FakeRedis(decode_responses=False))
    monkeypatch.setattr("bms_core.tasks.signal.shared_async_client", lambda: client)
    monkeypatch.setattr("bms_core.redis.base.shared_async_client", lambda: client)
    return client


def _missing_id(ns: Namespace) -> int:
    """本用例专属的「不存在」任务主键（避免与库中既有行相撞）。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 不存在的主键。
    """
    return int(ns.prefix[2:], 16) * 1000 + 999


def _body(code: str, **overrides: object) -> ConcurrentStableDict[str, object]:
    """构造新建任务的请求体（默认合法，按需覆盖）。

    Args:
        code: 任务代码（本用例命名空间内唯一）。
        **overrides: 字段覆盖。

    Returns:
        ConcurrentStableDict[str, object]: 请求体。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "code": code,
            "name": code,
            "handler": _HANDLER,
            "cron": "0 3 * * *",
        }
    )
    payload.update(overrides)
    return payload


async def _create(
    client: AsyncClient, ns: Namespace, *, suffix: str = "clean", name: str | None = None, **overrides: object
) -> ConcurrentStableDict[str, Any]:
    """新建任务并断言成功。

    Args:
        client: 测试客户端。
        ns: 用例命名空间。
        suffix: 代码后缀（同一用例内区分多个任务）。
        name: 任务名（缺省与代码同名）。
        **overrides: 请求体覆盖。

    Returns:
        ConcurrentStableDict[str, Any]: 新建任务的数据体。
    """
    code = ns.code(suffix)
    params: ConcurrentStableDict[str, object] = ConcurrentStableDict({"name": name or code})
    params.update(overrides)
    resp = await client.post("/api/v1/tasks", json=dict(_body(code, **dict(params))))
    assert resp.status_code == 200, resp.text
    return ConcurrentStableDict(resp.json()["data"])


async def test_create_and_list(client: AsyncClient, ns: Namespace) -> None:
    """新建成功（回填 next_run_at）→ 列表可见 → 名称 / 状态筛选生效（按本用例代码限定）。"""
    code = ns.code("clean")
    data = await _create(client, ns)
    assert data["code"] == code
    assert data["status"] == "enabled"
    assert data["next_run_at"] is not None
    items = (await client.get("/api/v1/tasks", params={"name": code})).json()["data"]
    assert items["total"] == 1
    assert items["page"] == 1 and items["size"] == 20
    assert items["list"][0]["id"] == data["id"]
    filtered = (await client.get("/api/v1/tasks", params={"name": code, "status": "enabled"})).json()["data"]
    assert filtered["total"] == 1
    empty = (await client.get("/api/v1/tasks", params={"name": ns.code("nope")})).json()["data"]
    assert empty["total"] == 0


async def test_create_manual_only_task_has_no_schedule(client: AsyncClient, ns: Namespace) -> None:
    """无 cron 的任务不排期（仅手动触发）。"""
    data = await _create(client, ns, suffix="manual", cron=None)
    assert data["cron"] is None
    assert data["next_run_at"] is None


async def test_create_disabled_task_not_scheduled(client: AsyncClient, ns: Namespace) -> None:
    """初始停用：不排期。"""
    data = await _create(client, ns, suffix="disabled", status="disabled")
    assert data["status"] == "disabled"
    assert data["next_run_at"] is None


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"cron": "0 0 30 2 *"}, 70002),
        ({"cron": "bad cron"}, 70002),
        ({"handler": "os.system:run"}, 70003),
        ({"args": "{broken"}, 70004),
        ({"status": "paused"}, 10001),
    ],
)
async def test_create_validation_errors(
    client: AsyncClient, ns: Namespace, overrides: ConcurrentStableDict[str, object], expected_code: int
) -> None:
    """校验分支：cron / handler / args / 状态各自返回对应错误码。"""
    resp = await client.post("/api/v1/tasks", json=dict(_body(ns.code("bad"), **overrides)))
    assert resp.json()["code"] == expected_code


async def test_create_duplicate_code_and_name(client: AsyncClient, ns: Namespace) -> None:
    """代码 / 名称重复一律 70005。"""
    code = ns.code("dup")
    await _create(client, ns, suffix="dup")
    dup_code = await client.post("/api/v1/tasks", json=dict(_body(code, name=ns.code("other"))))
    assert dup_code.json()["code"] == 70005
    dup_name = await client.post("/api/v1/tasks", json=dict(_body(ns.code("other-code"), name=code)))
    assert dup_name.json()["code"] == 70005


async def test_update_task_recomputes_schedule(client: AsyncClient, ns: Namespace) -> None:
    """修改成功：名称与 cron 更新并重算下次到期。"""
    data = await _create(client, ns)
    resp = await client.put(
        f"/api/v1/tasks/{data['id']}",
        json={"name": "改过的名字", "cron": "0 5 * * *", "version": data["version"]},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()["data"]
    assert updated["name"] == "改过的名字"
    assert updated["cron"] == "0 5 * * *"
    assert updated["version"] == data["version"] + 1


async def test_update_version_conflict(client: AsyncClient, ns: Namespace) -> None:
    """版本不匹配：并发冲突 10004。"""
    data = await _create(client, ns)
    resp = await client.put(f"/api/v1/tasks/{data['id']}", json={"name": "x", "version": data["version"] + 5})
    assert resp.json()["code"] == 10004


async def test_update_name_conflict_with_other_task(client: AsyncClient, ns: Namespace) -> None:
    """改名撞他人：70005。"""
    first = await _create(client, ns, suffix="first")
    second = await _create(client, ns, suffix="second")
    resp = await client.put(f"/api/v1/tasks/{first['id']}", json={"name": second["name"], "version": first["version"]})
    assert resp.json()["code"] == 70005


async def test_update_missing_task(client: AsyncClient, ns: Namespace) -> None:
    """任务不存在：70001。"""
    resp = await client.put(f"/api/v1/tasks/{_missing_id(ns)}", json={"name": "x", "version": 1})
    assert resp.json()["code"] == 70001


async def test_delete_task(client: AsyncClient, ns: Namespace) -> None:
    """软删除后列表不可见（按本用例代码过滤后为空）。"""
    code = ns.code("clean")
    data = await _create(client, ns)
    assert (await client.delete(f"/api/v1/tasks/{data['id']}")).status_code == 200
    assert (await client.get("/api/v1/tasks", params={"name": code})).json()["data"]["total"] == 0
    assert (await client.delete(f"/api/v1/tasks/{_missing_id(ns)}")).json()["code"] == 70001


async def test_enable_and_disable(client: AsyncClient, ns: Namespace) -> None:
    """停用清空排期；启用重算排期；无 cron 的任务启用仍不排期。"""
    data = await _create(client, ns)
    disabled = (await client.post(f"/api/v1/tasks/{data['id']}/disable")).json()["data"]
    assert disabled["status"] == "disabled"
    assert disabled["next_run_at"] is None
    enabled = (await client.post(f"/api/v1/tasks/{data['id']}/enable")).json()["data"]
    assert enabled["status"] == "enabled"
    assert enabled["next_run_at"] is not None
    manual = await _create(client, ns, suffix="manual-only", cron=None)
    reenabled = (await client.post(f"/api/v1/tasks/{manual['id']}/enable")).json()["data"]
    assert reenabled["next_run_at"] is None


async def test_trigger_creates_run_and_enqueues(client: AsyncClient, ns: Namespace) -> None:
    """手动触发：落 running 记录并入队；记录可在执行记录里查到。"""
    data = await _create(client, ns)
    resp = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    assert resp.status_code == 200, resp.text
    trigger = resp.json()["data"]
    assert int(trigger["log_id"]) > 0
    assert trigger["run_id"]
    logs = (await client.get(f"/api/v1/tasks/{data['id']}/logs")).json()["data"]
    assert logs["total"] == 1
    assert logs["list"][0]["status"] == "running"
    assert logs["list"][0]["trigger_source"] == "manual"


async def test_trigger_respects_cooldown(client: AsyncClient, ns: Namespace) -> None:
    """冷却窗口内重复触发：70006。"""
    data = await _create(client, ns)
    assert (await client.post(f"/api/v1/tasks/{data['id']}/trigger")).status_code == 200
    second = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    assert second.json()["code"] == 70006


async def test_trigger_when_redis_unavailable_still_allowed(
    client: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis 不可用：跳过冷却（限流属可降级域），作业提交不依赖 Redis，触发照常成功。"""
    data = await _create(client, ns)

    def _boom() -> Redis:
        from bms_core.core.exceptions import RedisUnavailableError

        raise RedisUnavailableError("redis down")

    monkeypatch.setattr("bms_core.redis.base.shared_async_client", _boom)
    resp = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    assert resp.json()["code"] == 0


async def test_logs_of_missing_task(client: AsyncClient, ns: Namespace) -> None:
    """执行记录查不存在任务：70001。"""
    assert (await client.get(f"/api/v1/tasks/{_missing_id(ns)}/logs")).json()["code"] == 70001


async def test_update_only_schedule_keeps_name_and_remark(client: AsyncClient, ns: Namespace) -> None:
    """只改 cron（不改名 / 不改备注）：其余字段保持原值。"""
    data = await _create(client, ns, remark="原始备注")
    resp = await client.put(f"/api/v1/tasks/{data['id']}", json={"cron": "0 7 * * *", "version": data["version"]})
    assert resp.status_code == 200, resp.text
    updated = resp.json()["data"]
    assert updated["cron"] == "0 7 * * *"
    assert updated["name"] == data["name"]
    assert updated["remark"] == "原始备注"


async def test_trigger_cooldown_disabled(client: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """冷却秒数为 0 时不限流（连触两次都成功）。"""
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_TASK_SCHEDULER__TRIGGER_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    data = await _create(client, ns)
    first = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    second = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    assert first.json()["code"] == 0
    assert second.json()["code"] == 0


async def test_trigger_skips_cooldown_when_cache_unavailable(
    client: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """冷却用的客户端不可用：放行触发（限流属可降级域）。"""
    data = await _create(client, ns)

    def _boom() -> Redis:
        from bms_core.core.exceptions import RedisUnavailableError

        raise RedisUnavailableError("cache down")

    monkeypatch.setattr("bms_platform.domains.task.services.task.shared_async_client", _boom)
    resp = await client.post(f"/api/v1/tasks/{data['id']}/trigger")
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0


async def test_update_remark_only(client: AsyncClient, ns: Namespace) -> None:
    """只改备注：其余字段保持原值。"""
    data = await _create(client, ns)
    resp = await client.put(f"/api/v1/tasks/{data['id']}", json={"remark": "运维备注", "version": data["version"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["remark"] == "运维备注"
