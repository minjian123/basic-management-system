"""用户完整域管理面用例（Kiwi 2270；任务 02_01）。

覆盖：`/api/v1/users` 新建（含初始密码生成与幂等键）/ 列表（关键字四字段）/ 详情 / 修改（乐观锁）/
启停（会话失效）/ 删除（引用校验、闭锁、用户名复用）/ 重置密码（策略与历史）/ 角色查看，
以及错误码登记、内置与自身保护、事件发射（载荷不含组织字段）。
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_idempotency_store, get_outbox_store, get_service_client, get_uow
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import (
    ServiceUnavailableError,
    UsernameExistsError,
    UserNotFoundError,
    UserProtectedError,
    UserReferencedError,
)
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.idempotency.base import DEFAULT_IDEMPOTENCY_TTL, IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore
from bms_core.models.base import Base
from bms_core.outbox.null import NullOutboxStore
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_platform.models.role import ROLE_TYPE_SYSTEM, SysRole, SysUserRole
from bms_platform.models.user import SysAccountLock, SysUser
from tests_support.permission_admin import setup_min_tenant

API = "/api/v1/users"
REVOKE_PATH = "/api/v1/identity/internal/sessions/revoke-user"
PASSWORD = "Abcd1234!x"


def _now() -> datetime:
    """当前 UTC naive 时间。

    Returns:
        datetime: UTC naive 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _json(response: Response) -> ConcurrentStableDict[str, object]:
    """取响应 JSON 对象。

    Args:
        response: 响应。

    Returns:
        ConcurrentStableDict[str, object]: 响应体。
    """
    return cast("ConcurrentStableDict[str, object]", response.json())


def _code(response: Response) -> int:
    """取响应业务码。

    Args:
        response: 响应。

    Returns:
        int: 业务码。
    """
    return int(cast("int", _json(response)["code"]))


def _data(response: Response) -> ConcurrentStableDict[str, object]:
    """取响应 `data`（并断言成功）。

    Args:
        response: 响应。

    Returns:
        ConcurrentStableDict[str, object]: 响应 data。
    """
    payload = _json(response)
    assert payload["code"] == 0, payload
    return cast("ConcurrentStableDict[str, object]", payload["data"])


def _user_of(data: ConcurrentStableDict[str, object]) -> ConcurrentStableDict[str, object]:
    """取 `data.user`。

    Args:
        data: 响应 data。

    Returns:
        ConcurrentStableDict[str, object]: 用户对象。
    """
    return cast("ConcurrentStableDict[str, object]", data["user"])


def _uid(data: ConcurrentStableDict[str, object]) -> int:
    """取 `data.user.id`（雪花 id 字符串化）。

    Args:
        data: 响应 data。

    Returns:
        int: 用户主键。
    """
    return int(cast("str", _user_of(data)["id"]))


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """真实权限校验所需的最小租户库 + 内置系统管理员主体。

    Args:
        tmp_path_factory: pytest 临时目录工厂。
        monkeypatch: pytest 环境变量覆盖夹具。
    """
    await setup_min_tenant(tmp_path_factory, monkeypatch)


class RecordingOutbox(NullOutboxStore):
    """测试替身：记录入队事件（不落库）。"""

    plugin_name: str = "admin_recording"

    def __init__(self) -> None:
        """初始化（空事件列表）。"""
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    async def enqueue(self, session: DbSession, event: EventEnvelope) -> str:
        """记录事件并回显 ID。

        Args:
            session: 业务会话（替身忽略）。
            event: 事件信封。

        Returns:
            str: 事件 ID。
        """
        del session
        self.events.add(event)
        return event.event_id or "recording"


class StubServiceClient(BaseServiceClient):
    """测试替身：记录跨服务调用并可模拟不可达。"""

    plugin_name: str = "admin_session_stub"

    def __init__(self) -> None:
        """初始化（无失败、空调用记录）。"""
        self.calls: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
        self.revoked = 2
        self.fail = False

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录调用并返回统一响应。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 统一响应。

        Raises:
            ServiceUnavailableError: 开关打开时模拟不可达（10007）。
        """
        if self.fail:
            raise ServiceUnavailableError("identity 不可达")
        body = request.json_body or ConcurrentStableDict()
        self.calls.add((request.path, body))
        payload = f'{{"code": 0, "message": "ok", "data": {{"revoked": {self.revoked}}}}}'
        return ServiceResponse(status_code=200, content=payload.encode())


class MemoryIdempotency(IdempotencyStore):
    """测试替身：内存幂等键（首次 True + 结果复用）。"""

    plugin_name: str = "admin_memory_idem"

    def __init__(self) -> None:
        """初始化（空键集）。"""
        self.seen: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """前置去重。

        Args:
            key: 幂等 key。
            ttl: 键有效期（忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        return key not in self.seen

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果。

        Args:
            key: 幂等 key。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果。
        """
        return self.seen.get(key)

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """写首次结果。

        Args:
            key: 幂等 key。
            payload: 首次结果载荷。
            ttl: 键有效期（忽略）。
        """
        del ttl
        self.seen.set(key, payload)


class _Harness:
    """用例夹具：临时库 + 依赖替身。"""

    def __init__(self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化。

        Args:
            engine: 临时库引擎。
            factory: 会话工厂。
        """
        self.engine = engine
        self.factory = factory
        self.outbox = RecordingOutbox()
        self.sessions = StubServiceClient()
        self.idempotency = MemoryIdempotency()

    async def close(self) -> None:
        """释放引擎。"""
        await self.engine.dispose()

    async def grant_role(self, user_id: int, *, role_type: str = ROLE_TYPE_SYSTEM) -> int:
        """直插角色并分配给用户。

        Args:
            user_id: 用户主键。
            role_type: 角色类型（默认内置系统管理员）。

        Returns:
            int: 角色主键。
        """
        async with self.factory() as session:
            role = SysRole(code=f"r_{role_type}_{user_id}", name="测试角色", status="enabled", role_type=role_type)
            session.add(role)
            await session.flush()
            session.add(SysUserRole(role_id=role.id, user_id=user_id))
            await session.commit()
            return role.id

    async def unassign_all(self, user_id: int) -> None:
        """物理删除该用户全部角色分配（绕过服务层）。

        Args:
            user_id: 用户主键。
        """
        async with self.factory() as session:
            rows = (await session.execute(select(SysUserRole).where(SysUserRole.user_id == user_id))).scalars().all()
            for row in rows:
                await session.delete(row)
            await session.commit()

    async def add_open_lock(self, user_id: int) -> None:
        """插入一条未解锁锁定记录。

        Args:
            user_id: 用户主键。
        """
        async with self.factory() as session:
            session.add(SysAccountLock(user_id=user_id, lock_type="manual", locked_at=_now(), reason="测试锁定"))
            await session.commit()

    async def user_row(self, user_id: int) -> SysUser:
        """取用户行（绕过 HTTP）。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser: 用户行。
        """
        async with self.factory() as session:
            return (await session.execute(select(SysUser).where(SysUser.id == user_id))).scalar_one()

    async def lock_rows(self, user_id: int) -> ConcurrentStableList[SysAccountLock]:
        """取该用户锁定记录。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysAccountLock]: 锁定记录列表。
        """
        async with self.factory() as session:
            rows = await session.execute(select(SysAccountLock).where(SysAccountLock.user_id == user_id))
            return ConcurrentStableList(rows.scalars().all())


async def _harness(tmp_path: Path, service_app: FastAPI) -> _Harness:
    """建文件级 SQLite 库 + 覆盖依赖（会话 / 发件箱 / 服务客户端 / 幂等）。

    Args:
        tmp_path: pytest 临时目录。
        service_app: 应用实例。

    Returns:
        _Harness: 用例夹具。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    tables = [
        cast("Table", SysUser.__table__),
        cast("Table", SysRole.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysAccountLock.__table__),
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    harness = _Harness(engine, factory)
    service_app.dependency_overrides[get_uow] = lambda: DbUnitOfWork(factory())
    service_app.dependency_overrides[get_outbox_store] = lambda: harness.outbox
    service_app.dependency_overrides[get_service_client] = lambda: harness.sessions
    service_app.dependency_overrides[get_idempotency_store] = lambda: harness.idempotency
    return harness


async def _create(
    client: AsyncClient,
    *,
    username: str = "alice",
    name: str = "爱丽丝",
    password: str | None = PASSWORD,
    **extra: object,
) -> ConcurrentStableDict[str, object]:
    """经端点新建用户并返回 `data`。

    Args:
        client: 测试客户端。
        username: 登录账号。
        name: 昵称。
        password: 初始密码（None = 后端生成）。
        **extra: 其他请求字段。

    Returns:
        ConcurrentStableDict[str, object]: 响应 data。
    """
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict({"username": username, "name": name})
    if password is not None:
        body.set("password", password)
    for key, value in extra.items():
        body.set(key, value)
    return _data(await client.post(API, json=dict(body)))


@pytest.mark.kiwi_id(2270)
def test_user_error_codes_registered() -> None:
    """用户域错误码 `30002` / `30003` / `30009` / `30011` 与异常子段登记。"""
    assert ErrorCode.USER_NOT_FOUND == 30002
    assert ErrorCode.USERNAME_EXISTS == 30003
    assert ErrorCode.USER_PROTECTED == 30009
    assert ErrorCode.USER_REFERENCED == 30011
    assert UserNotFoundError().http_status == 404
    assert UsernameExistsError().http_status == 409
    assert UserProtectedError().http_status == 403
    assert UserReferencedError().http_status == 409


@pytest.mark.kiwi_id(2270)
async def test_create_list_detail_update(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """新建（生成初始密码）/ 列表关键字四字段 / 详情 / 修改与乐观锁冲突 / 事件发射。"""
    harness = await _harness(tmp_path, service_app)

    created = await _create(client, password=None, email="alice@example.com", phone="13800000001")
    user = _user_of(created)
    assert created["initial_password"]
    assert user["username"] == "alice"
    assert user["status"] == "enabled"
    assert user["version"] == 1
    assert "password_hash" not in user
    user_id = _uid(created)

    duplicated = await client.post(API, json={"username": "alice", "name": "重复", "password": PASSWORD})
    assert _code(duplicated) == 30003

    for keyword in ("ali", "爱丽丝", "alice@example.com", "13800000001"):
        listed = _data(await client.get(API, params={"kw": keyword}))
        assert listed["total"] == 1, keyword
        rows = cast("ConcurrentStableList[ConcurrentStableDict[str, object]]", listed["list"])
        assert rows[0]["last_login_at"] is None

    detail = _data(await client.get(f"{API}/{user_id}"))
    assert detail["email"] == "alice@example.com"

    updated = _data(await client.put(f"{API}/{user_id}", json={"name": "爱丽丝改", "version": 1}))
    assert updated["name"] == "爱丽丝改"

    stale = await client.put(f"{API}/{user_id}", json={"name": "过期版本", "version": 1})
    assert _code(stale) == 10004  # 乐观锁冲突（ConcurrentConflictError）

    missing = await client.get(f"{API}/999999")
    assert _code(missing) == 30002

    assert [event.event_type for event in harness.outbox.events] == ["sys.user.created", "sys.user.updated"]
    assert "dept_id" not in harness.outbox.events[0].payload
    assert harness.outbox.events[0].payload["user_id"] == str(user_id)

    await harness.close()


@pytest.mark.kiwi_id(2270)
async def test_status_protection_and_session_revoke(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """启停：会话失效调用、重复停用幂等、内置管理员与自身保护、会话不可达降级。"""
    harness = await _harness(tmp_path, service_app)
    created = await _create(client, username="bob")
    user_id = _uid(created)

    disabled = _data(await client.put(f"{API}/{user_id}/status", json={"status": "disabled"}))
    assert disabled["session_revoked"] is True
    assert harness.sessions.calls[-1][0] == REVOKE_PATH
    assert harness.sessions.calls[-1][1]["reason"] == "user_disabled"

    again = _data(await client.put(f"{API}/{user_id}/status", json={"status": "disabled"}))
    assert again["session_revoked"] is False

    invalid = await client.put(f"{API}/{user_id}/status", json={"status": "unknown"})
    assert _code(invalid) == 10001

    enabled = _data(await client.put(f"{API}/{user_id}/status", json={"status": "enabled"}))
    assert enabled["session_revoked"] is False  # 启用不失效会话

    # 会话撤销跨服务不可达：不阻断主流程（状态已改、session_revoked 显式暴露）
    other = await _create(client, username="bob2")
    other_id = _uid(other)
    harness.sessions.fail = True
    degraded = _data(await client.put(f"{API}/{other_id}/status", json={"status": "disabled"}))
    assert degraded["session_revoked"] is False
    assert (await harness.user_row(other_id)).status == "disabled"
    harness.sessions.fail = False

    await harness.grant_role(user_id)
    protected = await client.put(f"{API}/{user_id}/status", json={"status": "disabled"})
    assert _code(protected) == 30009
    assert _code(await client.delete(f"{API}/{user_id}")) == 30009

    await harness.close()


@pytest.mark.kiwi_id(2270)
async def test_delete_reference_lock_and_reuse(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """删除：引用校验 30011、关闭锁定记录、用户名可复用、会话失效与不可达降级。"""
    harness = await _harness(tmp_path, service_app)
    created = await _create(client, username="carol")
    user_id = _uid(created)
    await harness.grant_role(user_id, role_type="custom")

    assert _code(await client.delete(f"{API}/{user_id}")) == 30011

    await harness.unassign_all(user_id)
    await harness.add_open_lock(user_id)
    deleted = _data(await client.delete(f"{API}/{user_id}"))
    assert deleted == {"deleted": True, "session_revoked": True}
    assert harness.sessions.calls[-1][1]["reason"] == "user_deleted"

    locks = await harness.lock_rows(user_id)
    assert locks and locks[0].unlock_at is not None and locks[0].unlock_mode == "auto"

    recreated = await _create(client, username="carol", name="新卡罗尔")
    assert _user_of(recreated)["username"] == "carol"
    assert _uid(recreated) != user_id

    await harness.close()


@pytest.mark.kiwi_id(2270)
async def test_password_reset_policy_history_and_revoke(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """重置密码：复杂度 30005、历史重复 30006、字段写入与会话失效。"""
    harness = await _harness(tmp_path, service_app)
    created = await _create(client, username="dave")
    user_id = _uid(created)

    weak = await client.put(f"{API}/{user_id}/password", json={"new_password": "weak", "force_change": True})
    assert _code(weak) == 30005

    reused = await client.put(f"{API}/{user_id}/password", json={"new_password": PASSWORD, "force_change": True})
    assert _code(reused) == 30006

    ok = _data(
        await client.put(f"{API}/{user_id}/password", json={"new_password": "Zyxw9876!q", "force_change": False})
    )
    assert ok["reset"] is True and ok["session_revoked"] is True
    assert harness.sessions.calls[-1][1]["reason"] == "password_reset"

    row = await harness.user_row(user_id)
    assert row.pwd_history and row.pwd_changed_at is not None
    assert row.pwd_reset_required is False
    # 历史存旧密码哈希（非明文），且新哈希已生效
    assert len(cast("ConcurrentStableList[str]", json.loads(row.pwd_history))) == 1
    assert row.password_hash != json.loads(row.pwd_history)[0]

    missing = await client.put(f"{API}/999999/password", json={"new_password": "Zyxw9876!q"})
    assert _code(missing) == 30002

    await harness.close()


@pytest.mark.kiwi_id(2270)
async def test_create_idempotency_and_roles(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """幂等键重复不重复建号；`GET /users/{id}/roles` 返回角色码 / 名称 / 类型。"""
    harness = await _harness(tmp_path, service_app)

    body = {"username": "erin", "name": "艾琳", "password": PASSWORD}
    first = _data(await client.post(API, json=body, headers={"Idempotency-Key": "k1"}))
    user_id = _uid(first)

    second = _data(await client.post(API, json=body, headers={"Idempotency-Key": "k1"}))
    assert _uid(second) == user_id
    assert second["initial_password"] is None
    assert _data(await client.get(API))["total"] == 1

    await harness.grant_role(user_id, role_type="custom")
    roles = _data(await client.get(f"{API}/{user_id}/roles"))
    items = cast("ConcurrentStableList[ConcurrentStableDict[str, object]]", roles["items"])
    assert len(items) == 1
    assert items[0]["role_type"] == "custom"
    assert cast("str", items[0]["role_code"]).startswith("r_custom")

    await harness.close()
