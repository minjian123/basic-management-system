"""能力分配授权端点与服务（07B `02_04`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 1~6、14~20 的端到端部分：

- 管理面：分页筛选、人工授予（幂等 UPSERT / 能力与消费方须已登记 / 临时授权参数成对）、
  软撤销（不删行、重复撤销幂等、不存在 10002）；
- 声明同步：新建 / 声明移除置撤销 / 声明回归恢复，变更经审计捕获、有效授权数指标刷新；
- 内部授权视图：`provider` / `consumer` 二选一、维度越界即拒（403）、登录态按权限码放行。
"""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import AuthError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import DbSession, session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.capability_grant import (
    GRANT_NOTE_DECLARED,
    GRANT_NOTE_REMOVED,
    GRANT_SOURCE_DECLARED,
    GRANT_SOURCE_MANUAL,
    GRANT_STATUS_DISABLED,
    GRANT_STATUS_ENABLED,
    SysCapabilityGrant,
)
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.services.module_registry import (
    CollaborationRecord,
    collaboration_catalog_view,
    domain_service_view,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)
from bms_core.testing.locks import file_lock
from bms_core.testing.namespace import Namespace
from bms_platform.domains.platform_registry.repositories.capability_grant import CapabilityGrantRepository
from bms_platform.domains.platform_registry.services.capability_grant import CapabilityGrantService
from tests_support.metrics import RecordingMetrics
from tests_support.permission_admin import setup_min_tenant

API = "/api/v1/capability-grants"
INTERNAL_API = "/api/v1/platform/internal/capability-grants"

CONSUMER = "platform"
"""消费方取真实服务键：授权表唯一键是「能力 × 消费方」，能力名带命名空间即已唯一，
消费方若也命名空间化就不再是已登记服务键（授予前校验直接 10001）。"""


def _grant_domain(ns: Namespace) -> str:
    """本用例能力所属业务域（带命名空间前缀）。

    域键形态是小写字母开头、仅小写字母 / 数字 / 下划线，故用 `grant_<前缀>`。
    命名空间化是为了让「按 provider 维度取授权视图」只命中本用例写入的行——
    真实域 `mdm` 在共享库里有装配期落库的声明行，固定域会让断言随库里数据漂移。

    Args:
        ns: 用例命名空间。

    Returns:
        str: 业务域标识。
    """
    return f"grant_{ns.prefix}"


def _capability_of(ns: Namespace) -> str:
    """本用例的能力名（`demo.<命名空间域>.user-roles`）。

    Args:
        ns: 用例命名空间。

    Returns:
        str: 能力名（跨 worker / 跨轮次不相交）。
    """
    return f"demo.{_grant_domain(ns)}.user-roles"


@pytest.fixture
def capability(ns: Namespace) -> str:
    """本用例的能力名（带命名空间，替代原先的固定键 `demo.mdm.user-roles`）。

    Args:
        ns: 用例命名空间。

    Returns:
        str: 能力名。
    """
    return _capability_of(ns)


async def _grant_of(session: DbSession, capability: str, consumer: str) -> SysCapabilityGrant | None:
    """按「能力 × 消费方」取当前行（按本用例数据断言，不依赖全表计数）。

    Args:
        session: 平台库会话。
        capability: 能力名。
        consumer: 消费方服务键。

    Returns:
        SysCapabilityGrant | None: 未软删的那一行；不存在为 None。
    """
    result = await session.execute(
        select(SysCapabilityGrant).where(
            SysCapabilityGrant.capability_name == capability,
            SysCapabilityGrant.consumer_key == consumer,
            SysCapabilityGrant.deleted_at.is_(None),
        )
    )
    return result.scalars().first()


class _RecordingAudit:
    """审计捕获替身：记录每次 `capture` 的表名 / 主键 / 新状态 / 操作人。"""

    def __init__(self) -> None:
        """初始化。"""
        self.calls: ConcurrentStableList[tuple[str, int, str, object]] = ConcurrentStableList()

    def is_audited(self, table: str) -> bool:
        """恒纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: True。
        """
        del table
        return True

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[object],
        actor: int | None = None,
    ) -> object:
        """记录一次审计捕获。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更列表。
            actor: 操作人。

        Returns:
            object: 占位事件信封（用例只断言调用参数）。
        """
        new_status = ""
        for change in changes:
            new_status = str(getattr(change, "new", ""))
        self.calls.add((table, model_id, new_status, actor))
        return object()


class _StubVerifier:
    """令牌校验替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串（即服务标识）。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        del audience
        if token in ("platform", "mdm"):
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


def _record(ns: Namespace, *, consumers: ConcurrentStableFrozenList[str] | None = None) -> CollaborationRecord:
    """构造本用例的能力记录（读出口，缺省默认消费方为 platform）。

    Args:
        ns: 用例命名空间（能力名与业务域都带前缀）。
        consumers: 默认消费方（空表示声明里没有消费方）。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=_capability_of(ns),
        domain=_grant_domain(ns),
        kind="read",
        contract_version="0.1.0",
        path="/api/v1/demo/user-roles",
        product_key="demo",
        frontend_prefix="demo",
        default_consumers=(
            ConcurrentStableFrozenList((CONSUMER,)) if consumers is None else ConcurrentStableFrozenList(consumers)
        ),
    )


@pytest.fixture(autouse=True)
async def _admin_subject(tenant_db: str) -> None:
    """把测试主体置为内置系统管理员（**真实授权**，不换检查器）。

    管理面 / 内部视图的**权限码挂载**属路由契约，权限码级判定由权限引擎专项用例覆盖；
    本套用例只验端点语义。装配常驻后不能再靠 `BMS_PERMISSION__PROVIDER=null` 切实现——
    权限检查器在装配期就建好，逐例改环境变量读不到；改为像真实运行一样准备授权数据
    （主体命中内置管理员豁免层级，13_10 口径）。

    Args:
        tenant_db: 共享测试租户库连接串（授权数据落这里）。
    """
    assert tenant_db
    await setup_min_tenant(tenant_db)


@pytest.fixture(autouse=True)
def _grant_global_serial() -> Iterator[None]:
    """能力授权是共享库上的**全局状态**：用专用文件锁串行，避免多 worker 同删同建。

    数据库门只按单次读写取放，无法承担「整段全局状态」的独占；文件锁是本用例组专用的
    串行开关（心跳兜底陈旧，等锁上限 120s 是排队预算，不是死锁等待）。

    Yields:
        None: 用例运行期。
    """
    with file_lock("platform-global-state", timeout=180.0):
        yield


@pytest.fixture(autouse=True)
def _isolate_grant_state(ns: Namespace, _grant_global_serial: None) -> Iterator[None]:
    """在**装配态目录之上**追加本用例的能力与业务域，用例结束原样恢复。

    为什么不再「清空目录 + 只装一条」：装配常驻后能力目录是装配期产物，清空会连带
    `platform` 自身的声明与对端声明一起消失；此时若用例跑到启动装配
    （`bootstrap_capability_grants`），同步会把共享库里所有真实声明判成「声明移除」并置撤销，
    污染其它 worker。改为「追加 + 恢复」：本用例仍拿到唯一命名空间，装配态不受损。

    Args:
        ns: 用例命名空间。
        _grant_global_serial: 整段全局状态的独占开关（依赖顺序）。

    Yields:
        None: 用例运行期。
    """
    previous_collaborations = collaboration_catalog_view()
    previous_domains = domain_service_view()
    register_collaboration_records((_record(ns),))
    register_domain_services(ConcurrentStableFrozenDict({_grant_domain(ns): "platform"}))
    try:
        yield
    finally:
        reset_collaboration_records()
        register_collaboration_records(previous_collaborations)
        reset_domain_services()
        register_domain_services(ConcurrentStableFrozenDict(previous_domains.to_list()))


@pytest_asyncio.fixture(autouse=True)
async def _clean_grants(
    ns: Namespace, _grant_global_serial: None, _admin_subject: None, service_app: FastAPI
) -> AsyncIterator[None]:
    """只清**本用例能力**的授权行（进入 / 退出各一次），并复位进程内授权缓存。

    不再删全局声明行（那会让别的 worker 重新同步并与本用例竞争）；也不再用整条用例回滚。

    Args:
        ns: 用例命名空间（本用例能力名唯一，删行不会波及他人）。
        service_app: 应用实例（启动钩子已执行）。
        _admin_subject: 保证授权主体先就位（依赖顺序；装配常驻后权限检查器不再逐例替换）。
        _grant_global_serial: 整段全局状态的独占开关（依赖顺序）。

    Yields:
        None: 用例运行期。
    """
    from bms_core.collaboration import reset_capability_grants

    name = _capability_of(ns)

    async def _purge() -> None:
        """删除本用例能力的授权行（Core 删除，不做 ORM 行数校验）。"""
        async with session_scope(
            service_app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=service_app.state.session_factory,
        ) as session:
            await session.execute(
                text("DELETE FROM sys_capability_grant WHERE capability_name = :capability"),
                {"capability": name},
            )

    await _purge()
    reset_capability_grants()
    yield
    await _purge()
    reset_capability_grants()


@pytest.mark.anyio
async def test_grant_is_idempotent_and_listed(client: AsyncClient, capability: str) -> None:
    """人工授予：首次新建、重复授予复用同一行；清单按能力筛选命中。"""
    first = await client.post(API, json={"capability_name": capability, "consumer_key": CONSUMER})
    assert first.status_code == 200
    granted = first.json()["data"]
    assert granted["source"] == GRANT_SOURCE_MANUAL
    assert granted["status"] == GRANT_STATUS_ENABLED
    assert granted["revoked_at"] is None

    second = await client.post(API, json={"capability_name": capability, "consumer_key": CONSUMER})
    assert second.json()["data"]["id"] == granted["id"]

    listed = await client.get(API, params={"capability_name": capability})
    rows = listed.json()["data"]["list"]
    assert [row["id"] for row in rows] == [granted["id"]]


@pytest.mark.anyio
async def test_grant_rejects_unregistered_capability_and_consumer(client: AsyncClient, capability: str) -> None:
    """入库前校验：能力未登记 / 消费方未登记均按参数非法拒绝（10001）。"""
    unknown_capability = await client.post(API, json={"capability_name": "demo.mdm.ghost", "consumer_key": CONSUMER})
    assert unknown_capability.json()["code"] == 10001

    unknown_consumer = await client.post(API, json={"capability_name": capability, "consumer_key": "ghost"})
    assert unknown_consumer.json()["code"] == 10001


@pytest.mark.anyio
async def test_temporary_grant_requires_expire_and_note(client: AsyncClient, capability: str) -> None:
    """临时授权：有效期与理由成对；过期时间必须晚于当前时间。"""
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    missing_note = await client.post(
        API, json={"capability_name": capability, "consumer_key": CONSUMER, "expire_at": future}
    )
    assert missing_note.json()["code"] == 10001

    past_expire = await client.post(
        API,
        json={"capability_name": capability, "consumer_key": CONSUMER, "expire_at": past, "note": "排障"},
    )
    assert past_expire.json()["code"] == 10001

    ok = await client.post(
        API,
        json={"capability_name": capability, "consumer_key": CONSUMER, "expire_at": future, "note": "排障"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["note"] == "排障"


@pytest.mark.anyio
async def test_temporary_grant_expire_at_read_back_is_utc(
    client: AsyncClient, service_app: FastAPI, capability: str
) -> None:
    """临时授权从库读回：naive datetime 补齐 UTC（`_to_grant` 的时区归一分支）。

    为什么要「读回」：授予响应由同一会话的 ORM 对象序列化，`expire_at` 仍带写入时的 tzinfo，
    归一分支走不到；SQLite 不存时区，重新查询得到 naive datetime 才会进入归一。

    Args:
        client: 测试客户端。
        service_app: 应用实例（取平台库引擎与会话工厂）。
    """
    future = datetime.now(UTC) + timedelta(hours=2)
    created = await client.post(
        API,
        json={
            "capability_name": capability,
            "consumer_key": CONSUMER,
            "expire_at": future.isoformat(),
            "note": "排障",
        },
    )
    assert created.status_code == 200

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        grants = await CapabilityGrantService(session)._current_grants()  # pyright: ignore[reportPrivateUsage]

    target = [
        grant
        for grant in grants
        if grant.capability_name == capability and grant.consumer_key == CONSUMER and grant.expire_at is not None
    ]
    assert len(target) == 1
    assert target[0].expire_at is not None
    assert target[0].expire_at.tzinfo is not None


@pytest.mark.anyio
async def test_revoke_is_soft_and_idempotent(client: AsyncClient, capability: str) -> None:
    """撤销：软撤销保留行（`disabled` + `revoked_at`）、重复撤销幂等、不存在 10002。"""
    created = await client.post(API, json={"capability_name": capability, "consumer_key": CONSUMER})
    grant_id = created.json()["data"]["id"]

    revoked = await client.delete(f"{API}/{grant_id}")
    assert revoked.status_code == 200
    body = revoked.json()["data"]
    assert body["status"] == GRANT_STATUS_DISABLED
    assert body["revoked_at"] is not None
    assert body["source"] == GRANT_SOURCE_MANUAL

    again = await client.delete(f"{API}/{grant_id}")
    assert again.json()["data"]["status"] == GRANT_STATUS_DISABLED

    missing = await client.delete(f"{API}/{int(grant_id) + 1}")
    assert missing.json()["code"] == 10002


class _MemoryGrantRepo:
    """内存仓储替身：只实现 `sync_declared()` 用到的几个方法（不连库）。

    行对象用 `SimpleNamespace` 承载——`_to_grant()` 只读六个字段，真 ORM 行的其余列
    在这条路径上不参与判定。`pair_where()` 用二元组表达谓词，替身的写方法认得它。
    """

    def __init__(self) -> None:
        """初始化空仓储与自增主键。"""
        self._rows: ConcurrentStableDict[tuple[str, str], SimpleNamespace] = ConcurrentStableDict()
        self._next_id = 1

    def pair_where(self, capability: str, consumer: str) -> tuple[str, str]:
        """按「能力 × 消费方」构造谓词。

        Args:
            capability: 能力名。
            consumer: 消费方标识。

        Returns:
            tuple[str, str]: 替身内部使用的键。
        """
        return (capability, consumer)

    async def insert_if_absent(self, values: ConcurrentStableDict[str, Any], *, match: tuple[str, str]) -> bool:
        """不存在才插入（与真仓储同语义）。

        Args:
            values: 待写入字段。
            match: 唯一键（`pair_where()` 的产物）。

        Returns:
            bool: 真正插入为 True，已存在为 False。
        """
        if match in self._rows:
            return False
        row = SimpleNamespace(
            id=self._next_id,
            capability_name=match[0],
            consumer_key=match[1],
            source=values["source"],
            status=values["status"],
            expire_at=None,
            note=values.get("note"),
            granted_at=values.get("granted_at"),
            revoked_at=None,
        )
        self._next_id += 1
        self._rows.set(match, row)
        return True

    async def update_where(self, where: tuple[str, str], *, values: ConcurrentStableDict[str, Any]) -> bool:
        """按谓词覆盖字段（行不存在返回 False）。

        Args:
            where: 唯一键（`pair_where()` 的产物）。
            values: 待覆盖字段。

        Returns:
            bool: 命中并更新为 True。
        """
        row = self._rows.get(where)
        if row is None:
            return False
        for key, value in values.items():
            setattr(row, key, value)
        return True

    async def get_by_pair(self, capability: str, consumer: str) -> SimpleNamespace | None:
        """按「能力 × 消费方」取行。

        Args:
            capability: 能力名。
            consumer: 消费方标识。

        Returns:
            SimpleNamespace | None: 行；不存在为 None。
        """
        return self._rows.get((capability, consumer))

    async def list_all(self) -> ConcurrentStableList[SimpleNamespace]:
        """取全部行。

        Returns:
            ConcurrentStableList[SimpleNamespace]: 全部行（插入序）。
        """
        return ConcurrentStableList(self._rows.values())


class _NullSession:
    """会话替身：`_write_scope()` 只调 `rollback()` 清自动事务，替身无事可做。"""

    async def rollback(self) -> None:
        """空实现（无真实事务）。"""


class _NullUow:
    """工作单元替身：`begin()` 只提供事务上下文，不连库。"""

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """事务上下文（无真实提交）。

        Yields:
            None: 作用域运行期。
        """
        yield


@pytest.mark.anyio
async def test_declared_sync_create_disable_restore_with_audit(ns: Namespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """声明同步：新建 → 声明移除置撤销 → 声明回归恢复；状态变更逐次经审计捕获。

    服务层单测（内存仓储替身，不连共享库）：`sync_declared()` 断的是**库的全局状态**，
    而共享库上其它 worker 的启动装配会把本用例造的 `demo.*` 行判为「声明移除」改成
    disabled（2026-11-23 末批实测：每 3 轮复现 1 次，窗口在同步提交与本用例重查之间）。
    三段语义与审计序列用替身完全覆盖；真库装配路径由
    `test_bootstrap_registers_source_and_warms_views`（共享库）继续覆盖。
    """
    capability = _capability_of(ns)
    # 本用例断的是「声明 → 计划」的**全序列**，需要一个只装本用例能力的目录：这里临时收窄成一条
    # （仓储是内存替身、不触共享库；用例结束由 `_isolate_grant_state` 恢复装配态目录）。
    reset_collaboration_records()
    register_collaboration_records((_record(ns),))
    audit = _RecordingAudit()
    repo = _MemoryGrantRepo()
    monkeypatch.setattr(CapabilityGrantService, "_repo", property(lambda _self: repo))
    service = CapabilityGrantService(
        cast("DbSession", _NullSession()),
        audit=audit,  # pyright: ignore[reportArgumentType]  # 结构化替身
        uow=cast("DbUnitOfWork", _NullUow()),
    )

    first = await service.sync_declared()
    assert (first.created, first.revoked, first.restored) == (1, 0, 0)
    row = await repo.get_by_pair(capability, CONSUMER)
    assert row is not None
    assert (row.source, row.status) == (GRANT_SOURCE_DECLARED, GRANT_STATUS_ENABLED)

    reset_collaboration_records()
    register_collaboration_records((_record(ns, consumers=ConcurrentStableFrozenList()),))
    second = await service.sync_declared()
    assert (second.created, second.revoked, second.restored) == (0, 1, 0)
    row = await repo.get_by_pair(capability, CONSUMER)
    assert row is not None
    assert (row.status, row.note) == (GRANT_STATUS_DISABLED, GRANT_NOTE_REMOVED)

    reset_collaboration_records()
    register_collaboration_records((_record(ns),))
    third = await service.sync_declared()
    assert (third.created, third.revoked, third.restored) == (0, 0, 1)
    row = await repo.get_by_pair(capability, CONSUMER)
    assert row is not None
    assert (row.status, row.note) == (GRANT_STATUS_ENABLED, GRANT_NOTE_DECLARED)

    changes = [change for _table, _id, change, _actor in audit.calls]
    # 仓储是替身、声明只有本用例一条：变更序列完全确定，不依赖全表计数。
    assert changes == [GRANT_STATUS_ENABLED, GRANT_STATUS_DISABLED, GRANT_STATUS_ENABLED]


@pytest.mark.anyio
async def test_declared_sync_skips_insert_when_row_appears(
    service_app: FastAPI, capability: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发启动收敛：计划判「需新增」而库里已有同键行时，原子插入跳过（不产生重复行）。"""

    async def _empty(self: CapabilityGrantRepository) -> ConcurrentStableList[SysCapabilityGrant]:
        """伪造「库内无现状」，逼出 `plan.creates`（模拟两进程读到同一份空现状）。

        Args:
            self: 仓储（结构性替身，不使用）。

        Returns:
            ConcurrentStableList[SysCapabilityGrant]: 空清单。
        """
        del self
        return ConcurrentStableList()

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        service = CapabilityGrantService(session, uow=DbUnitOfWork(session))
        await service.sync_declared()
        monkeypatch.setattr(CapabilityGrantRepository, "list_all", _empty)
        report = await service.sync_declared()
        assert report.created >= 1, "伪造空现状后计划里必须有新增项"
        rows = (
            (
                await session.execute(
                    select(SysCapabilityGrant).where(
                        SysCapabilityGrant.capability_name == capability,
                        SysCapabilityGrant.consumer_key == CONSUMER,
                        SysCapabilityGrant.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "同键已有行时原子插入必须跳过，不能插出第二行"


@pytest.mark.anyio
async def test_grant_refreshes_active_gauge(service_app: FastAPI, capability: str) -> None:
    """人工授予后按能力刷新有效授权数（gauge 带 `capability` 标签）。"""
    from bms_core.collaboration import METRIC_CAPABILITY_GRANT_ACTIVE

    metrics = RecordingMetrics()
    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        service = CapabilityGrantService(
            session,
            audit=_RecordingAudit(),  # pyright: ignore[reportArgumentType]  # 结构化替身
            metrics=metrics,
            uow=DbUnitOfWork(session),
        )
        await service.grant(capability_name=capability, consumer_key=CONSUMER, note="用例")
        await service.sync_declared()

    # 目录里还有装配期声明的真实能力，`sync_declared()` 会逐个能力刷 gauge：
    # 只按「本用例能力」标签取本次写入的那一条，不对全表序列下断言。
    gauges = [
        value
        for name, value, labels in metrics.gauges_labeled
        if name == METRIC_CAPABILITY_GRANT_ACTIVE and labels is not None and labels.get("capability") == capability
    ]
    assert gauges and gauges[-1] == 1.0


@pytest.mark.anyio
async def test_internal_view_provider_and_consumer_dimensions(
    client: AsyncClient,
    service_app: FastAPI,
    ns: Namespace,
    capability: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内部视图：登录态按 provider 维度取；服务身份只能读自身消费方或自身承载域。"""
    created = await client.post(API, json={"capability_name": capability, "consumer_key": CONSUMER})
    assert created.status_code == 200

    # provider 取本用例的命名空间域：真实域（如 mdm）在共享库里有装配期落库的声明行，
    # 用固定域断言「恰好一条」会随库里既有数据漂移。
    by_provider = await client.get(INTERNAL_API, params={"provider": _grant_domain(ns)})
    assert by_provider.status_code == 200
    assert [item["capability_name"] for item in by_provider.json()["data"]["grants"]] == [capability]

    # 令牌校验替身用 `monkeypatch` 装、用例结束自动卸：装配常驻后 `dependency_overrides`
    # 挂在会话级应用上，直接赋值会泄漏给同 worker 的后续用例。
    monkeypatch.setitem(service_app.dependency_overrides, get_token_verifier, lambda: _StubVerifier())
    own = await client.get(INTERNAL_API, params={"consumer": CONSUMER}, headers={"Authorization": "Bearer platform"})
    assert own.status_code == 200
    # 出站维度是全局视图（平台还有装配期声明的其它能力）：只断言「返回的都是本消费方的记录」。
    assert {item["consumer_key"] for item in own.json()["data"]["grants"]} == {CONSUMER}
    assert capability in [item["capability_name"] for item in own.json()["data"]["grants"]]

    foreign_consumer = await client.get(
        INTERNAL_API, params={"consumer": "mdm"}, headers={"Authorization": "Bearer platform"}
    )
    assert foreign_consumer.status_code == 403

    foreign_domain = await client.get(
        INTERNAL_API, params={"provider": "mdm"}, headers={"Authorization": "Bearer platform"}
    )
    assert foreign_domain.status_code == 403

    own_domain = await client.get(
        INTERNAL_API, params={"provider": "platform_registry"}, headers={"Authorization": "Bearer platform"}
    )
    assert own_domain.status_code == 200


@pytest.mark.anyio
async def test_internal_view_requires_single_dimension(client: AsyncClient) -> None:
    """内部视图：`provider` / `consumer` 未二选一即参数非法（10001）。"""
    missing = await client.get(INTERNAL_API)
    assert missing.json()["code"] == 10001

    both = await client.get(INTERNAL_API, params={"provider": "mdm", "consumer": CONSUMER})
    assert both.json()["code"] == 10001


@pytest.mark.anyio
async def test_list_filters_by_consumer_status_and_source(client: AsyncClient, capability: str) -> None:
    """清单筛选：消费方 / 状态 / 来源三个筛选条件均可组合（无匹配返回空清单）。"""
    created = await client.post(API, json={"capability_name": capability, "consumer_key": CONSUMER})
    grant_id = created.json()["data"]["id"]
    await client.delete(f"{API}/{grant_id}")

    by_status = await client.get(
        API,
        params={
            "status": GRANT_STATUS_DISABLED,
            "source": GRANT_SOURCE_MANUAL,
            "capability_name": capability,
        },
    )
    assert [row["id"] for row in by_status.json()["data"]["list"]] == [grant_id]

    by_consumer = await client.get(API, params={"consumer_key": CONSUMER, "capability_name": capability})
    assert by_consumer.json()["data"]["total"] == 1

    no_match = await client.get(API, params={"consumer_key": "mdm", "capability_name": capability})
    assert no_match.json()["data"]["list"] == []


@pytest.mark.anyio
async def test_service_rejects_invalid_view_dimension_and_missing_uow(service_app: FastAPI, capability: str) -> None:
    """服务层防御：视图维度未二选一（10001）/ 无工作单元写（配置错误）/ 无审计器时不写审计。"""
    from bms_core.core.exceptions import ConfigError, ParamError

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        read_only = CapabilityGrantService(session)
        with pytest.raises(ParamError):
            await read_only.view()
        with pytest.raises(ParamError):
            await read_only.view(provider="mdm", consumer=CONSUMER)
        with pytest.raises(ConfigError):
            await read_only.grant(capability_name=capability, consumer_key=CONSUMER)

        writable = CapabilityGrantService(session, uow=DbUnitOfWork(session))
        row = await writable.grant(capability_name=capability, consumer_key=CONSUMER)
        assert row.status == GRANT_STATUS_ENABLED


@pytest.mark.anyio
async def test_sync_keeps_manual_revocation_and_warns(service_app: FastAPI, capability: str) -> None:
    """人工撤销后再装载声明：记录保持撤销（不覆盖），同步报告含不一致警示。"""
    audit = _RecordingAudit()
    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        service = CapabilityGrantService(
            session,
            audit=audit,  # pyright: ignore[reportArgumentType]  # 结构化替身
            uow=DbUnitOfWork(session),
        )
        granted = await service.grant(capability_name=capability, consumer_key=CONSUMER)
        await service.revoke(granted.id)

        report = await service.sync_declared()
        row = await _grant_of(session, capability, CONSUMER)

    # 共享库上还有平台声明行：只断言「本用例这条人工撤销没有被声明覆盖」。
    assert report.created == 0
    assert any("声明与人工不一致" in message for message in report.warnings)
    assert row is not None
    assert (row.status, row.source) == (GRANT_STATUS_DISABLED, GRANT_SOURCE_MANUAL)


@pytest.mark.anyio
async def test_bootstrap_registers_source_and_warms_views(service_app: FastAPI, capability: str) -> None:
    """启动装配：重复执行幂等（登记来源 + 预热本服务承载域与自身消费方视图）。

    共享平台库：`_clean_grants` 在用例前后只清本用例夹具能力的授权行，装配会把它重新落库；
    并行 worker 的其他能力不在本用例断言范围内。
    """
    from bms_core.collaboration import capability_grant_pairs
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        bootstrap_capability_grants,
    )

    await bootstrap_capability_grants(service_app)
    # 再跑一次：登记来源幂等、视图预热不重复、授权行不重复
    await bootstrap_capability_grants(service_app)

    assert list(capability_grant_pairs(provider="platform_registry")) == []
    rows = capability_grant_pairs(consumer=CONSUMER)
    # 只断言本用例登记的能力：进程内可能还带着平台内置能力（如 notification.read）的声明，
    # 它们同样会被启动装配落库，不属于本用例的判定范围。
    mine = [(row.capability_name, row.source) for row in rows if row.capability_name == capability]
    assert mine == [(capability, GRANT_SOURCE_DECLARED)]


@pytest.mark.anyio
@pytest.mark.kiwi_id(2534)
async def test_bootstrap_grants_opens_two_scopes(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动装配的取门次数：声明比对（只读）1 次 +（有差异时）同步 1 次 + 预热 1 次。"""
    from bms_core.collaboration import reset_capability_grants
    from bms_platform.domains.platform_registry.services import capability_grant_bootstrap as bootstrap

    reset_capability_grants()
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    original = cast("Any", bootstrap.session_scope)

    def _counting(*args: object, **kwargs: object) -> Any:
        entered.add("enter")
        return original(*args, **kwargs)

    monkeypatch.setattr(bootstrap, "session_scope", _counting)
    await bootstrap.bootstrap_capability_grants(service_app)

    # 声明比对恒有一次；同步只在确有差异时发生（共享库已同步时为 2 次）
    assert len(entered) in (2, 3)


@pytest.mark.anyio
async def test_revoke_tolerates_capability_removed_from_catalog(service_app: FastAPI, capability: str) -> None:
    """能力已从目录卸载时撤销仍可完成：快照失效按「未命中能力」跳过，不抛错。"""
    audit = _RecordingAudit()
    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        service = CapabilityGrantService(
            session,
            audit=audit,  # pyright: ignore[reportArgumentType]  # 结构化替身
            uow=DbUnitOfWork(session),
        )
        granted = await service.grant(capability_name=capability, consumer_key=CONSUMER)
        reset_collaboration_records()
        register_collaboration_records(
            (
                CollaborationRecord(
                    name="demo.mdm.other",
                    domain="mdm",
                    kind="read",
                    contract_version="0.1.0",
                    path="/api/v1/demo/other",
                    product_key="demo",
                    frontend_prefix="demo",
                ),
            )
        )
        revoked = await service.revoke(granted.id)

    assert revoked.status == GRANT_STATUS_DISABLED


@pytest.mark.anyio
async def test_warm_views_skips_consumer_when_service_key_blank() -> None:
    """预热：服务标识为空时只按承载域预热（不请求空的消费方维度）。"""
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        warm_capability_grant_views,
    )

    await warm_capability_grant_views("")


@pytest.mark.anyio
@pytest.mark.kiwi_id(2511)
async def test_bootstrap_rejects_when_storage_unavailable(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """库不可读 / 未建表：拒启（数据库没准备好属部署错误，不带病启动）。"""
    from sqlalchemy.exc import OperationalError

    from bms_platform.domains.platform_registry.services import capability_grant_bootstrap as bootstrap

    class _UnavailableService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """初始化（忽略入参）。"""

        async def declared_plan(self) -> object:
            """模拟只读比对时库不可读。

            Raises:
                OperationalError: 恒抛（表缺失）。
            """
            raise OperationalError("SELECT 1", {}, Exception("no such table"))

        async def sync_declared(self) -> object:
            """模拟库不可读。

            Raises:
                OperationalError: 恒抛（表缺失）。
            """
            raise OperationalError("SELECT 1", {}, Exception("no such table"))

    monkeypatch.setattr(bootstrap, "CapabilityGrantService", _UnavailableService)

    from bms_core.core.exceptions import CatalogError

    with pytest.raises(CatalogError, match="能力分配声明同步失败：库未就绪"):
        await bootstrap.bootstrap_capability_grants(service_app)


@pytest.mark.anyio
async def test_bootstrap_reports_declaration_conflicts(service_app: FastAPI, capability: str) -> None:
    """启动装配：人工撤销与声明不一致时只告警（记录保持撤销，不覆盖人工判断）。"""
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        bootstrap_capability_grants,
    )

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        service = CapabilityGrantService(
            session,
            audit=_RecordingAudit(),  # pyright: ignore[reportArgumentType]  # 结构化替身
            uow=DbUnitOfWork(session),
        )
        revoked = await service.grant(capability_name=capability, consumer_key=CONSUMER)
        await service.revoke(revoked.id)

    await bootstrap_capability_grants(service_app)

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        row = await _grant_of(session, capability, CONSUMER)
    assert row is not None
    assert (row.status, row.source) == (GRANT_STATUS_DISABLED, GRANT_SOURCE_MANUAL)


@pytest.mark.anyio
async def test_bootstrap_wraps_failures_as_catalog_error(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动装配失败即拒启：同步异常 / 预热异常均转 `CatalogError`（不静默跳过）。"""
    from bms_core.core.exceptions import CatalogError
    from bms_platform.domains.platform_registry.services import capability_grant_bootstrap as bootstrap

    class _BrokenService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """初始化（忽略入参）。"""

        async def sync_declared(self) -> object:
            """模拟同步失败。

            Raises:
                RuntimeError: 恒抛。
            """
            raise RuntimeError("boom")

    monkeypatch.setattr(bootstrap, "CapabilityGrantService", _BrokenService)
    with pytest.raises(CatalogError):
        await bootstrap.bootstrap_capability_grants(service_app)

    class _CatalogBrokenService(_BrokenService):
        async def sync_declared(self) -> object:
            """模拟同步抛目录错误（原样上抛，不再包一层）。

            Raises:
                CatalogError: 恒抛。
            """
            raise CatalogError("catalog boom")

    monkeypatch.setattr(bootstrap, "CapabilityGrantService", _CatalogBrokenService)
    with pytest.raises(CatalogError):
        await bootstrap.bootstrap_capability_grants(service_app)

    monkeypatch.undo()
    monkeypatch.setattr(bootstrap, "warm_capability_grant_views", _raise_catalog_error)
    with pytest.raises(CatalogError):
        await bootstrap.bootstrap_capability_grants(service_app)


async def _raise_catalog_error(_settings: object) -> None:
    """模拟预热失败（抛普通异常，由启动装配统一转 `CatalogError`）。

    Args:
        _settings: 应用配置（忽略）。

    Raises:
        RuntimeError: 恒抛。
    """
    raise RuntimeError("warm boom")


def _has_route(app: FastAPI, path: str) -> bool:
    """判断应用路由表里是否存在该路径（防「常量与真实路由漂移」）。

    Args:
        app: 应用实例。
        path: 待查路径。

    Returns:
        bool: 存在为 True。
    """
    paths = app.openapi()["paths"]
    return path in paths


@pytest.mark.kiwi_id(2368)
def test_internal_path_constant_matches_route(service_app: FastAPI) -> None:
    """基座内部出口常量必须与平台真实路由一致（路径写错只会 404，运行期难发现）。"""
    from bms_core.collaboration.grant import GRANT_VIEW_PATH

    assert GRANT_VIEW_PATH == INTERNAL_API
    assert _has_route(service_app, GRANT_VIEW_PATH)
