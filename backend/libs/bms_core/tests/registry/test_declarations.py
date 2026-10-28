"""产品声明注册核心用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖纯逻辑三块：
- 内容指纹（稳定 / 随要素变化）；
- 整体对账（新增 / 未变 / 覆盖 / 退役 / 跨产品撞键 / 同产品重复）；
- 跨产品一致性校验（域未登记 / 能力要素缺失 / 消费方未登记 / 使用声明不可兑现 / 错误码段位与撞码）。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.collaboration.usage import CapabilityUsage, capability_usage_view
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.datasource.registry import DataSourceRecord
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    DeclarationPayload,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
    declaration_wire,
    from_manifest,
    plan_declarations,
    validate_declarations,
)
from bms_core.services.module_registry import (
    CollaborationRecord,
    ErrorCodeRecord,
    ModuleRecord,
    ProductRecord,
    ProductRouteRecord,
    SeedRecord,
)


def _capability(name: str = "demo.org.user-roles", *, kind: str = "read", **kwargs: object) -> CollaborationRecord:
    """构造能力记录（缺省合法读出口）。

    Args:
        name: 能力名。
        kind: 访问面类别。
        **kwargs: 覆盖字段（如 `branch_id` / `default_consumers`）。

    Returns:
        CollaborationRecord: 能力记录。
    """
    base: Any = {
        "name": name,
        "domain": "org",
        "kind": kind,
        "contract_version": "0.1.0",
        "path": "/api/v1/demo/roles",
        "product_key": "demo",
        "frontend_prefix": "demo",
    }
    base.update(kwargs)
    return CollaborationRecord(**base)  # type: ignore[arg-type]


def _payload(**kwargs: object) -> DeclarationPayload:
    """构造注册载荷（缺省仅产品键与服务键）。

    Args:
        **kwargs: 覆盖段（如 `collaborations=`）。

    Returns:
        DeclarationPayload: 注册载荷。
    """
    base: Any = {"product_key": "demo", "service_key": "demo"}
    base.update(kwargs)
    return DeclarationPayload(**base)


def _snapshot(*, owner: str = "demo", **kwargs: object) -> RegistrySnapshot:
    """按类别构造注册表现状（自动补内容指纹 / 行主键 / 声明方）。

    Args:
        owner: 记录自带 `product_key` 缺失时的声明方（默认 `demo`；平台行用 `platform`）。
        **kwargs: `{类别: 记录列表}`。

    Returns:
        RegistrySnapshot: 注册表现状。
    """
    records: ConcurrentStableDict[str, ConcurrentStableList[object]] = ConcurrentStableDict()
    hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    ids: ConcurrentStableDict[str, ConcurrentStableDict[str, int]] = ConcurrentStableDict()
    retired: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for kind in DECLARATION_KINDS:
        items = ConcurrentStableList(cast("Any", kwargs.get(kind) or ()))
        records.set(kind, items)
        kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        kind_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        kind_owners: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for index, record in enumerate(items):
            key = declaration_key(kind, record)
            kind_hashes.set(key, content_hash_of(kind, record))
            kind_ids.set(key, index + 1)
            kind_owners.set(key, str(getattr(record, "product_key", None) or owner))
        hashes.set(kind, kind_hashes)
        ids.set(kind, kind_ids)
        owners.set(kind, kind_owners)
        retired.set(kind, ConcurrentStableSet())
    return RegistrySnapshot(records=records, hashes=hashes, ids=ids, retired=retired, owners=owners)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    """用例隔离占位（本模块只用纯函数，无进程级状态）。

    Yields:
        None: 用例运行期。
    """
    yield


def test_content_hash_is_stable_and_field_sensitive() -> None:
    """内容指纹：同要素稳定、要素变化即变（与字段顺序无关）。"""
    record = _capability()
    assert content_hash_of("collaborations", record) == content_hash_of("collaborations", record)
    changed = _capability(path="/api/v1/demo/roles-v2")
    assert content_hash_of("collaborations", record) != content_hash_of("collaborations", changed)
    assert content_hash_of("collaborations", record) != content_hash_of("usages", record)


def test_declaration_key_unknown_kind_rejected() -> None:
    """未知类别取键即拒（内部契约错误，不静默）。"""
    from bms_core.core.exceptions import CatalogError

    with pytest.raises(CatalogError, match="未知的声明类别"):
        declaration_key("unknown", _capability())


def test_plan_creates_on_empty_registry() -> None:
    """空注册表：八类声明全部新增，无冲突。"""
    payload = _payload(
        products=ConcurrentStableFrozenList((ProductRecord(product_key="demo", name="演示产品"),)),
        collaborations=ConcurrentStableFrozenList((_capability(),)),
        usages=ConcurrentStableFrozenList((CapabilityUsage(name="demo.org.user-roles"),)),
    )

    plan, conflicts = plan_declarations(payload, _snapshot())

    assert list(conflicts) == []
    assert len(plan.created.get("collaborations") or ()) == 1
    assert len(plan.created.get("usages") or ()) == 1
    assert plan.retired.get("collaborations") == []
    assert plan.is_empty() is False


def test_plan_unchanged_when_content_identical() -> None:
    """同内容重复注册：全 `unchanged`，不写库。"""
    record = _capability()
    payload = _payload(collaborations=ConcurrentStableFrozenList((record,)))

    plan, conflicts = plan_declarations(payload, _snapshot(collaborations=[record]))

    assert list(conflicts) == []
    assert len(plan.unchanged.get("collaborations") or ()) == 1
    assert plan.is_empty() is True


def test_plan_updates_when_content_changed() -> None:
    """内容变化：进 `updated`（覆盖而非拒收）。"""
    old = _capability()
    new = _capability(path="/api/v1/demo/roles-v2")
    payload = _payload(collaborations=ConcurrentStableFrozenList((new,)))

    plan, conflicts = plan_declarations(payload, _snapshot(collaborations=[old]))

    assert list(conflicts) == []
    assert [record.path for record in plan.updated.get("collaborations") or ()] == ["/api/v1/demo/roles-v2"]


def test_plan_retires_absent_records() -> None:
    """本次未声明的记录：进 `retired`。"""
    kept = _capability()
    dropped = _capability(name="demo.org.dept-data", kind="dataset", data_source_key="demo_dept")
    payload = _payload(collaborations=ConcurrentStableFrozenList((kept,)))

    plan, _conflicts = plan_declarations(payload, _snapshot(collaborations=[kept, dropped]))

    assert list(plan.retired.get("collaborations") or ()) == ["demo.org.dept-data"]


def test_plan_rejects_cross_product_conflict() -> None:
    """同一键被其他产品占用：冲突（不静默覆盖）。"""
    other = _capability(product_key="other")
    mine = _capability(path="/api/v1/demo/roles-v2")
    payload = _payload(collaborations=ConcurrentStableFrozenList((mine,)))

    plan, conflicts = plan_declarations(payload, _snapshot(collaborations=[other]))

    assert any("跨产品撞键" in item for item in conflicts)
    assert plan.created.get("collaborations") == []


def test_plan_rejects_duplicate_within_payload() -> None:
    """同一产品在一次上报里重复声明：冲突。"""
    payload = _payload(collaborations=ConcurrentStableFrozenList((_capability(), _capability())))

    _plan, conflicts = plan_declarations(payload, _snapshot())

    assert any("重复声明" in item for item in conflicts)


def test_validate_accepts_well_formed_payload() -> None:
    """合规载荷：无错误（域已登记、消费方已登记、使用声明指向已注册能力）。"""
    payload = _payload(
        services=ConcurrentStableFrozenList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_key="demo",
                    service_group="product",
                    product_key="demo",
                ),
            )
        ),
        collaborations=ConcurrentStableFrozenList(
            (_capability(default_consumers=ConcurrentStableFrozenList(("platform",))),)
        ),
        usages=ConcurrentStableFrozenList((CapabilityUsage(name="demo.org.user-roles"),)),
    )
    warnings: ConcurrentStableList[str] = ConcurrentStableList()

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=warnings,
    )

    assert list(errors) == []


def test_validate_rejects_unknown_domain_and_missing_element() -> None:
    """域未登记与 `txn-branch` 要素缺失分别拒收。"""
    payload = _payload(
        services=ConcurrentStableFrozenList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_key="demo",
                    service_group="product",
                    product_key="demo",
                ),
            )
        ),
        collaborations=ConcurrentStableFrozenList(
            (
                _capability(name="demo.org.user-posts", kind="txn-branch"),
                _capability(name="demo.unknown.roles", domain="nowhere"),
            )
        ),
    )

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    joined = "；".join(errors)
    assert "txn-branch 类须声明 branch_id 与 branch_op" in joined
    assert "提供方业务域未登记（nowhere）" in joined


def test_validate_warns_unregistered_consumer() -> None:
    """默认消费方未登记：只告警不拒收（03_01 方案 A：平台先起、产品后起是常态）。"""
    payload = _payload(
        collaborations=ConcurrentStableFrozenList(
            (_capability(default_consumers=ConcurrentStableFrozenList(("nobody",))),)
        )
    )
    warnings: ConcurrentStableList[str] = ConcurrentStableList()

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform",)),
        warnings=warnings,
    )

    assert list(errors) == []
    assert any("默认消费方尚未注册（nobody" in item for item in warnings)


def test_validate_rejects_unregistered_usage_and_write_degrade() -> None:
    """使用声明：未注册能力只告警；对写能力声明降级 / 缺理由仍拒收。"""
    write_capability = _capability(
        name="demo.org.user-posts",
        kind="txn-branch",
        branch_id="d",
        branch_op="demo.user-posts.assign",
    )
    payload = _payload(
        collaborations=ConcurrentStableFrozenList((write_capability,)),
        usages=ConcurrentStableFrozenList(
            (
                CapabilityUsage(name="demo.org.missing"),
                CapabilityUsage(name="demo.org.user-posts", degrade="empty", reason="不该降级"),
                CapabilityUsage(name="demo.org.user-posts", degrade="empty"),
            )
        ),
    )

    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=warnings,
    )

    joined = "；".join(errors)
    # 未注册能力只告警（方案 A）；写能力降级 / 缺理由仍拒收（契约硬约束）
    assert "被消费能力未注册" not in joined
    assert any("尚未注册" in item for item in warnings)
    assert "写 / 强一致能力不得声明降级" in joined
    assert "声明降级须给出理由" in joined


def test_validate_errcodes_segment_and_collision() -> None:
    """错误码：段位与码不一致、跨产品撞码分别拒收。"""
    payload = _payload(
        services=ConcurrentStableFrozenList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_key="demo",
                    service_group="product",
                    product_key="demo",
                    errcode_segment="88",
                ),
            )
        ),
        errcodes=ConcurrentStableFrozenList(
            (
                ErrorCodeRecord(
                    code=880001,
                    domain="demo",
                    http_status=200,
                    message_key="demo.error.bad",
                    severity="warning",
                    description="段位不符",
                    product_key="demo",
                    segment="99",
                ),
                ErrorCodeRecord(
                    code=770001,
                    domain="demo",
                    http_status=200,
                    message_key="demo.error.taken",
                    severity="warning",
                    description="撞码",
                    product_key="demo",
                    segment="77",
                ),
            )
        ),
    )
    other = ErrorCodeRecord(
        code=770001,
        domain="other",
        http_status=200,
        message_key="other.error.taken",
        severity="warning",
        description="他产品已注册",
        product_key="other",
        segment="77",
    )

    errors = validate_declarations(
        payload,
        _snapshot(errcodes=[other]),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    joined = "；".join(errors)
    assert "880001：码与段位不一致" in joined
    assert "770001：跨产品撞码" in joined


def test_from_manifest_maps_all_eight_kinds() -> None:
    """清单 → 载荷：八段一一对应，服务键取服务行、缺省回落产品键。"""

    class _Manifest:
        """清单替身（只提供载荷映射所需字段）。"""

        product_key = "demo"
        products = ConcurrentStableFrozenList()
        services = ConcurrentStableFrozenList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_key="demo-svc",
                    service_group="product",
                    product_key="demo",
                ),
            )
        )
        product_routes = ConcurrentStableFrozenList()
        data_sources = ConcurrentStableFrozenList()
        collaborations = ConcurrentStableFrozenList()
        seeds = ConcurrentStableFrozenList()
        error_codes = ConcurrentStableFrozenList()
        usages = ConcurrentStableFrozenList()

    payload = from_manifest(_Manifest())

    assert payload.product_key == "demo"
    assert payload.service_key == "demo-svc"
    assert payload.contract_version == "0.1.0"
    assert payload.of("products") == []


def test_from_manifest_without_services_falls_back_to_product_key() -> None:
    """清单无服务行：服务键回落产品键（注册方与服务行一致的校验留给校验步）。"""

    class _Manifest:
        """空清单替身。"""

        product_key = "demo"
        products = ConcurrentStableFrozenList()
        services = ConcurrentStableFrozenList()
        product_routes = ConcurrentStableFrozenList()
        data_sources = ConcurrentStableFrozenList()
        collaborations = ConcurrentStableFrozenList()
        seeds = ConcurrentStableFrozenList()
        error_codes = ConcurrentStableFrozenList()
        usages = ConcurrentStableFrozenList()

    payload = from_manifest(_Manifest())

    assert payload.service_key == "demo"


def test_plan_covers_routes_and_seeds_kinds() -> None:
    """路由与种子同样参与整体对账（新增 + 退役）。"""
    route = ProductRouteRecord(product_key="demo", domain="demo", service_key="demo")
    seed = SeedRecord(
        name="demo-seed",
        module="demo.seeds",
        entry="seed_demo",
        service="demo",
        db_key="platform_platform",
    )
    payload = _payload(
        product_routes=ConcurrentStableFrozenList((route,)),
        seeds=ConcurrentStableFrozenList((seed,)),
    )
    vanished = SeedRecord(
        name="old-seed",
        module="demo.seeds",
        entry="seed_old",
        service="demo",
        db_key="platform_platform",
    )

    plan, _conflicts = plan_declarations(payload, _snapshot(seeds=[vanished]))

    assert len(plan.created.get("product_routes") or ()) == 1
    assert len(plan.created.get("seeds") or ()) == 1
    assert list(plan.retired.get("seeds") or ()) == ["old-seed"]


def test_plan_restores_retired_record() -> None:
    """曾退役的记录再次声明：进 `updated`（恢复）。"""
    record = _capability()
    snapshot = _snapshot(collaborations=[record])
    snapshot.retired.set("collaborations", ConcurrentStableSet(("demo.org.user-roles",)))
    payload = _payload(collaborations=ConcurrentStableFrozenList((record,)))

    plan, _conflicts = plan_declarations(payload, snapshot)

    assert len(plan.updated.get("collaborations") or ()) == 1
    assert plan.unchanged.get("collaborations") == []


def test_validate_service_key_must_be_declared() -> None:
    """注册方服务键未在服务行出现：拒收（注册方与服务行须一致）。"""
    payload = _payload(service_key="demo-svc")

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    assert any("未在服务行声明" in item for item in errors)


def test_validate_warns_when_only_usages_declared() -> None:
    """只声明使用项：给出警示（不阻断）。"""
    payload = _payload(
        usages=ConcurrentStableFrozenList((CapabilityUsage(name="demo.org.user-roles"),)),
    )
    warnings: ConcurrentStableList[str] = ConcurrentStableList()

    errors = validate_declarations(
        payload,
        _snapshot(collaborations=[_capability()]),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=warnings,
    )

    assert list(errors) == []
    assert any("仅声明使用" in item for item in warnings)


def test_validate_service_key_declared_by_separate_service_row() -> None:
    """产品键与服务键不同但服务行已声明：不报错（单服务产品通常相同，多服务允许不同）。"""
    payload = _payload(
        service_key="demo-svc",
        services=ConcurrentStableFrozenList(
            (
                ModuleRecord(
                    module_key="demo",
                    name="演示服务",
                    table_prefix="demo_",
                    event_domain="demo",
                    service_key="demo-svc",
                    service_group="product",
                    product_key="demo",
                ),
            )
        ),
    )

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    assert list(errors) == []


def test_validate_collaboration_element_matrix() -> None:
    """能力要素矩阵：`codes` 缺码 / `dataset` 缺数据源键 / 非 codes 缺路径 各自拒收。"""
    payload = _payload(
        collaborations=ConcurrentStableFrozenList(
            (
                _capability(name="demo.org.codes-empty", kind="codes", path=None),
                _capability(name="demo.org.dept-data", kind="dataset"),
                _capability(name="demo.org.no-path", path=None),
            )
        ),
    )

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    joined = "；".join(errors)
    assert "codes 类须声明业务码 / 权限码" in joined
    assert "dataset 类须声明 data_source_key" in joined
    assert "访问面路径缺失（kind=read）" in joined


def test_validate_codes_capability_with_permission_codes_passes() -> None:
    """`codes` 类声明了权限码：要素齐备，不报错。"""
    payload = _payload(
        collaborations=ConcurrentStableFrozenList(
            (
                _capability(
                    name="demo.org.admin-codes",
                    kind="codes",
                    path=None,
                    permission_codes=ConcurrentStableFrozenList(("demo:query",)),
                ),
            )
        ),
    )

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    assert list(errors) == []


def test_validate_errcode_segment_from_registry_services() -> None:
    """段位来源含注册表现有服务行（`setdefault` 分支）且合法时放行。"""
    payload = _payload(
        errcodes=ConcurrentStableFrozenList(
            (
                ErrorCodeRecord(
                    code=330031,
                    domain="org",
                    http_status=404,
                    message_key="demo.error.post_not_found",
                    severity="warning",
                    description="岗位不存在",
                    product_key="demo",
                    segment="33",
                ),
            )
        ),
    )
    existing_service = ModuleRecord(
        module_key="demo",
        name="演示服务",
        table_prefix="demo_",
        event_domain="demo",
        service_key="demo",
        service_group="product",
        product_key="demo",
        errcode_segment="33",
    )

    errors = validate_declarations(
        payload,
        _snapshot(services=[existing_service]),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    assert list(errors) == []


def test_jsonable_converts_mapping_and_stable_collections() -> None:
    """指纹要素转换：映射与插入序集合都转成可序列化结构（保证跨进程稳定）。"""

    class _Record:
        """带映射与插入序集合要素的替身（含映射内嵌普通列表）。"""

        name = "demo.org.x"
        tables = ConcurrentStableFrozenDict({"a": "b", "list": ["x", "y"]})
        after = ConcurrentStableFrozenList(("s1", "s2"))

    seed_payload = content_hash_of("seeds", _Record())

    assert seed_payload == content_hash_of("seeds", _Record())
    assert seed_payload != content_hash_of(
        "seeds",
        type(
            "_Other",
            (),
            {
                "name": "demo.org.x",
                "tables": ConcurrentStableFrozenDict({"a": "c"}),
                "after": ConcurrentStableFrozenList(("s1", "s2")),
            },
        )(),
    )


def test_validate_usage_degrades_rejected_modes() -> None:
    """使用声明：`stale` 降级暂不支持、错误码段位非法各自拒收。"""
    payload = _payload(
        collaborations=ConcurrentStableFrozenList((_capability(),)),
        usages=ConcurrentStableFrozenList(
            (CapabilityUsage(name="demo.org.user-roles", degrade="stale", reason="旧副本"),)
        ),
        errcodes=ConcurrentStableFrozenList(
            (
                ErrorCodeRecord(
                    code=880001,
                    domain="demo",
                    http_status=200,
                    message_key="demo.error.bad",
                    severity="warning",
                    description="段位长度非法",
                    product_key="demo",
                    segment="9",
                ),
            )
        ),
    )

    errors = validate_declarations(
        payload,
        _snapshot(),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    joined = "；".join(errors)
    assert "降级模式暂不支持" in joined
    assert "段位非法（9）" in joined


def test_validate_ignores_current_service_without_segment() -> None:
    """注册表现有服务行无段位：跳过段位基准收集（不误判）。"""
    payload = _payload()
    segmentless = ModuleRecord(
        module_key="demo",
        name="演示服务",
        table_prefix="demo_",
        event_domain="demo",
        service_key="demo",
        service_group="product",
        product_key="demo",
    )

    errors = validate_declarations(
        payload,
        _snapshot(services=[segmentless]),
        domain_services=ConcurrentStableDict({"org": "demo"}),
        consumer_keys=ConcurrentStableSet(("platform", "demo")),
        warnings=ConcurrentStableList(),
    )

    assert list(errors) == []


def test_declaration_models_registered_tables() -> None:
    """注册表六模型可导入且表名与表设计一致（模型层无分支，仅需被导入覆盖）。"""
    from bms_core.models.platform.declaration import (
        SysCollaboration,
        SysCollaborationUsage,
        SysDataSource,
        SysErrcode,
        SysProductRoute,
        SysSeed,
    )

    assert SysCollaboration.__tablename__ == "sys_collaboration"
    assert SysCollaborationUsage.__tablename__ == "sys_collaboration_usage"
    assert SysSeed.__tablename__ == "sys_seed"
    assert SysErrcode.__tablename__ == "sys_errcode"
    assert SysDataSource.__tablename__ == "sys_data_source"
    assert SysProductRoute.__tablename__ == "sys_product_route"


def test_plan_does_not_retire_other_products_rows() -> None:
    """共享表按声明方作用域对账：别的产品的行不因本次未声明而退役。"""
    ours = ProductRecord(product_key="demo", name="演示产品")
    theirs = ProductRecord(product_key="other", name="其他产品")
    payload = _payload(products=ConcurrentStableFrozenList((ours,)))

    plan, conflicts = plan_declarations(payload, _snapshot(products=[ours, theirs]))

    assert list(conflicts) == []
    assert plan.retired.get("products") == []
    assert len(plan.unchanged.get("products") or ()) == 1


def test_platform_owns_service_rows_without_product_key() -> None:
    """平台服务行（`product_key` 为空）归 `platform`：平台注册时不误退役，也不与其他产品撞键。"""
    platform_row = ModuleRecord(
        module_key="sys",
        name="平台地基服务",
        table_prefix="sys_",
        event_domain="sys",
        service_key="platform",
    )
    product_row = ModuleRecord(
        module_key="mdm",
        name="主数据服务",
        table_prefix="mdm_",
        event_domain="mdm",
        service_key="mdm",
        service_group="product",
        product_key="mdm",
    )
    payload = DeclarationPayload(
        product_key="platform",
        service_key="platform",
        services=ConcurrentStableFrozenList((platform_row,)),
    )

    plan, conflicts = plan_declarations(payload, _snapshot(owner="platform", services=[platform_row, product_row]))

    assert list(conflicts) == []
    assert plan.retired.get("services") == []
    assert len(plan.unchanged.get("services") or ()) == 1


def test_parse_manifest_text_feeds_payload() -> None:
    """清单文本 → 载荷（注册通道输入解析与文件装载同一实现）。"""
    from bms_core.registry.products import parse_manifest_text

    text = """
product_key = "demo"

[[services]]
module_key = "demo"
service_key = "demo-svc"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"

[[usages]]
name = "demo.org.roles"
degrade = "empty"
reason = "断链按无角色"
"""
    payload = from_manifest(parse_manifest_text(text, source="<test>"))

    assert payload.product_key == "demo"
    assert payload.service_key == "demo-svc"
    assert len(payload.usages) == 1


def test_wire_roundtrip_keeps_content_fingerprint() -> None:
    """传输形态往返（`declaration_wire` → `record_from_wire`）：内容指纹不变（八类逐类）。"""
    from bms_core.registry.declarations import record_from_wire

    samples = {
        "products": ProductRecord(product_key="demo", name="演示产品"),
        "services": ModuleRecord(
            module_key="demo",
            service_key="demo",
            name="演示服务",
            table_prefix="demo_",
            event_domain="demo",
            service_group="product",
            product_key="demo",
        ),
        "product_routes": ProductRouteRecord(product_key="demo", domain="demo", service_key="demo"),
        "data_sources": DataSourceRecord(
            data_source_key="demo_dept",
            name="部门",
            data_source="demo.demo.dept",
            product_key="demo",
        ),
        "collaborations": _capability(),
        "seeds": SeedRecord(
            name="demo-seed",
            module="demo.seeds",
            entry="seed_demo",
            service="demo",
            db_key="platform_platform",
        ),
        "errcodes": ErrorCodeRecord(
            code=880001,
            domain="demo",
            http_status=200,
            message_key="demo.error.bad",
            severity="warning",
            description="说明",
            product_key="demo",
            segment="88",
        ),
        "usages": CapabilityUsage(name="demo.user.roles", degrade="empty", reason="断链按无角色"),
    }
    for kind, record in samples.items():
        wire = declaration_wire(kind, record)
        restored = record_from_wire(kind, ConcurrentStableDict(cast("Any", wire)))
        assert content_hash_of(kind, restored) == content_hash_of(kind, record), kind


def test_record_from_wire_rejects_unknown_kind() -> None:
    """未知类别还原即拒（内部契约错误）。"""
    from bms_core.core.exceptions import CatalogError
    from bms_core.registry.declarations import record_from_wire

    with pytest.raises(CatalogError, match="未知的声明类别"):
        record_from_wire("unknown", ConcurrentStableDict())


async def test_snapshot_from_wire_builds_registry_view() -> None:
    """快照响应体还原：八类记录 + 指纹 + 声明方；结构非法即拒。"""
    from bms_core.registry.remote import snapshot_from_wire

    wire = {
        "snapshot_version": "2",
        "declarations": {
            "collaborations": [dict(declaration_wire("collaborations", _capability()))],
            "usages": [dict(declaration_wire("usages", CapabilityUsage(name="demo.user.roles")))],
        },
    }

    snapshot = await snapshot_from_wire(wire)

    assert len(snapshot.of("collaborations")) == 1
    assert snapshot.owner_of("collaborations", "demo.org.user-roles") == "demo"
    assert len(snapshot.of("usages")) == 1
    assert snapshot.of("seeds") == []


async def test_snapshot_from_wire_rejects_bad_payload() -> None:
    """快照响应体非法：非对象 / 缺段 / 段非数组 三种都拒。"""
    from bms_core.core.exceptions import CatalogError
    from bms_core.registry.remote import snapshot_from_wire

    with pytest.raises(CatalogError, match="data 非对象"):
        await snapshot_from_wire(None)
    with pytest.raises(CatalogError, match="缺 declarations 段"):
        await snapshot_from_wire({"snapshot_version": "1"})
    with pytest.raises(CatalogError, match="非数组"):
        await snapshot_from_wire({"declarations": {"products": "x"}})
    with pytest.raises(CatalogError, match="含非对象行"):
        await snapshot_from_wire({"declarations": {"products": ["x"]}})


def test_parse_manifest_text_rejects_bad_input() -> None:
    """清单文本非法：TOML 语法错与使用声明降级模式非法均即拒。"""
    from bms_core.core.exceptions import CatalogError
    from bms_core.registry.products import parse_manifest_text

    with pytest.raises(CatalogError, match="TOML 非法"):
        parse_manifest_text("product_key = [", source="<test>")

    with pytest.raises(CatalogError, match="degrade 非法"):
        parse_manifest_text(
            'product_key = "demo"\n\n[[usages]]\nname = "demo.user.roles"\ndegrade = "oops"\n',
            source="<test>",
        )


def test_projection_groups_multiple_usages_of_same_declarer() -> None:
    """同一声明方多条使用声明：同组累加（不覆盖）。"""
    from bms_core.registry.projection import project_registry

    snapshot = _snapshot(
        usages=[
            CapabilityUsage(name="demo.user.roles"),
            CapabilityUsage(name="demo.user.posts", degrade="empty", reason="断链"),
        ],
        owners=ConcurrentStableDict(
            {
                "usages": ConcurrentStableDict(
                    {"demo.user.roles": "demo", "demo.user.posts": "demo"},
                )
            }
        ),
    )

    project_registry(snapshot)

    assert [item.name for item in capability_usage_view().get("demo") or ()] == [
        "demo.user.roles",
        "demo.user.posts",
    ]


def test_declaration_payload_of_and_snapshot_accessors() -> None:
    """载荷 / 现状的取值访问器：缺类别返回空、缺键返回 None。"""
    payload = _payload()
    snapshot = _snapshot(collaborations=[_capability()])

    assert payload.of("seeds") == []
    assert snapshot.hash_of("collaborations", "demo.org.user-roles") is not None
    assert snapshot.hash_of("collaborations", "missing") is None
    assert snapshot.row_id("collaborations", "demo.org.user-roles") == 1
    assert snapshot.row_id("collaborations", "missing") is None
    assert snapshot.is_retired("collaborations", "demo.org.user-roles") is False
    assert snapshot.owner_of("collaborations", "demo.org.user-roles") == "demo"
    assert snapshot.owner_of("collaborations", "missing") is None
    assert snapshot.of("seeds") == []
    wire = declaration_wire("collaborations", _capability())
    assert wire.get("name") == "demo.org.user-roles"
    assert wire.get("path") == "/api/v1/demo/roles"
