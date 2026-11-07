"""三级作用域值对象与资源类型注册（07D `01_01`）：纯逻辑用例。

覆盖详细设计 §5 用例 1~12、16~17：
- 值对象不可变 / 派生 / 形态校验（`ParamError`）；
- 记录派生 `module_key` / `resource_kind`、命名规则 `accepts`；
- 清单 `[[resource_types]]` 解析与装载期校验（V1 / V2 / V3 / V4 / V5 / V6 / V7）；
- 注册期跨产品校验（`validate_scope_resource_types`）；
- 视图注册（同键同值合并、同键异值即拒）、投影口径（保留 `disabled`、排除 `retired`）；
- 快照要素（`admin_status` 随快照下发但不进内容指纹）与 wire 往返。
"""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import CatalogError, ParamError
from bms_core.registry.declarations import (
    DeclarationPayload,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
    declaration_wire,
    record_from_wire,
    validate_scope_resource_types,
)
from bms_core.registry.products import inspect_product_manifests, parse_manifest_text
from bms_core.registry.projection import project_registry
from bms_core.resource_scope import (
    SCOPE_RESOURCE_DISABLED,
    ResourceScopeKey,
    ScopeResourceTypeRecord,
    find_scope_resource_type,
    register_scope_resource_types,
    reset_scope_resource_types,
    scope_resource_type_issues,
    scope_resource_type_view,
    scope_resource_types_of,
)
from bms_core.services.module_registry import ModuleRecord

pytestmark = pytest.mark.kiwi_id(2445)

_MINIMAL_MANIFEST = """
product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"
status = "enabled"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"
status = "enabled"

{extra}
"""


@pytest.fixture(autouse=True)
def _reset_view() -> Iterator[None]:
    """每例前后复位作用域资源类型视图（投影整表重建会覆盖进程内经状态）。

    Yields:
        None: 用例运行期。
    """
    reset_scope_resource_types()
    yield
    reset_scope_resource_types()


def _manifest_file(tmp_path: Path, extra: str) -> Path:
    """写一份最小清单（含 `extra` 段）。

    Args:
        tmp_path: 临时目录。
        extra: 追加的清单段（如 `[[resource_types]]` 块）。

    Returns:
        Path: 清单路径。
    """
    path = tmp_path / "demo.toml"
    path.write_text(_MINIMAL_MANIFEST.format(extra=extra), encoding="utf-8")
    return path


def _inspection_errors(tmp_path: Path, extra: str) -> ConcurrentStableList[str]:
    """装载一份清单并取错误明细。

    Args:
        tmp_path: 临时目录。
        extra: 追加的清单段。

    Returns:
        ConcurrentStableList[str]: 错误明细。
    """
    inspection = inspect_product_manifests(ConcurrentStableList([_manifest_file(tmp_path, extra)]))
    return inspection.errors


def _snapshot(**kwargs: object) -> RegistrySnapshot:
    """按类别构造注册表快照（自动补指纹与声明方）。

    Args:
        **kwargs: `{类别: 记录列表}`。

    Returns:
        RegistrySnapshot: 快照。
    """
    records: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
    hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for kind, items in kwargs.items():
        kind_records: ConcurrentStableList[Any] = ConcurrentStableList(cast("Any", items))
        records.set(kind, kind_records)
        kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        kind_owners: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for record in kind_records:
            key = declaration_key(kind, record)
            kind_hashes.set(key, content_hash_of(kind, record))
            kind_owners.set(key, str(getattr(record, "product_key", "") or ""))
        hashes.set(kind, kind_hashes)
        owners.set(kind, kind_owners)
    return RegistrySnapshot(records=records, hashes=hashes, owners=owners)


def test_scope_key_is_immutable_and_derives_new_instance() -> None:
    """值对象不可变；`with_resource` 返回新实例、原实例不变；文本形态用于缓存 / 审计定位。"""
    scope = ResourceScopeKey(tenant_id=1001, module_key="msg")

    with_resource = scope.with_resource("topic_a")

    assert scope.resource_key is None
    assert with_resource.tenant_id == 1001
    assert with_resource.resource_key == "topic_a"
    assert scope.as_text() == "1001/msg/"
    assert with_resource.as_text() == "1001/msg/topic_a"
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass 赋值一律失败（具体异常由 dataclass 给出）
        cast("Any", scope).module_key = "mdm"


def test_scope_key_rejects_invalid_shapes() -> None:
    """形态校验：租户主键非正 / 模块键与资源标识非 snake_case 一律 `ParamError`。"""
    with pytest.raises(ParamError):
        ResourceScopeKey(tenant_id=0, module_key="msg")
    with pytest.raises(ParamError):
        ResourceScopeKey(tenant_id=1, module_key="MSG")
    with pytest.raises(ParamError):
        ResourceScopeKey(tenant_id=1, module_key="msg", resource_key="Topic-1")


def test_record_derives_module_and_kind_and_accepts() -> None:
    """记录由类型标识派生模块键与短名；`accepts` 同时约束长度与命名规则。"""
    record = ScopeResourceTypeRecord(resource_type_key="msg.topic", name="主题", max_length=8)

    assert record.module_key == "msg"
    assert record.resource_kind == "topic"
    assert record.is_active() is True
    assert record.accepts("topic_a") is True
    assert record.accepts("topic_abcdef") is False, "超出 max_length 即拒"
    assert record.accepts("Topic") is False, "命名规则不命中即拒"


def test_manifest_parses_resource_types(tmp_path: Path) -> None:
    """清单解析：`[[resource_types]]` 落记录，`product_key` 由清单归属注入、缺省值可省。"""
    path = _manifest_file(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
retention_days = 30
removal_policy = "purge"
""",
    )

    manifest = parse_manifest_text(path.read_text(encoding="utf-8"), source=str(path))

    assert [record.resource_type_key for record in manifest.resource_types] == ["demo.topic"]
    record = manifest.resource_types[0]
    assert record.product_key == "demo"
    assert record.name_pattern == r"^[a-z][a-z0-9_]{0,63}$"
    assert record.max_length == 64
    assert record.retention_days == 30
    assert record.removal_policy == "purge"
    assert record.status == "enabled"


def test_manifest_accepts_valid_resource_type(tmp_path: Path) -> None:
    """合法声明：装载期无错误。"""
    errors = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
""",
    )

    assert errors == []


def test_manifest_rejects_foreign_module_key(tmp_path: Path) -> None:
    """模块键不属于本清单服务行（V2）：拒装载并提示先声明服务行。"""
    errors = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "mdm.org_node"
name = "组织节点"
""",
    )

    assert any("不属于本产品" in error for error in errors)


def test_manifest_rejects_duplicate_and_bad_pattern(tmp_path: Path) -> None:
    """同一清单重复声明（V4）与命名规则不自洽（V5 / V6）：均拒装载。"""
    duplicated = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"

[[resource_types]]
key = "demo.topic"
name = "主题（重复）"
""",
    )
    nested = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
name_pattern = "^(a+)+$"
""",
    )
    loose = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
name_pattern = "^[a-z]+$"
max_length = 8
""",
    )

    assert any("类型标识重复" in error for error in duplicated)
    assert any("嵌套无界量词" in error for error in nested)
    assert any("未约束长度" in error for error in loose)


def test_pattern_tolerates_optional_group_and_rejects_unbounded_group(tmp_path: Path) -> None:
    """嵌套量词判定：可选分组（`(ab+)?`）不计入（放行）；无界重复分组（`(a+){2,}`）拒。"""
    optional = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
name_pattern = "^(ab+)?c$"
""",
    )
    unbounded = _inspection_errors(
        tmp_path,
        """
[[resource_types]]
key = "demo.topic"
name = "主题"
name_pattern = "^(a+){2,}$"
""",
    )

    assert optional == []
    assert any("嵌套无界量词" in error for error in unbounded)


def test_manifest_rejects_disabled_service_row(tmp_path: Path) -> None:
    """清单服务行停用：类型挂到未启用模块键即拒（登记态，非租户开关）。"""
    path = tmp_path / "demo.toml"
    path.write_text(
        _MINIMAL_MANIFEST.format(
            extra="""
[[resource_types]]
key = "demo.topic"
name = "主题"
"""
        ).replace('product_key = "demo"\nstatus = "enabled"', 'product_key = "demo"\nstatus = "disabled"'),
        encoding="utf-8",
    )

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert any("所属模块键未启用" in error for error in inspection.errors)


def test_type_issues_reject_field_shapes() -> None:
    """字段形态（V7）：保留期 / 到期处置 / 声明态 / 长度 / 显示名逐项拒。"""
    module_keys = ConcurrentStableSet({"demo"})
    base = ScopeResourceTypeRecord(resource_type_key="demo.topic", name="主题")

    assert scope_resource_type_issues(base, module_keys=module_keys) == []
    for broken, keyword in (
        (replace(base, retention_days=-1), "保留期非法"),
        (replace(base, removal_policy="drop"), "到期处置非法"),
        (replace(base, status="retired"), "声明态非法"),
        (replace(base, max_length=0), "max_length 越界"),
        (replace(base, name=""), "显示名为空"),
        (replace(base, name_pattern=""), "命名规则为空"),
        (replace(base, name_pattern="([a-z"), "无法编译"),
        (replace(base, name_pattern="^" + "a*" * 17 + "$"), "量词过多"),
        (replace(base, name_pattern="^[a-z]*$"), "接受空串"),
        (replace(base, resource_type_key="DemoTopic"), "类型标识形态非法"),
    ):
        issues = scope_resource_type_issues(broken, module_keys=module_keys)
        assert any(keyword in issue for issue in issues), f"{keyword} 未命中：{issues}"


def test_validate_scope_resource_types_detects_conflicts() -> None:
    """注册期跨产品校验：跨产品撞键 / 模块键停用 / 同清单重复 / 合法通过。"""
    valid = ScopeResourceTypeRecord(resource_type_key="demo.topic", name="主题", product_key="demo")
    service = ModuleRecord(
        module_key="demo", name="演示服务", table_prefix="demo_", event_domain="demo", service_key="demo"
    )
    payload = DeclarationPayload(
        product_key="demo",
        service_key="demo",
        services=ConcurrentStableFrozenList((service,)),
        resource_types=ConcurrentStableFrozenList((valid,)),
    )
    current = _snapshot(services=[service], resource_types=[valid])

    assert validate_scope_resource_types(payload, current, label="产品 demo") == []

    occupied = _snapshot(
        services=[service],
        resource_types=[replace(valid, product_key="other")],
    )
    conflict = validate_scope_resource_types(payload, occupied, label="产品 demo")
    assert any("已被产品 other 注册" in error for error in conflict)

    duplicate = replace(payload, resource_types=ConcurrentStableFrozenList((valid, valid)))
    assert any(
        "类型标识重复" in error for error in validate_scope_resource_types(duplicate, current, label="产品 demo")
    )

    disabled_service = replace(service, status="disabled")
    disabled_current = _snapshot(services=[disabled_service])
    disabled_current.owners.set("services", ConcurrentStableDict({"demo": "demo"}))
    bare = replace(payload, services=ConcurrentStableFrozenList())
    assert any(
        "所属模块键未启用" in error
        for error in validate_scope_resource_types(bare, disabled_current, label="产品 demo")
    )


def test_view_registers_and_rejects_conflicting_value() -> None:
    """视图：同键同值合并、同键异值即拒；查询按模块键 + 短名命中。"""
    first = ScopeResourceTypeRecord(resource_type_key="demo.topic", name="主题", product_key="demo")
    register_scope_resource_types([first, first])

    assert find_scope_resource_type("demo", "topic") is first
    assert [record.resource_type_key for record in scope_resource_types_of("demo")] == ["demo.topic"]
    assert scope_resource_types_of("mdm") == []

    with pytest.raises(CatalogError):
        register_scope_resource_types([replace(first, name="另一个")])

    assert scope_resource_type_view() == {"demo.topic": first}


def test_projection_keeps_disabled_and_drops_retired() -> None:
    """投影口径：`disabled` 进视图（区分未注册 / 已停用），`retired` 不进。"""
    active = ScopeResourceTypeRecord(resource_type_key="demo.topic", name="主题", product_key="demo")
    disabled = ScopeResourceTypeRecord(
        resource_type_key="demo.bucket",
        name="存储桶",
        product_key="demo",
        status=SCOPE_RESOURCE_DISABLED,
    )
    retired = ScopeResourceTypeRecord(resource_type_key="demo.old", name="旧类型", product_key="demo")
    snapshot = _snapshot(resource_types=[active, disabled, retired])
    snapshot.retired.set("resource_types", ConcurrentStableSet(("demo.old",)))

    project_registry(snapshot)

    view = scope_resource_type_view()
    assert set(view) == {"demo.topic", "demo.bucket"}
    assert find_scope_resource_type("demo", "bucket") is not None
    assert cast("ScopeResourceTypeRecord", find_scope_resource_type("demo", "bucket")).is_active() is False


def test_wire_carries_admin_status_without_changing_hash() -> None:
    """快照要素：`admin_status` 与声明版本随快照下发，但不进内容指纹。"""
    record = ScopeResourceTypeRecord(resource_type_key="demo.topic", name="主题", product_key="demo")

    wire = declaration_wire("resource_types", record)
    stopped = replace(record, admin_status=SCOPE_RESOURCE_DISABLED, declaration_version=3)

    assert wire["admin_status"] == "enabled"
    assert wire["declaration_version"] == 1
    assert content_hash_of("resource_types", record) == content_hash_of("resource_types", stopped)


def test_record_from_wire_roundtrip() -> None:
    """wire → 记录：要素与运营态、声明版本全部还原。"""
    record = ScopeResourceTypeRecord(
        resource_type_key="demo.topic",
        name="主题",
        name_pattern=r"^[a-z]{1,8}$",
        max_length=8,
        retention_days=7,
        removal_policy="purge",
        product_key="demo",
        admin_status=SCOPE_RESOURCE_DISABLED,
        declaration_version=4,
    )

    restored = record_from_wire("resource_types", declaration_wire("resource_types", record))

    assert restored == record
