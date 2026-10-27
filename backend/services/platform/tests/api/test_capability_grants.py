"""能力分配授权端点与服务（07B `02_04`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 1~6、14~20 的端到端部分：

- 管理面：分页筛选、人工授予（幂等 UPSERT / 能力与消费方须已登记 / 临时授权参数成对）、
  软撤销（不删行、重复撤销幂等、不存在 10002）；
- 声明同步：新建 / 声明移除置撤销 / 声明回归恢复，变更经审计捕获、有效授权数指标刷新；
- 内部授权视图：`provider` / `consumer` 二选一、维度越界即拒（403）、登录态按权限码放行。
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import AuthError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
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
from bms_core.schemas.pagination import BasePageQuery
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)
from bms_platform.domains.platform_registry.services.capability_grant import CapabilityGrantService
from tests_support.metrics import RecordingMetrics

API = "/api/v1/capability-grants"
INTERNAL_API = "/api/v1/platform/internal/capability-grants"

CAPABILITY = "demo.org.user-roles"
CONSUMER = "platform"


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


def _record(*, consumers: ConcurrentStableFrozenList[str] | None = None) -> CollaborationRecord:
    """构造能力记录（读出口，缺省默认消费方为 platform）。

    Args:
        consumers: 默认消费方（空表示声明里没有消费方）。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=CAPABILITY,
        domain="org",
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
def _null_permission(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """权限校验改用占位实现（恒放行）。

    管理面 / 内部视图的**权限码挂载**属路由契约，权限码级判定由权限引擎专项用例覆盖；
    本套用例只验端点语义，故显式设 `[permission].provider = null`（服务装配尊重显式配置）。

    Args:
        monkeypatch: 环境变量覆盖夹具。

    Yields:
        None: 用例运行期。
    """
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_grant_state() -> Iterator[None]:
    """每例复位能力记录 / 域映射 / 授权视图，并登记夹具能力。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_domain_services()
    register_collaboration_records((_record(),))
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm", "platform_registry": "platform"}))
    yield
    reset_collaboration_records()
    reset_domain_services()


@pytest.fixture(autouse=True)
async def _clean_grants(_null_permission: None, service_app: FastAPI) -> None:
    """清空授权表（会话级平台库跨用例共享，逐例起点一致）。

    Args:
        service_app: 应用实例（启动钩子已执行，声明同步行随后清空）。
        _null_permission: 保证权限实现先于应用装配生效（依赖顺序）。
    """
    from bms_core.collaboration import reset_capability_grants

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        await session.execute(delete(SysCapabilityGrant))
        await session.commit()
    reset_capability_grants()


@pytest.mark.anyio
async def test_grant_is_idempotent_and_listed(client: AsyncClient) -> None:
    """人工授予：首次新建、重复授予复用同一行；清单按能力筛选命中。"""
    first = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER})
    assert first.status_code == 200
    granted = first.json()["data"]
    assert granted["source"] == GRANT_SOURCE_MANUAL
    assert granted["status"] == GRANT_STATUS_ENABLED
    assert granted["revoked_at"] is None

    second = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER})
    assert second.json()["data"]["id"] == granted["id"]

    listed = await client.get(API, params={"capability_name": CAPABILITY})
    rows = listed.json()["data"]["list"]
    assert [row["id"] for row in rows] == [granted["id"]]


@pytest.mark.anyio
async def test_grant_rejects_unregistered_capability_and_consumer(client: AsyncClient) -> None:
    """入库前校验：能力未登记 / 消费方未登记均按参数非法拒绝（10001）。"""
    unknown_capability = await client.post(API, json={"capability_name": "demo.org.ghost", "consumer_key": CONSUMER})
    assert unknown_capability.json()["code"] == 10001

    unknown_consumer = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": "ghost"})
    assert unknown_consumer.json()["code"] == 10001


@pytest.mark.anyio
async def test_temporary_grant_requires_expire_and_note(client: AsyncClient) -> None:
    """临时授权：有效期与理由成对；过期时间必须晚于当前时间。"""
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    missing_note = await client.post(
        API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER, "expire_at": future}
    )
    assert missing_note.json()["code"] == 10001

    past_expire = await client.post(
        API,
        json={"capability_name": CAPABILITY, "consumer_key": CONSUMER, "expire_at": past, "note": "排障"},
    )
    assert past_expire.json()["code"] == 10001

    ok = await client.post(
        API,
        json={"capability_name": CAPABILITY, "consumer_key": CONSUMER, "expire_at": future, "note": "排障"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["note"] == "排障"


@pytest.mark.anyio
async def test_revoke_is_soft_and_idempotent(client: AsyncClient) -> None:
    """撤销：软撤销保留行（`disabled` + `revoked_at`）、重复撤销幂等、不存在 10002。"""
    created = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER})
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


@pytest.mark.anyio
async def test_declared_sync_create_disable_restore_with_audit(service_app: FastAPI) -> None:
    """声明同步：新建 → 声明移除置撤销 → 声明回归恢复；状态变更逐次经审计捕获。"""
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
        created = await service.sync_declared()
        assert (created.created, created.restored, created.revoked) == (1, 0, 0)
        rows, total = await service.page(BasePageQuery())
        assert (total, rows[0].source, rows[0].status) == (1, GRANT_SOURCE_DECLARED, GRANT_STATUS_ENABLED)

        reset_collaboration_records()
        register_collaboration_records((_record(consumers=ConcurrentStableFrozenList()),))
        removed = await service.sync_declared()
        assert (removed.created, removed.restored, removed.revoked) == (0, 0, 1)
        rows, _total = await service.page(BasePageQuery())
        assert (rows[0].status, rows[0].note) == (GRANT_STATUS_DISABLED, GRANT_NOTE_REMOVED)

        reset_collaboration_records()
        register_collaboration_records((_record(),))
        restored = await service.sync_declared()
        assert (restored.created, restored.restored, restored.revoked) == (0, 1, 0)
        rows, _total = await service.page(BasePageQuery())
        assert (rows[0].status, rows[0].note) == (GRANT_STATUS_ENABLED, GRANT_NOTE_DECLARED)

    assert [change for _table, _id, change, _actor in audit.calls] == [
        GRANT_STATUS_ENABLED,
        GRANT_STATUS_DISABLED,
        GRANT_STATUS_ENABLED,
    ]


@pytest.mark.anyio
async def test_grant_refreshes_active_gauge(service_app: FastAPI) -> None:
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
        await service.grant(capability_name=CAPABILITY, consumer_key=CONSUMER, note="用例")
        await service.sync_declared()

    gauges = [value for name, value in metrics.gauges if name == METRIC_CAPABILITY_GRANT_ACTIVE]
    assert gauges and gauges[-1] == 1.0


@pytest.mark.anyio
async def test_internal_view_provider_and_consumer_dimensions(client: AsyncClient, service_app: FastAPI) -> None:
    """内部视图：登录态按 provider 维度取；服务身份只能读自身消费方或自身承载域。"""
    created = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER})
    assert created.status_code == 200

    by_provider = await client.get(INTERNAL_API, params={"provider": "org"})
    assert by_provider.status_code == 200
    assert [item["capability_name"] for item in by_provider.json()["data"]["grants"]] == [CAPABILITY]

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    own = await client.get(INTERNAL_API, params={"consumer": CONSUMER}, headers={"Authorization": "Bearer platform"})
    assert own.status_code == 200
    assert [item["consumer_key"] for item in own.json()["data"]["grants"]] == [CONSUMER]

    foreign_consumer = await client.get(
        INTERNAL_API, params={"consumer": "mdm"}, headers={"Authorization": "Bearer platform"}
    )
    assert foreign_consumer.status_code == 403

    foreign_domain = await client.get(
        INTERNAL_API, params={"provider": "org"}, headers={"Authorization": "Bearer platform"}
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

    both = await client.get(INTERNAL_API, params={"provider": "org", "consumer": CONSUMER})
    assert both.json()["code"] == 10001


@pytest.mark.anyio
async def test_list_filters_by_consumer_status_and_source(client: AsyncClient) -> None:
    """清单筛选：消费方 / 状态 / 来源三个筛选条件均可组合（无匹配返回空清单）。"""
    created = await client.post(API, json={"capability_name": CAPABILITY, "consumer_key": CONSUMER})
    grant_id = created.json()["data"]["id"]
    await client.delete(f"{API}/{grant_id}")

    by_status = await client.get(API, params={"status": GRANT_STATUS_DISABLED, "source": GRANT_SOURCE_MANUAL})
    assert [row["id"] for row in by_status.json()["data"]["list"]] == [grant_id]

    by_consumer = await client.get(API, params={"consumer_key": CONSUMER})
    assert by_consumer.json()["data"]["total"] == 1

    no_match = await client.get(API, params={"consumer_key": "mdm"})
    assert no_match.json()["data"]["list"] == []


@pytest.mark.anyio
async def test_service_rejects_invalid_view_dimension_and_missing_uow(service_app: FastAPI) -> None:
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
            await read_only.view(provider="org", consumer=CONSUMER)
        with pytest.raises(ConfigError):
            await read_only.grant(capability_name=CAPABILITY, consumer_key=CONSUMER)

        writable = CapabilityGrantService(session, uow=DbUnitOfWork(session))
        row = await writable.grant(capability_name=CAPABILITY, consumer_key=CONSUMER)
        assert row.status == GRANT_STATUS_ENABLED


@pytest.mark.anyio
async def test_sync_keeps_manual_revocation_and_warns(service_app: FastAPI) -> None:
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
        granted = await service.grant(capability_name=CAPABILITY, consumer_key=CONSUMER)
        await service.revoke(granted.id)

        report = await service.sync_declared()

    assert (report.created, report.restored, report.revoked) == (0, 0, 0)
    assert any("声明与人工不一致" in message for message in report.warnings)
    rows_after, _total = await _read_grants(service_app)
    assert rows_after[0].status == GRANT_STATUS_DISABLED


@pytest.mark.anyio
async def test_bootstrap_registers_source_and_warms_views(service_app: FastAPI) -> None:
    """启动装配：重复执行幂等（登记来源 + 预热本服务承载域与自身消费方视图）。"""
    from bms_core.collaboration import capability_grant_pairs
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        bootstrap_capability_grants,
    )

    await bootstrap_capability_grants(service_app)

    assert list(capability_grant_pairs(provider="platform_registry")) == []
    rows = capability_grant_pairs(consumer=CONSUMER)
    assert [(row.capability_name, row.source) for row in rows] == [(CAPABILITY, GRANT_SOURCE_DECLARED)]


@pytest.mark.anyio
async def test_revoke_tolerates_capability_removed_from_catalog(service_app: FastAPI) -> None:
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
        granted = await service.grant(capability_name=CAPABILITY, consumer_key=CONSUMER)
        reset_collaboration_records()
        register_collaboration_records(
            (
                CollaborationRecord(
                    name="demo.org.other",
                    domain="org",
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
async def test_bootstrap_degrades_when_storage_unavailable(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """库不可读 / 未建表：降级放行（WARNING + `grant_sync_degraded`），不阻断启动。"""
    from sqlalchemy.exc import OperationalError

    from bms_platform.domains.platform_registry.services import capability_grant_bootstrap as bootstrap

    class _UnavailableService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """初始化（忽略入参）。"""

        async def sync_declared(self) -> object:
            """模拟库不可读。

            Raises:
                OperationalError: 恒抛（表缺失）。
            """
            raise OperationalError("SELECT 1", {}, Exception("no such table"))

    monkeypatch.setattr(bootstrap, "CapabilityGrantService", _UnavailableService)

    await bootstrap.bootstrap_capability_grants(service_app)

    assert service_app.state.grant_sync_degraded is True


@pytest.mark.anyio
async def test_bootstrap_reports_declaration_conflicts(service_app: FastAPI) -> None:
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
        revoked = await service.grant(capability_name=CAPABILITY, consumer_key=CONSUMER)
        await service.revoke(revoked.id)

    await bootstrap_capability_grants(service_app)

    rows, _total = await _read_grants(service_app)
    assert (rows[0].status, rows[0].source) == (GRANT_STATUS_DISABLED, GRANT_SOURCE_MANUAL)


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


async def _read_grants(service_app: FastAPI) -> tuple[ConcurrentStableList[SysCapabilityGrant], int]:
    """读取授权记录（用例断言用）。

    Args:
        service_app: 应用实例。

    Returns:
        tuple[ConcurrentStableList[SysCapabilityGrant], int]: (当前页记录, 总数)。
    """
    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        return await CapabilityGrantService(session).page(BasePageQuery())


async def _raise_catalog_error(_settings: object) -> None:
    """模拟预热失败（抛普通异常，由启动装配统一转 `CatalogError`）。

    Args:
        _settings: 应用配置（忽略）。

    Raises:
        RuntimeError: 恒抛。
    """
    raise RuntimeError("warm boom")
