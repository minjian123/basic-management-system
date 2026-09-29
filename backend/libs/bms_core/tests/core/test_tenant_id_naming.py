"""租户标识按值命名护栏用例（Kiwi 2220，10_05 收口）：内部键一律以雪花 `tenant_id` 表达。

覆盖（防命名 / 值语义回退）：

1. 载体字段按值命名——装租户主键（雪花 id）叫 `tenant_id`、装租户**自身**编码叫 `code`、
   引用租户编码叫 `tenant_code`（库键对象 `DbKey.tenant_code` 为「库名基」白名单）；
2. 令牌声明只认 `tenant_id`（服务 JWT 原 claim `tenant` 已退场）；
3. 平台事件负载键 `tenant_id`，已退场常量 `TENANT_CODE_PAYLOAD_KEY` 不得复活；
4. 发件箱 / 死信 ORM 租户列为 `BIGINT`；
5. 键空间租户位取雪花 id（`bms:{id}:…`，无主键落 `global`）；
6. 租户标识形态判定互斥（纯数字不判为编码、编码不判为主键）；
7. 源码扫描：`bms_core` 与各服务源码中不得再出现 `TENANT_CODE_PAYLOAD_KEY`。

口径依据：任务 10_01 详细设计 §6 命名对齐清单、《后端开发规范》命名节（按值命名）。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import BigInteger, inspect

from bms_core.api.base import AuthContext
from bms_core.api.deps import current_code_of, current_tenant_id_of
from bms_core.cache.base import GLOBAL_TENANT, build_cache_key
from bms_core.db.keys import DbKey
from bms_core.db.tenant import TenantContext, is_tenant_code, is_tenant_id
from bms_core.db.tenant_registry import TenantSnapshot
from bms_core.edge.base import EdgeIdentity
from bms_core.events import platform_events
from bms_core.events.base import EventEnvelope
from bms_core.events.platform_events import TENANT_ID_PAYLOAD_KEY
from bms_core.idp.state.base import IdpFlowState
from bms_core.models.outbox import SysEventDeadLetter, SysOutbox
from bms_core.oauth.token import ServiceTokenSpec
from bms_core.oauth.user_token import UserTokenSpec
from bms_core.oauth.verify import VerifiedToken
from bms_core.outbox.base import DeadLetterRecord, OutboxRecord

REPO_ROOT = Path(__file__).resolve().parents[5]
"""bms 仓库根（本文件位于 `backend/libs/bms_core/tests/core/`）。"""

DEMO_ID = "1001"
"""演示雪花租户主键（十进制字符串）。"""


def _fields(cls: object) -> frozenset[str]:
    """取 dataclass 字段名集合（非 dataclass 返回空集）。

    Args:
        cls: 待取字段的类型对象。

    Returns:
        frozenset[str]: 字段名集合。
    """
    if not dataclasses.is_dataclass(cls):
        return frozenset()
    return frozenset(field.name for field in dataclasses.fields(cls))


def _tenant_column(model: type[object]) -> Any:
    """取 ORM 模型的 `tenant_id` 列对象。

    Args:
        model: ORM 模型类。

    Returns:
        Any: SQLAlchemy 列对象。
    """
    return cast("Any", inspect(model)).columns["tenant_id"]


@pytest.mark.kiwi_id(2220)
def test_tenant_key_carriers_are_named_by_value() -> None:
    """载体字段按值命名：主键 `tenant_id`、自身编码 `code`、引用编码 `tenant_code`（库键白名单）。"""
    for cls in (TenantContext, TenantSnapshot):
        names = _fields(cls)
        assert "code" in names, f"{cls.__name__} 缺租户自身编码字段 `code`"
        assert "tenant_id" in names, f"{cls.__name__} 缺租户主键字段 `tenant_id`"
        assert "tenant_code" not in names, f"{cls.__name__} 不应以 `tenant_code` 承载自身编码"
    assert "db_basis" in _fields(TenantSnapshot), "租户快照应携带库名基 `db_basis`"

    for cls in (AuthContext, EdgeIdentity, IdpFlowState):
        names = _fields(cls)
        assert {"tenant_id", "tenant_code"} <= names, f"{cls.__name__} 应同时携带主键与编码"

    for cls in (ServiceTokenSpec, UserTokenSpec, VerifiedToken, EventEnvelope, OutboxRecord, DeadLetterRecord):
        names = _fields(cls)
        assert "tenant_id" in names, f"{cls.__name__} 租户位应叫 `tenant_id`"
        assert "tenant" not in names, f"{cls.__name__} 不应残留旧声明位 `tenant`"
        assert "tenant_code" not in names, f"{cls.__name__} 租户位不应以编码表达"

    assert "tenant_code" in _fields(DbKey), "库键对象字段名保持（语义为库名基 `db_basis`）"


@pytest.mark.kiwi_id(2220)
def test_event_payload_key_is_tenant_id() -> None:
    """平台事件负载键为 `tenant_id`，已退场常量 `TENANT_CODE_PAYLOAD_KEY` 不得复活。"""
    assert TENANT_ID_PAYLOAD_KEY == "tenant_id"
    assert "TENANT_ID_PAYLOAD_KEY" in platform_events.__all__
    assert not hasattr(platform_events, "TENANT_CODE_PAYLOAD_KEY")
    assert "TENANT_CODE_PAYLOAD_KEY" not in platform_events.__all__


@pytest.mark.kiwi_id(2220)
def test_outbox_models_tenant_column_is_bigint() -> None:
    """发件箱 / 死信租户列为 `BIGINT`（雪花 id），不再以 `VARCHAR` 承载编码。"""
    for model in (SysOutbox, SysEventDeadLetter):
        column = _tenant_column(model)
        assert column.name == "tenant_id"
        assert isinstance(column.type, BigInteger), f"{model.__name__}.tenant_id 应为 BIGINT"


@pytest.mark.kiwi_id(2220)
def test_key_space_and_helpers_use_snowflake_id() -> None:
    """键空间与助手租户位取雪花 id；编码仅用于展示（`current_code_of`）。"""
    assert build_cache_key(tenant=DEMO_ID, domain="dict", business_key="x") == f"bms:{DEMO_ID}:dict:x"
    assert build_cache_key(tenant=None, domain="dict", business_key="x") == f"bms:{GLOBAL_TENANT}:dict:x"

    context = TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(DEMO_ID))
    assert current_tenant_id_of(context) == DEMO_ID
    assert current_code_of(context) == "demo"
    assert current_tenant_id_of(TenantContext(code="demo", db_key="tenant_demo", name="演示租户")) is None
    assert current_code_of(None) is None


@pytest.mark.kiwi_id(2220)
def test_tenant_id_and_code_forms_are_disjoint() -> None:
    """形态判定互斥：纯数字是主键不是编码，编码不是主键（边界一次解析的前提）。"""
    assert is_tenant_id(DEMO_ID) is True
    assert is_tenant_code(DEMO_ID) is False
    assert is_tenant_code("demo") is True
    assert is_tenant_id("demo") is False


@pytest.mark.kiwi_id(2220)
def test_retired_payload_key_absent_in_sources() -> None:
    """源码扫描：`bms_core` 与各服务源码中不得再出现已退场的 `TENANT_CODE_PAYLOAD_KEY`。"""
    backend = REPO_ROOT / "backend"
    roots = (backend / "libs" / "bms_core" / "src", *sorted((backend / "services").glob("*/src")))
    offenders = tuple(
        str(path.relative_to(REPO_ROOT))
        for root in roots
        for path in sorted(root.rglob("*.py"))
        if "TENANT_CODE_PAYLOAD_KEY" in path.read_text(encoding="utf-8")
    )
    assert offenders == ()
