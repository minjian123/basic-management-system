"""04-6 补记：协议包归位基座体系（Kiwi 2444）。

**为什么单独一条**：`test_base_inheritance.py` 是 AST 全仓护栏，2026-11-06 全量预检首次在
`bms_core/msgclient` 上拦下 23 处「无基类 / 仅继承内建基类」——17 处是 `07B 06_01 步 1` 协议链
上移时的存量，当时提交环只选了 msgclient 用例，没跑到全量护栏。本用例把归位结果固定下来：
值对象 → `BaseValueObject`（frozen）、可变状态 → `BaseDataContract`、行为类 → `BaseFrameworkObject`、
异常 → `BizError`，避免下次再漂回裸类。

**只断言形态、不断言行为**：行为回归由各域既有用例负责；这里锁的是「类必须落进三个体系根之一」。
"""

# 归位断言需直接引用模块内私有状态类（`_Entry` / `_Pool` 等），局部关闭该规则
# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, cast

import pytest

from bms_core.core.exceptions import BizError
from bms_core.core.roots import BaseDataContract, BaseFrameworkObject, BaseValueObject
from bms_core.msgclient.adapter.instances import ServiceCatalogInstanceProvider
from bms_core.msgclient.circuit import _Entry
from bms_core.msgclient.frame import Frame, FrameBatch
from bms_core.msgclient.instances import (
    InstanceSelector,
    InstanceSnapshot,
    InstanceUnavailable,
    StaticInstanceProvider,
    _InstanceState,
    _Pool,
)
from bms_core.msgclient.retry import RetryBudget, RetryDecision, RpcRetryBlockedError, SystemClock, SystemJitter
from bms_core.msgclient.rpc import RpcCallError, RpcClient
from bms_core.msgclient.stream import RpcStream
from bms_core.msgclient.transport.base import RpcTransportError
from bms_core.msgclient.transport.connection import H2ClientConnection
from bms_core.msgclient.transport.pool import H2Transport, _H2TransportStream, _Origin
from bms_core.msgclient.transport.stream import H2Stream

pytestmark = pytest.mark.kiwi_id(2444)

_VALUE_OBJECTS = (Frame, FrameBatch, RetryDecision, InstanceSnapshot, _Origin)
"""不可变数据：必须继承 `BaseValueObject` 且声明 `@dataclass(frozen=True)`。"""

_DATA_CONTRACTS = (RetryBudget, _Entry, _InstanceState, _Pool)
"""可变的进程内状态：必须继承 `BaseDataContract`。"""

_FRAMEWORK_OBJECTS = (
    RpcClient,
    RpcStream,
    H2ClientConnection,
    H2Transport,
    H2Stream,
    _H2TransportStream,
    SystemClock,
    SystemJitter,
    StaticInstanceProvider,
    InstanceSelector,
    ServiceCatalogInstanceProvider,
)
"""行为类：必须继承 `BaseFrameworkObject`（框架对象不得是 dataclass）。"""

_EXCEPTIONS = (RpcCallError, RpcRetryBlockedError, RpcTransportError, InstanceUnavailable)
"""协议层异常：必须落在 `BizError` 体系（不新增产品码，统一 code=0）。"""


@pytest.mark.parametrize("cls", _VALUE_OBJECTS)
def test_value_objects_are_frozen_base_value_objects(cls: type) -> None:
    """值对象继承 `BaseValueObject` 且 frozen（与基座第 4 项校验一致）。"""
    assert issubclass(cls, BaseValueObject)
    assert is_dataclass(cls)
    params = cast("Any", cls).__dataclass_params__
    assert params.frozen is True


@pytest.mark.parametrize("cls", _DATA_CONTRACTS)
def test_mutable_states_are_base_data_contracts(cls: type) -> None:
    """可变状态继承 `BaseDataContract`（非 frozen、非框架对象）。"""
    assert issubclass(cls, BaseDataContract)
    assert not issubclass(cls, BaseFrameworkObject)
    assert is_dataclass(cls)


@pytest.mark.parametrize("cls", _FRAMEWORK_OBJECTS)
def test_behavior_classes_are_framework_objects(cls: type) -> None:
    """行为类继承 `BaseFrameworkObject`，且不是 dataclass（基座第 4 项硬规则）。"""
    assert issubclass(cls, BaseFrameworkObject)
    assert not is_dataclass(cls)


@pytest.mark.parametrize("cls", _EXCEPTIONS)
def test_protocol_exceptions_live_in_biz_error_tree(cls: type) -> None:
    """协议层异常继承 `BizError`，同时仍是 `Exception`（捕获语义不变）。"""
    assert issubclass(cls, BizError)
    assert issubclass(cls, Exception)


def test_error_messages_and_codes_survive_biz_error_migration() -> None:
    """归位后 `str()` / `message` / `code` 三件事实保持不变（日志与适配层依赖）。"""
    error = RpcCallError(350004, "预算耗尽", retryable=False, layer="business")
    assert (error.code, error.message, str(error)) == (350004, "预算耗尽", "预算耗尽")
    blocked = RpcRetryBlockedError(error)
    assert blocked.code == 0
    assert blocked.error is error
    unavailable = InstanceUnavailable("空来源", pool_key="msg", reason="empty_snapshot")
    assert (unavailable.pool_key, unavailable.reason) == ("msg", "empty_snapshot")
