"""能力寻址：单点入口 / 返回模型 / 过渡拓扑（07B `02_02`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 1~5、17、19：取用成功、缺失即抛、`codes` 无路径、默认拓扑等价（域布局派生）、
拓扑缺失拒启级报错、`disabled` 取用即抛、装载期补齐的前端域段直接取最终值。
"""

import re
from collections.abc import Iterator

import pytest

from bms_core.collaboration import (
    CapabilityMode,
    CapabilityTarget,
    DomainLayoutTopologyResolver,
    register_topology_resolver,
    reset_topology_resolver,
    resolve_capability,
)
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.exceptions import CatalogError, ParamError
from bms_core.services.module_registry import (
    CollaborationRecord,
    CollaborationStatus,
    domain_service_view,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
    service_key_for_domain,
)


def _record(
    *,
    name: str = "demo.org.user-roles",
    domain: str = "org",
    kind: str = "read",
    path: str | None = "/api/v1/demo/user-roles",
    status: str = CollaborationStatus.ENABLED,
    branch_op: str | None = None,
    branch_id: str | None = None,
    frontend_prefix: str | None = "demo",
    replacement: str | None = None,
    permission_codes: ConcurrentStableFrozenList[str] | None = None,
) -> CollaborationRecord:
    """构造能力记录（缺省 `read` 类；按需覆盖字段）。

    Args:
        name: 能力名。
        domain: 提供方业务域。
        kind: 访问面类别。
        path: 访问面路径模板（`codes` 类为 None）。
        status: 能力状态。
        branch_op: 分支动作名（`txn-branch` 类）。
        branch_id: 分支标识（`txn-branch` 类）。
        frontend_prefix: 前端命名空间域段。
        replacement: 替代能力名（`deprecated` 类）。
        permission_codes: 业务码 / 权限码集合（`codes` 类）。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=name,
        domain=domain,
        kind=kind,
        contract_version="0.1.0",
        path=path,
        product_key="demo",
        branch_op=branch_op,
        branch_id=branch_id,
        frontend_prefix=frontend_prefix,
        status=status,
        replacement=replacement,
        permission_codes=permission_codes or ConcurrentStableFrozenList(),
    )


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例前后复位能力记录、域→服务键映射与第二段解析实现（均为进程级状态）。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_domain_services()
    reset_topology_resolver()
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm", "user": "platform"}))
    yield
    reset_collaboration_records()
    reset_domain_services()
    reset_topology_resolver()


def test_resolve_capability_returns_endpoint_with_target() -> None:
    """能力存在 → 取用：字段与清单一致，第二段按域布局派生承载服务键与基址（用例 1 / 4）。"""
    register_collaboration_records((_record(branch_op="demo.user-roles.read", branch_id="d"),))

    endpoint = resolve_capability("demo.org.user-roles")

    assert endpoint.name == "demo.org.user-roles"
    assert endpoint.domain == "org"
    assert endpoint.kind == "read"
    assert endpoint.contract_version == "0.1.0"
    assert endpoint.path == "/api/v1/demo/user-roles"
    assert endpoint.product_key == "demo"
    assert endpoint.frontend_prefix == "demo"
    assert endpoint.branch_op == "demo.user-roles.read"
    assert endpoint.branch_id == "d"
    assert endpoint.target.mode == CapabilityMode.REMOTE
    assert endpoint.target.unit_key == "org"
    assert endpoint.target.service_key == "mdm"
    assert endpoint.target.base_url == "http://mdm:8000"
    assert endpoint.target.db_keys == []
    assert endpoint.access_url() == "http://mdm:8000/api/v1/demo/user-roles"
    assert endpoint.is_write_path is False


def test_resolve_capability_missing_raises_with_name() -> None:
    """能力未声明 → 抛 `ParamError`（10001），信息含能力名；不返回空值（用例 2）。"""
    with pytest.raises(ParamError, match=re.escape("能力未声明：demo.org.missing")) as exc:
        resolve_capability("demo.org.missing")

    assert exc.value.code == 10001
    assert "请检查产品清单" in str(exc.value)


def test_resolve_capability_blank_name_raises() -> None:
    """能力名为空 → 立即报错（防「以为按能力寻址、实际传了空串」）。"""
    with pytest.raises(ParamError, match="能力名不得为空"):
        resolve_capability("")


def test_resolve_capability_disabled_raises() -> None:
    """已声明但 `status=disabled` → 抛 `ParamError` 并注明状态（用例 17）。"""
    register_collaboration_records((_record(status=CollaborationStatus.DISABLED),))

    with pytest.raises(ParamError, match=re.escape("能力已禁用（status=disabled）：demo.org.user-roles")):
        resolve_capability("demo.org.user-roles")


def test_resolve_capability_deprecated_returns() -> None:
    """`deprecated` 仍在弃用期内可取用（迁移窗口；替代能力名由快照段下发给消费方）。"""
    register_collaboration_records(
        (_record(status=CollaborationStatus.DEPRECATED, replacement="demo.org.user-roles.v2"),)
    )

    endpoint = resolve_capability("demo.org.user-roles")

    assert endpoint.name == "demo.org.user-roles"
    assert endpoint.path == "/api/v1/demo/user-roles"


def test_resolve_codes_capability_has_no_path() -> None:
    """`codes` 类能力：`path is None`，据此发起调用即被拦住（用例 3）。"""
    register_collaboration_records(
        (
            _record(
                name="demo.org.admin-codes",
                kind="codes",
                path=None,
                permission_codes=ConcurrentStableFrozenList(("demo:query",)),
            ),
        )
    )

    endpoint = resolve_capability("demo.org.admin-codes")

    assert endpoint.path is None
    assert endpoint.permission_codes == ["demo:query"]
    with pytest.raises(ParamError, match="能力无访问面（kind=codes）"):
        endpoint.access_url()


def test_resolve_write_capability_marks_write_path() -> None:
    """`write` / `txn-branch` 属写 / 强一致路径（fail-closed 档，不得声明降级）。"""
    register_collaboration_records(
        (
            _record(
                name="demo.org.user-posts.assign",
                kind="txn-branch",
                path="/api/v1/demo/internal/user-posts/{user_id}",
                branch_op="demo.user-posts.assign",
                branch_id="d",
            ),
        )
    )

    endpoint = resolve_capability("demo.org.user-posts.assign")

    assert endpoint.is_write_path is True
    assert endpoint.branch_op == "demo.user-posts.assign"


def test_default_topology_rejects_unregistered_domain() -> None:
    """第二段解析不到承载服务 → `CatalogError`，信息含业务域名（用例 5）。"""
    register_collaboration_records((_record(domain="nowhere"),))

    with pytest.raises(CatalogError, match="业务域未在部署拓扑登记：nowhere"):
        resolve_capability("demo.org.user-roles")


def test_topology_resolver_can_be_replaced() -> None:
    """第二段解析实现可替换（07C 落地点）：替换后取用结果随之改变，复位回默认实现。"""
    register_collaboration_records((_record(),))

    class _LocalResolver:
        """替身解析器：恒返回同进程模式（验证协议可替换）。"""

        def resolve(self, domain: str) -> CapabilityTarget:
            """返回固定的本地目标。

            Args:
                domain: 业务域。

            Returns:
                CapabilityTarget: `mode=local` 的目标。
            """
            return CapabilityTarget(
                mode=CapabilityMode.LOCAL,
                unit_key=f"unit-{domain}",
                service_key="demo",
                base_url="http://demo:8000",
                db_keys=ConcurrentStableFrozenList(("platform",)),
            )

    register_topology_resolver(_LocalResolver())
    local = resolve_capability("demo.org.user-roles")
    assert local.target.mode == CapabilityMode.LOCAL
    assert local.target.unit_key == "unit-org"
    assert local.target.db_keys == ["platform"]

    reset_topology_resolver()
    assert resolve_capability("demo.org.user-roles").target.mode == CapabilityMode.REMOTE


def test_domain_service_registry_derives_and_rejects_conflict() -> None:
    """域 → 服务键登记：视图只读副本、按域取服务键、同域异服务即拒。"""
    assert service_key_for_domain("org") == "mdm"
    assert service_key_for_domain("nothing") is None
    assert domain_service_view() == {"org": "mdm", "user": "platform"}

    with pytest.raises(CatalogError, match="业务域承载服务冲突：'org'"):
        register_domain_services(ConcurrentStableFrozenDict({"org": "other"}))


def test_default_resolver_accepts_custom_template() -> None:
    """默认实现允许换基址模板（部署形态差异不改变解析协议）。"""
    resolver = DomainLayoutTopologyResolver(base_url_template="https://{service}.internal:8443/")

    target = resolver.resolve("org")

    assert target.base_url == "https://mdm.internal:8443"
    assert target.mode == CapabilityMode.REMOTE
