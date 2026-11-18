"""事件消费组声明的运维读取（CLI / 主题供给共用，不引入第二套声明来源）。

声明一律取目标服务应用工厂的 `event_consumer_records()`，与进程内宿主同源；
本模块只做「动态导入服务包 → 取工厂 → 合并 → 校验」，不做装配。
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from importlib import import_module
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.events.consumer_records import (
    EventConsumerRecord,
    merge_event_consumer_records,
    validate_event_consumer_records,
)
from bms_core.events.platform_events import register_platform_event_contracts

__all__ = ["load_records", "service_factory"]


def service_factory(service: str) -> object:
    """按服务键取应用工厂实例（零参构造）。

    Args:
        service: 服务键（如 `platform`）。

    Returns:
        object: `ApplicationFactory` 实例。

    Raises:
        SystemExit: 服务包不存在或未声明工厂（退出码 2）。
    """
    module_name = f"bms_{service}.main"
    try:
        module = import_module(module_name)
    except ImportError as exc:
        print(f"服务包不存在：{module_name}（{exc}）", file=sys.stderr)
        raise SystemExit(2) from exc
    factory_type = getattr(module, "ApplicationFactory", None)
    if factory_type is None:
        print(f"服务包未声明 ApplicationFactory：{module_name}", file=sys.stderr)
        raise SystemExit(2)
    return cast("object", factory_type())


def load_records(factory: object, *, group_prefix: str) -> ConcurrentStableList[EventConsumerRecord]:
    """取并校验服务自持的消费组声明。

    Args:
        factory: 应用工厂实例。
        group_prefix: 组名前缀。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 合并后的声明。

    Raises:
        SystemExit: 声明校验不通过（退出码 1）。
    """
    getter = getattr(factory, "event_consumer_records", None)
    declared: ConcurrentStableList[EventConsumerRecord] = (
        ConcurrentStableList(cast("Iterable[EventConsumerRecord]", getter()))
        if callable(getter)
        else ConcurrentStableList()
    )
    records = merge_event_consumer_records(declared, group_prefix=group_prefix)
    # 运维命令不经应用启动：平台事件契约在此幂等登记，保证声明校验同启动口径
    register_platform_event_contracts()
    errors = validate_event_consumer_records(records)
    if errors:
        for error in errors:
            print(f"[声明校验] {error}", file=sys.stderr)
        raise SystemExit(1)
    return records
