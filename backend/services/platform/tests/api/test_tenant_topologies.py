"""租户拓扑管理面与服务：整批替换 / 校验七条 / 导出回退 / 写入即生效（07C `02_01`；Kiwi 2366）。

覆盖设计 §5 用例 1、2（服务侧）、5、6、7、8、9、10、16，以及 §3.4 校验 1~7 的反例。
"""

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from bms_core.collaboration import resolve_for
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import CatalogError, NotFoundError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.platform.tenant_topology import SysTenantTopology
from bms_core.services.module_registry import domain_service_view
from bms_platform.domains.platform_registry.repositories.tenant_topology import (
    TenantTopologyRepository,
)
from bms_platform.domains.platform_registry.services.tenant_topology import (
    TenantTopologyService,
    TopologyRow,
)

pytestmark = pytest.mark.kiwi_id(2366)

API = "/api/v1/tenant-topologies"

WRITE_TENANT = 9001
REPLACE_TENANT = 9002
ROLLBACK_TENANT = 9003
DISABLED_TENANT = 9004
FALLBACK_TENANT = 9500


@pytest.fixture(autouse=True)
def _null_permission(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """权限校验改用占位实现（恒放行）：本套用例只验端点语义，权限码级判定归权限引擎专项。

    Args:
        monkeypatch: 环境变量覆盖夹具。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _rows(*pairs: tuple[str, str], status: str = "enabled") -> object:
    """构造写入行（`domain → unit`；JSON 载荷用原生 list，集合类不可序列化）。

    Args:
        pairs: `(域, 单元)` 对。
        status: 状态。

    Returns:
        object: 可直接作为 `json` 载荷的请求行。
    """
    return [{"domain_key": domain, "unit_key": unit, "status": status} for domain, unit in pairs]


def _row(domain: str, unit: str) -> TopologyRow:
    """构造服务层待写入行。

    Args:
        domain: 业务域标识。
        unit: 部署单元标识。

    Returns:
        TopologyRow: 待写入行。
    """
    return TopologyRow(domain_key=domain, unit_key=unit)


def _reason(exc: CatalogError) -> str:
    """取异常携带的失败原因（`data.reason`；`data` 为 `object`，测试内显式收窄）。

    Args:
        exc: 抛出的目录异常。

    Returns:
        str: 失败原因标识。
    """
    data = cast("ConcurrentStableDict[str, str]", exc.data)
    return data["reason"]


def _first_domain() -> str:
    """取一个已登记业务域（断言不写死域清单：域登记随清单演进）。

    Returns:
        str: 业务域标识。
    """
    return next(iter(domain_service_view()))


async def _soft_deleted(app: FastAPI, tenant_id: int) -> int:
    """统计某租户已软删除的拓扑行数（整批替换的历史留痕）。

    Args:
        app: 应用实例（取引擎与会话工厂）。
        tenant_id: 租户主键。

    Returns:
        int: 软删除行数。
    """
    async with session_scope(
        app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=app.state.session_factory
    ) as session:
        statement = (
            select(func.count())
            .select_from(SysTenantTopology)
            .where(
                SysTenantTopology.tenant_id == tenant_id,
                SysTenantTopology.deleted_at.is_not(None),
            )
        )
        return int((await session.execute(statement)).scalar_one())


async def test_default_topology_is_bootstrapped(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 1：启动自举默认拓扑——行数 = 已登记域数、版本 1、单元 = 该域承载服务键。"""
    del service_app
    resp = await client.get(API, params={"tenant_id": 0, "size": 200})
    body = resp.json()
    assert int(body["code"]) == 0
    rows = body["data"]["list"]
    assert {row["domain_key"] for row in rows} == set(domain_service_view())
    assert {row["topology_version"] for row in rows} == {1}
    assert {row["unit_key"] for row in rows} == set(domain_service_view().values())


async def test_list_filters_by_tenant_domain_and_unit(client: AsyncClient) -> None:
    """用例 16：分页端点按租户 / 域 / 单元筛选，且只返回未删除行。"""
    domain = _first_domain()
    by_tenant = await client.get(API, params={"tenant_id": 0})
    by_domain = await client.get(API, params={"tenant_id": 0, "domain_key": domain})
    missing = await client.get(API, params={"tenant_id": 0, "unit_key": "no-such-unit"})
    assert by_tenant.json()["data"]["total"] >= 1
    assert [row["domain_key"] for row in by_domain.json()["data"]["list"]] == [domain]
    assert missing.json()["data"]["total"] == 0


async def test_export_returns_current_version(client: AsyncClient) -> None:
    """用例 16：按租户导出当前版本（部署编排输入）。"""
    resp = await client.get(f"{API}/0")
    body = resp.json()
    assert int(body["code"]) == 0
    assert int(body["data"]["tenant_id"]) == 0
    assert int(body["data"]["version"]) == 1
    assert len(body["data"]["rows"]) == len(domain_service_view())


async def test_export_falls_back_to_default(client: AsyncClient) -> None:
    """用例 3（服务侧）：租户无记录时导出回退默认拓扑。"""
    resp = await client.get(f"{API}/{FALLBACK_TENANT}")
    body = resp.json()
    assert int(body["code"]) == 0
    assert int(body["data"]["version"]) == 1
    assert len(body["data"]["rows"]) == len(domain_service_view())


async def test_write_template_expands_registered_domains(client: AsyncClient) -> None:
    """用例 15（服务侧）：模板整批写入——行数 = 已登记域数、版本 1、单元取公共单元。"""
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"template": "single"})
    body = resp.json()
    assert int(body["code"]) == 0
    assert int(body["data"]["version"]) == 1
    assert {row["domain_key"] for row in body["data"]["rows"]} == set(domain_service_view())
    assert {row["unit_key"] for row in body["data"]["rows"]} == {"core"}


async def test_write_rejects_both_rows_and_template(client: AsyncClient) -> None:
    """校验：`rows` 与 `template` 只能二选一（10001）。"""
    resp = await client.put(
        f"{API}/{WRITE_TENANT}", json={"template": "single", "rows": [{"domain_key": "auth", "unit_key": "core"}]}
    )
    assert int(resp.json()["code"]) == 10001


async def test_write_rejects_missing_input(client: AsyncClient) -> None:
    """校验：既无 rows 也无 template 即拒（10001）。"""
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={})
    assert int(resp.json()["code"]) == 10001


async def test_write_rejects_unknown_template(client: AsyncClient) -> None:
    """校验 6：未知模板名即拒（10001）。"""
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"template": "micro"})
    assert int(resp.json()["code"]) == 10001


async def test_write_rejects_unregistered_domain(client: AsyncClient) -> None:
    """校验 1：引用未登记业务域即拒并列出域（10001）。"""
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"rows": _rows(("ghost", "core"))})
    body = resp.json()
    assert int(body["code"]) == 10001
    assert "ghost" in body["message"]


async def test_write_rejects_illegal_unit_name(client: AsyncClient) -> None:
    """校验 2：单元命名非法（大写 / 下划线 / 空）即拒（10001）。"""
    domain = _first_domain()
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"rows": _rows((domain, "Core_1"))})
    body = resp.json()
    assert int(body["code"]) == 10001
    assert "Core_1" in body["message"]


async def test_write_rejects_duplicate_domain(client: AsyncClient) -> None:
    """校验 3：同租户同域重复映射即拒（10003）。"""
    domain = _first_domain()
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"rows": _rows((domain, "core"), (domain, "dom-a"))})
    body = resp.json()
    assert int(body["code"]) == 10003
    assert domain in body["message"]


async def test_write_rejects_empty_topology(client: AsyncClient) -> None:
    """校验 4：空拓扑（无任何单元承载域）即拒（10001）。"""
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"rows": []})
    assert int(resp.json()["code"]) == 10001


async def test_write_rejects_illegal_status(client: AsyncClient) -> None:
    """校验：状态取值非法即拒（10001）。"""
    domain = _first_domain()
    resp = await client.put(f"{API}/{WRITE_TENANT}", json={"rows": _rows((domain, "core"), status="archived")})
    body = resp.json()
    assert int(body["code"]) == 10001
    assert "archived" in body["message"]


async def test_default_topology_must_cover_all_domains(client: AsyncClient) -> None:
    """校验 5：默认拓扑必须覆盖全部已登记域，缺域即拒并列出缺失域（10001）。"""
    domain = _first_domain()
    resp = await client.put(f"{API}/0", json={"rows": _rows((domain, "core"))})
    body = resp.json()
    assert int(body["code"]) == 10001
    assert "缺少" in body["message"]


async def test_replace_soft_deletes_previous_version(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 10：整批替换后只看到新版本，旧行已软删除（历史留痕）。"""
    domain = _first_domain()
    first = await client.put(f"{API}/{REPLACE_TENANT}", json={"rows": _rows((domain, "core"))})
    assert int(first.json()["data"]["version"]) == 1
    second = await client.put(f"{API}/{REPLACE_TENANT}", json={"rows": _rows((domain, "dom-x"))})
    body = second.json()
    assert int(body["code"]) == 0
    assert int(body["data"]["version"]) == 2
    assert [row["unit_key"] for row in body["data"]["rows"]] == ["dom-x"]
    assert await _soft_deleted(service_app, REPLACE_TENANT) == 1
    listed = await client.get(API, params={"tenant_id": REPLACE_TENANT})
    assert [int(row["topology_version"]) for row in listed.json()["data"]["list"]] == [2]


async def test_version_rollback_rejected(client: AsyncClient) -> None:
    """校验 7：版本回退即拒（10003）。"""
    domain = _first_domain()
    await client.put(f"{API}/{ROLLBACK_TENANT}", json={"rows": _rows((domain, "core")), "version": 5})
    resp = await client.put(f"{API}/{ROLLBACK_TENANT}", json={"rows": _rows((domain, "core")), "version": 5})
    body = resp.json()
    assert int(body["code"]) == 10003
    assert "须递增" in body["message"]


async def test_disabled_domain_is_not_resolvable(client: AsyncClient) -> None:
    """用例 11（服务侧）：写入 `disabled` 后解析报 `not_enabled`（写入即生效）。"""
    domain = _first_domain()
    await client.put(f"{API}/{DISABLED_TENANT}", json={"rows": _rows((domain, "core"), status="disabled")})
    with pytest.raises(CatalogError) as captured:
        resolve_for(DISABLED_TENANT, domain)
    assert _reason(captured.value) == "not_enabled"


async def test_export_missing_tenant_without_default_reports_not_found(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """导出兜底：租户与默认拓扑都无记录时报 10002（不静默返回空）。"""
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        monkeypatch.setattr(TenantTopologyRepository, "list_current", _empty_rows)
        monkeypatch.setattr(TenantTopologyRepository, "current_version", _zero_version)
        with pytest.raises(NotFoundError):
            await service.export(FALLBACK_TENANT + 1)


async def _empty_rows(self: object, tenant_id: int) -> ConcurrentStableList[SysTenantTopology]:
    """无记录替身（覆盖导出兜底的「默认拓扑也未自举」分支）。

    Args:
        self: 仓储实例占位（类级替身会被绑定为方法）。
        tenant_id: 租户主键（未使用）。

    Returns:
        ConcurrentStableList[SysTenantTopology]: 空清单。
    """
    del tenant_id
    return ConcurrentStableList()


async def _zero_version(self: object, tenant_id: int) -> int:
    """无版本替身。

    Args:
        self: 仓储实例占位（类级替身会被绑定为方法）。
        tenant_id: 租户主键（未使用）。

    Returns:
        int: 恒 0。
    """
    del tenant_id
    return 0


async def test_list_without_tenant_filter_returns_all(client: AsyncClient) -> None:
    """分页端点不传租户筛选时取全量（运维排查「跨租户看拓扑」）。"""
    resp = await client.get(API, params={"size": 200})
    body = resp.json()
    assert int(body["code"]) == 0
    assert body["data"]["total"] >= len(domain_service_view())


async def test_write_applies_batch_note(client: AsyncClient) -> None:
    """写入时给批次说明：行内无说明则继承批次说明（留痕来源可读）。"""
    domain = _first_domain()
    resp = await client.put(
        f"{API}/{WRITE_TENANT}",
        json={"rows": _rows((domain, "core")), "note": "按业务重心拆分"},
    )
    body = resp.json()
    assert int(body["code"]) == 0
    assert body["data"]["rows"][0]["note"] == "按业务重心拆分"


async def test_service_write_without_audit(client: AsyncClient, service_app: FastAPI) -> None:
    """服务层无审计捕获器时写入照常（只读场景复用同一服务，不留痕）。"""
    del client
    domain = _first_domain()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        version, rows = await service.replace(FALLBACK_TENANT, rows=ConcurrentStableList([_row(domain, "core")]))
        await session.commit()
    assert version == 1
    assert [row.unit_key for row in rows] == ["core"]


async def test_export_default_without_rows_reports_not_found(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """默认拓扑本身无记录：导出报 10002（不返回空拓扑冒充默认）。"""
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        monkeypatch.setattr(TenantTopologyRepository, "list_current", _empty_rows)
        with pytest.raises(NotFoundError):
            await service.export(0)
