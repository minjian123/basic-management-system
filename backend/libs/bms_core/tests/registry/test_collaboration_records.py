"""能力（第五类）与种子（第六类）记录：视图族 / 唯一性纪律 / 访问面模板填充（07B `02_01`）。

与既有 `ModuleRecord` / `ProductRecord` 同口径：装载时注册、运行期只读、不落库、
同键同值合并 / 同键异值即拒；访问面模板填充由记录自身承担（消费方不自行拼接）。
新建用例的 Kiwi 编号由 07B `05_01` 统一登记后回填。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import CatalogError, ParamError
from bms_core.services.module_registry import (
    CollaborationRecord,
    SeedRecord,
    collaboration_catalog_view,
    normalize_capability_path,
    register_collaboration_records,
    register_seed_records,
    reset_collaboration_records,
    reset_seed_records,
    seed_catalog_view,
)


def _collaboration(
    *,
    path: str | None = "/api/v1/demo/user-roles",
    kind: str = "read",
    contract_version: str = "0.1.0",
    permission_codes: ConcurrentStableFrozenList[str] | None = None,
) -> CollaborationRecord:
    """构造能力记录（缺省 `read` 类，按需覆盖字段）。

    Args:
        path: 访问面路径模板（`codes` 类为 None）。
        kind: 访问面类别。
        contract_version: 契约版本。
        permission_codes: 业务码 / 权限码集合。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name="demo.org.user-roles",
        domain="org",
        kind=kind,
        contract_version=contract_version,
        path=path,
        permission_codes=permission_codes or ConcurrentStableFrozenList(),
    )


def _seed(*, entry: str = "seed_admin_codes") -> SeedRecord:
    """构造种子记录（按需覆盖入口名）。

    Args:
        entry: 入口函数名。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(name="demo-admin-codes", module="demo.seeds.permissions", entry=entry)


@pytest.fixture(autouse=True)
def _isolate_records() -> Iterator[None]:
    """每例前后清空能力与种子注入表（进程级全局状态）。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_seed_records()
    yield
    reset_collaboration_records()
    reset_seed_records()


def test_normalize_capability_path() -> None:
    """路径参数名不参与比较：`{任意名}` 统一归一为 `{}`。"""
    assert normalize_capability_path("/api/v1/demo/depts/{dept_id}/roles") == "/api/v1/demo/depts/{}/roles"
    assert normalize_capability_path("/api/v1/demo/user-roles") == "/api/v1/demo/user-roles"


def test_render_path_fills_parameters() -> None:
    """模板填充：占位符按参数替换；重复占位与无占位路径均可用。"""
    record = _collaboration(path="/api/v1/demo/depts/{dept_id}/roles/{role_id}")

    assert record.render_path(dept_id=7, role_id=3) == "/api/v1/demo/depts/7/roles/3"
    assert _collaboration().render_path() == "/api/v1/demo/user-roles"


def test_render_path_rejects_missing_and_extra() -> None:
    """参数缺失 / 多余均拒（防静默拼错），错误信息含能力名与参数名。"""
    record = _collaboration(path="/api/v1/demo/depts/{dept_id}")

    with pytest.raises(ParamError, match="缺少路径参数（dept_id）"):
        record.render_path()

    with pytest.raises(ParamError, match="路径参数多余（role_id）"):
        record.render_path(dept_id=1, role_id=2)


def test_render_path_rejects_codes_kind() -> None:
    """`codes` 类无访问面：调用填充即报错（消费方不得据此发起调用）。"""
    record = _collaboration(kind="codes", path=None, permission_codes=ConcurrentStableFrozenList(("demo:query",)))

    assert record.normalized_path() is None
    with pytest.raises(ParamError, match="能力无访问面"):
        record.render_path()


def test_collaboration_registry_merges_and_views() -> None:
    """能力注册：同键同值幂等合并、视图按插入序返回、复位清空。"""
    assert collaboration_catalog_view() == []

    record = _collaboration()
    register_collaboration_records(ConcurrentStableFrozenList((record,)))
    register_collaboration_records(ConcurrentStableFrozenList((record,)))
    assert collaboration_catalog_view() == [record]

    reset_collaboration_records()
    assert collaboration_catalog_view() == []


def test_collaboration_registry_rejects_conflict() -> None:
    """能力注册：同键异值即拒（fail-closed，不静默取一侧）。"""
    register_collaboration_records(ConcurrentStableFrozenList((_collaboration(),)))

    with pytest.raises(CatalogError, match="能力记录同键异值"):
        register_collaboration_records(ConcurrentStableFrozenList((_collaboration(contract_version="0.2.0"),)))


def test_seed_registry_merges_and_rejects_conflict() -> None:
    """种子注册：同键同值幂等、同键异值即拒、视图与复位同口径。"""
    assert seed_catalog_view() == []

    record = _seed()
    register_seed_records(ConcurrentStableFrozenList((record,)))
    register_seed_records(ConcurrentStableFrozenList((record,)))
    assert seed_catalog_view() == [record]

    with pytest.raises(CatalogError, match="种子记录同键异值"):
        register_seed_records(ConcurrentStableFrozenList((_seed(entry="other"),)))

    reset_seed_records()
    assert seed_catalog_view() == []
