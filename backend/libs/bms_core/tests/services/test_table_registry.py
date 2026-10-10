"""表归属登记测试（Kiwi 2176）：单一来源校验 / 表级归属查询 / 链派生 / 双向对账 / 模型声明。"""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import UniqueConstraint

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.services.table_registry import (
    OWNER_EVERY_SERVICE,
    TABLE_OWNERSHIP,
    Datasource,
    TableOwnershipRegistry,
    TableRecord,
    TableStatus,
    chain_tables,
    infrastructure_tables,
    injected_table_records,
    known_service_keys,
    owned_tables_for,
    register_table_records,
    reset_table_records,
    table_names,
    table_owner,
    table_ownership_view,
    table_record,
    validate_table_ownership,
)


@pytest.fixture(autouse=True)
def _reset_injected_table_records() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """每个用例前后清空产品注入记录（进程级注册表隔离，避免用例间串扰）。"""
    reset_table_records()
    yield
    reset_table_records()


_BASE_RECORD = TableRecord(table_name="zzz_item", owner="platform", datasource=Datasource.TENANT)


def _record(table_name: str = "zzz_item", **overrides: object) -> TableRecord:
    """构造测试归属记录（默认满足格式与归属合法性）。"""
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict({"table_name": table_name})
    fields.update(overrides.items())
    return replace(_BASE_RECORD, **fields)  # pyright: ignore[reportCallIssue, reportArgumentType]


@pytest.mark.kiwi_id(2176)
def test_table_ownership_registry_valid() -> None:
    """单一来源清单：全量登记通过校验，覆盖平台层 / 租户层 / 基础设施表三类。"""
    assert TableOwnershipRegistry().validate() == []
    assert len(TABLE_OWNERSHIP) >= 35
    assert "sys_table_ownership" in table_names()
    assert Datasource.BOTH in {record.datasource for record in TABLE_OWNERSHIP}


@pytest.mark.kiwi_id(2176)
def test_table_owner_lookup() -> None:
    """表级归属查询：归属命中 / 基础设施哨兵 / 未登记 None。"""
    assert table_owner("sys_tenant") == "tenant"
    assert table_owner("sys_module") == "platform"
    assert table_owner("sys_product") == "platform"
    assert table_owner("sys_notification") == "notification"
    assert table_owner("ai_chat_log") == "ai"
    assert table_owner("sys_outbox") == OWNER_EVERY_SERVICE
    assert table_owner("zzz_unknown") is None
    record = table_record("sys_tenant")
    assert record is not None and record.datasource == Datasource.PLATFORM
    assert table_record("zzz_unknown") is None
    assert infrastructure_tables() == {"sys_outbox", "sys_event_consumed", "sys_event_dead_letter"}
    assert "permission" in known_service_keys()


@pytest.mark.kiwi_id(2176)
@pytest.mark.kiwi_id(2247)
@pytest.mark.kiwi_id(2249)
def test_owned_tables_and_chain_derivation() -> None:
    """服务表集与链派生：本服务表 + 基础设施三表；库类别过滤生效。"""
    tenant_platform_tables = owned_tables_for("tenant", datasource=Datasource.PLATFORM)
    assert "sys_tenant" in tenant_platform_tables
    assert "sys_tenant_quota" in tenant_platform_tables
    assert owned_tables_for("tenant", datasource=Datasource.PLATFORM, include_planned=False) == frozenset(
        {"sys_tenant", "sys_tenant_database", "sys_user_tenant"}
    )

    platform_chain = chain_tables("platform", Datasource.PLATFORM)
    assert {"sys_module", "sys_module_i18n", "sys_product", "sys_table_ownership"} <= platform_chain
    assert "sys_tenant" not in platform_chain
    assert infrastructure_tables() <= platform_chain
    assert {table for table in platform_chain if table not in infrastructure_tables()} == {
        "sys_module",
        "sys_module_i18n",
        "sys_product",
        "sys_table_ownership",
        "sys_business",
        "sys_business_i18n",
        "sys_action",
        "sys_action_i18n",
        "sys_permission",
        "sys_menu",
        "sys_menu_i18n",
        "sys_form",
        "sys_menu_form",
        "sys_button",
        "sys_field",
        "sys_field_i18n",
    }

    tenant_chain = chain_tables("platform", Datasource.TENANT)
    assert {"sys_dict_type", "sys_dict_item", "sys_query_scheme"} <= tenant_chain
    # 角色域 5 表（02_03）与用户 / 账号锁定两表（02_05）落 platform 服务租户库
    assert {
        "sys_role",
        "sys_user_role",
        "sys_role_permission",
        "sys_role_field",
        "sys_data_scope",
        "sys_user",
        "sys_account_lock",
    } <= tenant_chain
    assert infrastructure_tables() <= tenant_chain
    # 未定稿表（骨架表 / 演示表）不进链（06_02 状态收口）
    assert {"sys_task", "sys_task_log", "sys_icon", "demo"}.isdisjoint(tenant_chain)

    assert chain_tables("tenant", Datasource.PLATFORM) == frozenset(
        {"sys_tenant", "sys_tenant_database", "sys_user_tenant", *infrastructure_tables()}
    )
    # org 服务用户 / 账号锁定两表随 02_05 迁 platform → 该链只余基础设施三表
    assert chain_tables("org", Datasource.TENANT) == frozenset(infrastructure_tables())
    assert chain_tables("identity", Datasource.TENANT) == frozenset(
        {"sys_session", "sys_identity_provider", "sys_client", *infrastructure_tables()}
    )
    assert chain_tables("identity", Datasource.PLATFORM) == frozenset({"sys_user_identity", *infrastructure_tables()})
    # 归档链不含基础设施表（每服务自有仅限平台 / 租户链）
    assert chain_tables("platform", Datasource.ARCHIVE) == frozenset()


@pytest.mark.kiwi_id(2176)
def test_registry_detects_conflicts() -> None:
    """归属校验：表名重复 / 归属未登记 / 库类别与状态非法 / 哨兵误用 / 前缀不符逐项检出。"""
    registry = TableOwnershipRegistry(
        ConcurrentStableList(
            [
                _record("zzz_item"),
                _record("zzz_item", note="重复"),
                _record("zzz_ghost", owner="ghost"),
                _record("zzz_bad_ds", datasource="memory"),
                _record("zzz_bad_status", status="disabled"),
                _record("zzz_sentinel", owner=OWNER_EVERY_SERVICE, datasource=Datasource.TENANT),
                _record("org_item", owner="platform"),
                _record("BadTable"),
            ]
        )
    )
    errors = registry.validate()
    joined = "；".join(errors)
    assert "表名重复登记：zzz_item" in joined
    assert "归属服务未登记（ghost）" in joined
    assert "库类别非法（memory）" in joined
    assert "状态非法（disabled）" in joined
    assert "`*` 归属须为 `both` 库类别" in joined
    assert "表前缀 org_ 不属于归属服务 platform" in joined
    assert "表名非法" in joined


def _ownership_records() -> ConcurrentStableList[TableRecord]:
    """归属清单的插入序副本（接库对账用例的「库中行」基线）。

    Returns:
        ConcurrentStableList[TableRecord]: 归属清单副本。
    """
    return ConcurrentStableList(TABLE_OWNERSHIP)


def _replaced_owner(
    records: ConcurrentStableList[TableRecord], table_name: str, owner: str
) -> ConcurrentStableList[TableRecord]:
    """把指定表的归属改为给定值（集合类无下标赋值，按插入序重建）。

    Args:
        records: 归属记录副本。
        table_name: 目标表名。
        owner: 替换后的归属标签。

    Returns:
        ConcurrentStableList[TableRecord]: 替换后的副本。
    """
    return ConcurrentStableList(
        replace(record, owner=owner) if record.table_name == table_name else record for record in records
    )


@pytest.mark.kiwi_id(2176)
def test_validate_table_ownership_roundtrip() -> None:
    """接库对账：清单自身往返通过；缺行 / 清单外行 / 字段不符逐项检出。"""
    ownership = ConcurrentStableList(TABLE_OWNERSHIP)
    assert validate_table_ownership(ownership, _ownership_records()) == []

    records = _ownership_records()
    records.remove(ownership[0])
    assert any("库中缺登记行" in error for error in validate_table_ownership(ownership, records))

    records = _ownership_records()
    records.add(_record("zzz_extra"))
    assert any("库中登记行不在清单：zzz_extra" in error for error in validate_table_ownership(ownership, records))

    records = _replaced_owner(_ownership_records(), "sys_tenant", "platform")
    errors = validate_table_ownership(ownership, records)
    assert any("owner 与清单不一致" in error for error in errors)


@pytest.mark.kiwi_id(2176)
def test_ownership_model_declared() -> None:
    """模型声明：`sys_table_ownership` 在元数据中，唯一约束为 `(table_name, deleted_at)`，状态默认 enabled。"""
    assert SysTableOwnership.__tablename__ == "sys_table_ownership"
    assert "sys_table_ownership" in Base.metadata.tables
    unique_names = {
        constraint.name for constraint in SysTableOwnership.__table_args__ if isinstance(constraint, UniqueConstraint)
    }
    assert unique_names == {"uq_sys_table_ownership_name_deleted_at"}
    assert SysTableOwnership.__table__.columns["status"].default.arg == TableStatus.ENABLED


def _org_records() -> ConcurrentStableList[TableRecord]:
    """构造产品侧（mdm 组织域）注入记录。

    Returns:
        ConcurrentStableList[TableRecord]: 归属记录（插入序）。
    """
    return ConcurrentStableList(
        [
            TableRecord(table_name="org_dept", owner="org", datasource=Datasource.TENANT, note="部门"),
            TableRecord(table_name="org_post", owner="org", datasource=Datasource.TENANT, note="岗位"),
        ]
    )


@pytest.mark.kiwi_id(2254)
def test_product_table_injection_enters_chain() -> None:
    """产品表装载期注入 → 视图 / 归属查询 / 链派生均可见；清空后回到平台清单。"""
    assert "org_dept" not in chain_tables("org", Datasource.TENANT)
    assert table_owner("org_dept") is None

    register_table_records(_org_records())

    assert len(injected_table_records()) == 2
    assert table_owner("org_dept") == "org"
    assert "org_post" in table_names()
    assert len(table_ownership_view()) == len(TABLE_OWNERSHIP) + 2
    tenant_chain = chain_tables("org", Datasource.TENANT)
    assert {"org_dept", "org_post"} <= tenant_chain
    assert infrastructure_tables() <= tenant_chain
    assert not chain_tables("org", Datasource.ARCHIVE), "租户层产品表不进归档链"
    assert TableOwnershipRegistry().validate() == []

    reset_table_records()
    assert "org_dept" not in chain_tables("org", Datasource.TENANT)


@pytest.mark.kiwi_id(2254)
def test_injection_dedupe_and_conflict() -> None:
    """同 `table_name` 同值 → 去重（视图条目数不变）；异值 → 报「表名重复登记」（fail-closed）。"""
    platform_record = table_record("sys_notification")
    assert platform_record is not None

    register_table_records(ConcurrentStableList([platform_record]))
    assert len(table_ownership_view()) == len(TABLE_OWNERSHIP)
    assert TableOwnershipRegistry().validate() == []

    register_table_records(ConcurrentStableList([replace(platform_record, note="冲突登记")]))
    errors = TableOwnershipRegistry().validate()
    assert any("表名重复登记" in error and "sys_notification" in error for error in errors)
