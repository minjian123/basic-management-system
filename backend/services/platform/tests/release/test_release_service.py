"""发布清单服务与只读端点（07C `04_01`）：六条前置校验 / 清单写入 / 批次回滚 / 最近发布查询。

覆盖详细设计 §5 用例 1、2、3、4、5、6、7（主版本口径）、8、9、10、11、12、14。
结构 revision 由替身读面给出——它跨库读（每域一张 `alembic_version_{domain}`），真库路径归 `ops.release`。
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.audit.base import AuditCapturer
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError, ConflictError, NotFoundError, ParamError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.platform.release_manifest import (
    RELEASE_STATUS_FAILED,
    RELEASE_STATUS_RELEASED,
    RELEASE_STATUS_ROLLED_BACK,
    SysReleaseManifestDomain,
)
from bms_core.services.module_registry import domain_service_view, service_catalog_view
from bms_platform.domains.platform_registry.dto import ReleaseDomainEntry
from bms_platform.domains.platform_registry.repositories.release_manifest import (
    ReleaseManifestDomainRepository,
    ReleaseManifestRepository,
)
from bms_platform.domains.platform_registry.services import release as release_service
from bms_platform.domains.platform_registry.services.release import ReleaseService

UNIT = "platform"
"""默认拓扑里平台自身承载的部署单元（域 → 承载服务键自举）。"""


@pytest.fixture(autouse=True)
def _null_permission(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """权限校验改用占位实现（恒放行）：本套用例只验端点语义。

    Args:
        monkeypatch: 环境变量覆盖夹具。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _Revisions:
    """结构 revision 读面替身：按域返回预设值（缺省 `0001_init`）。

    `None` 表示该域的结构记录表尚未初始化（结构未就绪）。
    """

    def __init__(
        self, values: ConcurrentStableDict[str, str | None] | None = None, default: str | None = "0001_init"
    ) -> None:
        """初始化。

        Args:
            values: 域 → revision 覆盖表。
            default: 未覆盖域的返回值。
        """
        self._values = values or ConcurrentStableDict()
        self._default = default

    async def current(self, domain_key: str) -> str | None:
        """读取某域 revision。

        Args:
            domain_key: 业务域标识。

        Returns:
            str | None: 预设 revision。
        """
        return self._values.get(domain_key, self._default)


class _AuditSpy:
    """审计捕获器替身：只实现服务实际调用的 `capture`，记录「表 / 主键 / 字段名」。"""

    def __init__(self, sink: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            sink: 捕获结果落点。
        """
        self._sink = sink

    def capture(self, *, table: str, model_id: int, changes: ConcurrentStableList[object], actor: int | None) -> None:
        """记录一次捕获。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更清单。
            actor: 操作人。
        """
        del actor
        self._sink.add((table, model_id, [getattr(change, "field", "") for change in changes]))


def _platform_domains() -> ConcurrentStableList[str]:
    """取默认拓扑中平台单元承载的业务域（按域升序）。

    Returns:
        ConcurrentStableList[str]: 业务域标识。
    """
    return ConcurrentStableList(sorted(domain for domain, service in domain_service_view().items() if service == UNIT))


def _service_version() -> str:
    """取平台服务的登记版本（供声明值构造）。

    Returns:
        str: 服务版本。
    """
    for record in service_catalog_view():
        if record.service_key == UNIT:
            return record.service_version
    return "0.1.0"


def _contract_version() -> str:
    """取平台服务的登记契约版本（供声明值构造）。

    Returns:
        str: 契约版本。
    """
    for record in service_catalog_view():
        if record.service_key == UNIT:
            return record.contract_version
    return "0.1.0"


def _declared(contract_version: str | None = None) -> ConcurrentStableList[ReleaseDomainEntry]:
    """构造流水线声明条目（服务版本取登记值；契约版本可覆盖）。

    Args:
        contract_version: 契约版本（None 取登记值）。

    Returns:
        ConcurrentStableList[ReleaseDomainEntry]: 声明条目。
    """
    target = _contract_version() if contract_version is None else contract_version
    return ConcurrentStableList(
        ReleaseDomainEntry(
            domain_key=domain,
            service_key=UNIT,
            service_version=_service_version(),
            contract_version=target,
            schema_revision="0001_init",
        )
        for domain in _platform_domains()
    )


async def test_precheck_passes_and_record_writes_manifest(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 1、2：单单元多域发布——六条校验全过，主表一行 + 明细逐域一行，版本快照正确。"""
    scope = 9101
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope)
        assert result.passed, [item.detail for item in result.failures()]
        assert [item.key for item in result.items] == [
            "unit_complete",
            "version_consistent",
            "topology_current",
            "structure_ready",
            "contract_compatible",
            "manifest_version_monotonic",
        ]
        assert len(result.entries) == len(_platform_domains())
        snapshot = await service.record(unit_key=UNIT, tenant_scope=scope, note="首次发布")
        await session.commit()

    assert snapshot.status == RELEASE_STATUS_RELEASED
    assert snapshot.manifest_version == 1
    assert snapshot.topology_version == 1
    assert [entry.domain_key for entry in snapshot.domains] == list(_platform_domains())
    assert {entry.schema_revision for entry in snapshot.domains} == {"0001_init"}


async def test_manifest_version_must_increase(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 8：批次号回退被拒（清单版本校验）。"""
    scope = 9102
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        await service.record(unit_key=UNIT, tenant_scope=scope)
        await session.commit()

        stale = await service.precheck(unit_key=UNIT, tenant_scope=scope, manifest_version=1)
        assert not stale.passed
        assert [item.key for item in stale.failures()] == ["manifest_version_monotonic"]
        with pytest.raises(ConflictError):
            await service.record(unit_key=UNIT, tenant_scope=scope, manifest_version=1)


async def test_unit_complete_rejects_missing_domain(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 3：声明域集与拓扑不符——拒绝并列出缺失域。"""
    scope = 9103
    del client
    domains = _platform_domains()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        partial = ConcurrentStableList(
            ReleaseDomainEntry(
                domain_key=domain,
                service_key=UNIT,
                service_version=_service_version(),
                contract_version=_contract_version(),
                schema_revision="0001_init",
            )
            for domain in domains[1:]
        )
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope, declared=partial)

    failure = {item.key: item for item in result.failures()}["unit_complete"]
    assert not result.passed
    assert domains[0] in failure.detail


async def test_version_consistent_reports_per_domain_diff(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 4：三代版本不一致——逐域列出「声明 / 登记」差异。"""
    scope = 9104
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        declared = ConcurrentStableList(
            ReleaseDomainEntry(
                domain_key=entry.domain_key,
                service_key=entry.service_key,
                service_version="9.9.9",
                contract_version="9.9.9",
                schema_revision="9999_ghost",
            )
            for entry in _declared()
        )
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope, declared=declared)

    failure = {item.key: item for item in result.failures()}["version_consistent"]
    assert "服务版本 声明 9.9.9" in failure.detail
    assert "契约版本 声明 9.9.9" in failure.detail
    assert "结构 revision 声明 9999_ghost" in failure.detail


async def test_topology_version_must_match(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 5：拓扑版本过期——拒绝。"""
    scope = 9105
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope, topology_version=99)

    assert [item.key for item in result.failures()] == ["topology_current"]


async def test_structure_not_ready_rejects(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 6：某域结构记录表未初始化——拒绝并提示先执行清单。"""
    scope = 9106
    del client
    domain = _platform_domains()[0]
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions(ConcurrentStableDict({domain: None})))
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope)

    failure = {item.key: item for item in result.failures()}["structure_ready"]
    assert domain in failure.detail


async def test_contract_breaking_rejected_unless_allowed(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 7：上一发布记录的契约主版本与当前不同——拒绝；显式放行后可通过。"""
    scope = 9107
    del client
    domains = _platform_domains()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        manifests = ReleaseManifestRepository(session)
        details = ReleaseManifestDomainRepository(session)
        previous = await manifests.create_manifest(
            unit_key=UNIT,
            tenant_scope=scope,
            manifest_version=1,
            topology_version=1,
            status=RELEASE_STATUS_RELEASED,
            released_at=datetime.now(UTC),
            released_by=None,
            rolled_back_from=None,
            note="上一发布：契约 2.0.0",
        )
        await details.append_entries(
            previous.id,
            ConcurrentStableList(
                [
                    SysReleaseManifestDomain(
                        manifest_id=previous.id,
                        domain_key=domain,
                        schema_revision="0001_init",
                        service_version="0.1.0",
                        contract_version="2.0.0",
                        status=RELEASE_STATUS_RELEASED,
                        note=None,
                    )
                    for domain in domains
                ]
            ),
        )
        await session.commit()

        service = ReleaseService(session, revisions=_Revisions())
        breaking = await service.precheck(unit_key=UNIT, tenant_scope=scope)
        allowed = await service.precheck(unit_key=UNIT, tenant_scope=scope, allow_breaking=True)

    assert [item.key for item in breaking.failures()] == ["contract_compatible"]
    assert "契约主版本 2.0.0" in {item.key: item for item in breaking.failures()}["contract_compatible"].detail
    assert allowed.passed
    assert "已显式放行" in {item.key: item for item in allowed.items}["contract_compatible"].detail


async def test_failure_row_has_no_domains(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 9：执行阶段失败——只写主表行（`failed`），不写明细。"""
    scope = 9108
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        snapshot = await service.record_failure(
            unit_key=UNIT, tenant_scope=scope, topology_version=1, note="结构清单第 3 步失败"
        )
        await session.commit()

    assert snapshot.status == RELEASE_STATUS_FAILED
    assert snapshot.domains == ConcurrentStableList()
    assert snapshot.note == "结构清单第 3 步失败"


async def test_unknown_unit_is_rejected(client: AsyncClient, service_app: FastAPI) -> None:
    """拓扑里不存在的单元——参数错误（不做静默放过）。"""
    scope = 9109
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        with pytest.raises(ParamError):
            await service.precheck(unit_key="no-such-unit", tenant_scope=scope)


async def test_rollback_requires_confirmation_and_appends_row(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 10、11：回滚新增 `rolled_back` 行（原行不变）；结构回退需显式确认。"""
    scope = 9110
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        first = await service.record(unit_key=UNIT, tenant_scope=scope, note="v1")
        await session.commit()
        service = ReleaseService(session, revisions=_Revisions(default="0002_next"))
        second = await service.record(unit_key=UNIT, tenant_scope=scope, note="v2")
        await session.commit()

        plan = await service.plan_rollback(unit_key=UNIT, tenant_scope=scope)
        assert plan.source.manifest_version == second.manifest_version
        assert plan.target.manifest_version == first.manifest_version
        assert plan.requires_confirmation
        assert plan.executable

        with pytest.raises(ConflictError):
            await service.rollback(unit_key=UNIT, tenant_scope=scope)
        rolled = await service.rollback(unit_key=UNIT, tenant_scope=scope, confirmed=True)
        await session.commit()

    assert rolled.status == RELEASE_STATUS_ROLLED_BACK
    assert rolled.rolled_back_from == second.id
    assert rolled.manifest_version == second.manifest_version + 1
    assert {entry.schema_revision for entry in rolled.domains} == {"0001_init"}


async def test_rollback_without_history_is_not_found(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 12：没有可回滚的发布——明确报错（不做部分回滚）。"""
    scope = 9111
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        with pytest.raises(NotFoundError):
            await service.plan_rollback(unit_key=UNIT, tenant_scope=scope)


async def test_rollback_blocked_when_target_lacks_domain(client: AsyncClient, service_app: FastAPI) -> None:
    """回滚目标缺少某域记录——阻断（明细漏一行就有一个域回不去）。"""
    scope = 9112
    del client
    domains = _platform_domains()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        manifests = ReleaseManifestRepository(session)
        details = ReleaseManifestDomainRepository(session)
        base = await manifests.create_manifest(
            unit_key="mixed-unit",
            tenant_scope=scope,
            manifest_version=1,
            topology_version=1,
            status=RELEASE_STATUS_RELEASED,
            released_at=datetime.now(UTC),
            released_by=None,
            rolled_back_from=None,
            note="目标只含一域",
        )
        await details.append_entries(
            base.id,
            ConcurrentStableList(
                [
                    SysReleaseManifestDomain(
                        manifest_id=base.id,
                        domain_key=domains[0],
                        schema_revision="0001_init",
                        service_version="0.1.0",
                        contract_version="0.1.0",
                        status=RELEASE_STATUS_RELEASED,
                        note=None,
                    )
                ]
            ),
        )
        current = await manifests.create_manifest(
            unit_key="mixed-unit",
            tenant_scope=scope,
            manifest_version=2,
            topology_version=1,
            status=RELEASE_STATUS_RELEASED,
            released_at=datetime.now(UTC),
            released_by=None,
            rolled_back_from=None,
            note="当前含两域",
        )
        await details.append_entries(
            current.id,
            ConcurrentStableList(
                [
                    SysReleaseManifestDomain(
                        manifest_id=current.id,
                        domain_key=domain,
                        schema_revision="0002_next",
                        service_version="0.1.0",
                        contract_version="0.1.0",
                        status=RELEASE_STATUS_RELEASED,
                        note=None,
                    )
                    for domain in domains[:2]
                ]
            ),
        )
        await session.commit()

        service = ReleaseService(session, revisions=_Revisions())
        plan = await service.plan_rollback(unit_key="mixed-unit", tenant_scope=scope)
        assert not plan.executable
        with pytest.raises(ConflictError):
            await service.rollback(unit_key="mixed-unit", tenant_scope=scope, confirmed=True)


async def test_release_api_recent_and_detail(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 14：管理面按单元查最近发布与单条明细。"""
    scope = 9113
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        snapshot = await service.record(unit_key=UNIT, tenant_scope=scope, note="接口查询")
        await session.commit()

    recent = await client.get("/api/v1/releases/recent", params={"unit_key": UNIT, "tenant_scope": scope})
    body = recent.json()
    assert int(body["code"]) == 0
    assert body["data"]["items"][0]["manifest_version"] == snapshot.manifest_version
    assert len(body["data"]["items"][0]["domains"]) == len(_platform_domains())

    detail = await client.get(f"/api/v1/releases/{snapshot.id}")
    detail_body = detail.json()
    assert int(detail_body["code"]) == 0
    assert detail_body["data"]["note"] == "接口查询"

    page = await client.get("/api/v1/releases", params={"unit_key": UNIT, "tenant_scope": scope, "status": "released"})
    page_body = page.json()
    assert int(page_body["code"]) == 0
    assert page_body["data"]["total"] >= 1

    unfiltered = await client.get("/api/v1/releases")
    assert int(unfiltered.json()["code"]) == 0

    missing = await client.get("/api/v1/releases/99999999")
    assert int(missing.json()["code"]) != 0


async def test_unit_complete_reports_extra_domain(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 3（反例）：清单多出拓扑里没有的域——同样拒绝并列出。"""
    del client
    scope = 9114
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        declared = ConcurrentStableList(
            [
                *_declared(),
                ReleaseDomainEntry(domain_key="ghost", service_key=UNIT, service_version="1", contract_version="1"),
            ]
        )
        result = await service.precheck(unit_key=UNIT, tenant_scope=scope, declared=declared)

    failure = {item.key: item for item in result.failures()}["unit_complete"]
    assert "ghost" in failure.detail


async def test_precheck_requires_revisions_port(client: AsyncClient, service_app: FastAPI) -> None:
    """只读查询不需要 revision 读面；一旦要校验就必须注入（否则装配错误）。"""
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session)
        with pytest.raises(ConfigError):
            await service.precheck(unit_key=UNIT, tenant_scope=9115)


async def test_contract_breaches_reader_path(client: AsyncClient, service_app: FastAPI) -> None:
    """契约读面注入时：以外部结论为准（服务 → 破坏性变更摘要），不再看版本主版本。"""
    del client
    scope = 9116

    async def _breaches(service_key: str) -> ConcurrentStableList[str]:
        """契约读面替身：对平台服务报一条破坏性变更。

        Args:
            service_key: 服务标识。

        Returns:
            ConcurrentStableList[str]: 破坏性变更摘要。
        """
        return ConcurrentStableList(["/api/v1/x 请求体字段删除"]) if service_key == UNIT else ConcurrentStableList()

    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        await ReleaseService(session, revisions=_Revisions()).record(unit_key=UNIT, tenant_scope=scope)
        await session.commit()

        service = ReleaseService(session, revisions=_Revisions(), contract_breaches=_breaches)
        rejected = await service.precheck(unit_key=UNIT, tenant_scope=scope)
        allowed = await service.precheck(unit_key=UNIT, tenant_scope=scope, allow_breaking=True)

    assert [item.key for item in rejected.failures()] == ["contract_compatible"]
    assert "请求体字段删除" in {item.key: item for item in rejected.failures()}["contract_compatible"].detail
    assert allowed.passed

    async def _no_breaches(service_key: str) -> ConcurrentStableList[str]:
        """契约读面替身：无破坏性变更。

        Args:
            service_key: 服务标识。

        Returns:
            ConcurrentStableList[str]: 空清单。
        """
        del service_key
        return ConcurrentStableList()

    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        clean = await ReleaseService(session, revisions=_Revisions(), contract_breaches=_no_breaches).precheck(
            unit_key=UNIT, tenant_scope=scope
        )
    assert {item.key: item for item in clean.items}["contract_compatible"].passed


async def test_rollback_explicit_target_and_order_guard(client: AsyncClient, service_app: FastAPI) -> None:
    """回滚目标可按批次号指定；目标不早于当前发布即拒绝。"""
    del client
    scope = 9117
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions())
        first = await service.record(unit_key=UNIT, tenant_scope=scope)
        await session.commit()
        await ReleaseService(session, revisions=_Revisions(default="0002_next")).record(
            unit_key=UNIT, tenant_scope=scope
        )
        await session.commit()

        plan = await service.plan_rollback(unit_key=UNIT, tenant_scope=scope, target_version=first.manifest_version)
        assert plan.target.manifest_version == first.manifest_version
        with pytest.raises(ParamError):
            await service.plan_rollback(unit_key=UNIT, tenant_scope=scope, target_version=2)


async def test_rollback_without_earlier_release_is_not_found(client: AsyncClient, service_app: FastAPI) -> None:
    """只有一次发布时没有回退目标——明确报错（不做「回滚到自身」）。"""
    del client
    scope = 9118
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        await ReleaseService(session, revisions=_Revisions()).record(unit_key=UNIT, tenant_scope=scope)
        await session.commit()
        with pytest.raises(NotFoundError):
            await ReleaseService(session, revisions=_Revisions()).plan_rollback(unit_key=UNIT, tenant_scope=scope)


async def test_audit_capture_records_release(client: AsyncClient, service_app: FastAPI) -> None:
    """发布留一条审计（单元 / 批次号 / 域数），不逐域记。"""
    del client
    scope = 9119
    captured: ConcurrentStableList[object] = ConcurrentStableList()
    spy = _AuditSpy(captured)
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = ReleaseService(session, revisions=_Revisions(), audit=cast(AuditCapturer, spy))
        await service.record(unit_key=UNIT, tenant_scope=scope, note="留痕")
        await session.commit()

    assert len(captured) == 1
    table, model_id, fields = cast("tuple[str, int, list[str]]", captured[0])
    assert table == "sys_release_manifest"
    assert model_id > 0
    assert fields == ["unit_key", "manifest_version", "domains"]


def test_major_version_helper() -> None:
    """主版本口径：取首段；无版本信息返回空串。"""
    assert release_service._major("0.1.0") == "0"  # pyright: ignore[reportPrivateUsage]
    assert release_service._major("") == ""  # pyright: ignore[reportPrivateUsage]


async def test_contract_check_skips_domain_missing_in_previous(client: AsyncClient, service_app: FastAPI) -> None:
    """上一发布缺某域记录：该域跳过对比，其余域按同版本判兼容（不误报）。"""
    del client
    scope = 9120
    domains = _platform_domains()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        manifests = ReleaseManifestRepository(session)
        details = ReleaseManifestDomainRepository(session)
        previous = await manifests.create_manifest(
            unit_key=UNIT,
            tenant_scope=scope,
            manifest_version=1,
            topology_version=1,
            status=RELEASE_STATUS_RELEASED,
            released_at=datetime.now(UTC),
            released_by=None,
            rolled_back_from=None,
            note="上一发布只记一个域",
        )
        await details.append_entries(
            previous.id,
            ConcurrentStableList(
                [
                    SysReleaseManifestDomain(
                        manifest_id=previous.id,
                        domain_key=domains[0],
                        schema_revision="0001_init",
                        service_version="0.1.0",
                        contract_version=_contract_version(),
                        status=RELEASE_STATUS_RELEASED,
                        note=None,
                    )
                ]
            ),
        )
        await session.commit()

        result = await ReleaseService(session, revisions=_Revisions()).precheck(unit_key=UNIT, tenant_scope=scope)

    contract = {item.key: item for item in result.items}["contract_compatible"]
    assert contract.passed
    assert "无破坏性变更" in contract.detail


async def test_rollback_unknown_target_version_is_not_found(client: AsyncClient, service_app: FastAPI) -> None:
    """指定了不存在的目标批次——明确报错（不静默回退到上一条）。"""
    del client
    scope = 9121
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        await ReleaseService(session, revisions=_Revisions()).record(unit_key=UNIT, tenant_scope=scope)
        await session.commit()
        with pytest.raises(NotFoundError):
            await ReleaseService(session, revisions=_Revisions()).plan_rollback(
                unit_key=UNIT, tenant_scope=scope, target_version=99
            )


async def test_precheck_on_default_scope(client: AsyncClient, service_app: FastAPI) -> None:
    """默认作用范围（`0`）直接用默认拓扑，不走租户回退分支。"""
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        result = await ReleaseService(session, revisions=_Revisions()).precheck(unit_key=UNIT, tenant_scope=0)
    assert len(result.entries) == len(_platform_domains())


async def test_append_entries_empty_is_noop(client: AsyncClient, service_app: FastAPI) -> None:
    """明细批量追加：空清单不落库、不 flush（返回 0）。"""
    del client
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        details = ReleaseManifestDomainRepository(session)
        assert await details.append_entries(0, ConcurrentStableList()) == 0
