"""事件主题供给：按已登记事件契约与租户幂等创建 msg 主题（运维通道）。

用法::

    # 幂等创建 / 扩容（默认；审计三主题 4 分区，其余 1 分区）
    uv run python -m ops.event_topics

    # 只校验存在性、分区数与同组主题分区数一致性
    uv run python -m ops.event_topics --check

    # 只处理指定租户 / 只看计划
    uv run python -m ops.event_topics --tenant demo --tenant acme
    uv run python -m ops.event_topics --dry-run

口径：

- 命名空间取**事件类型首段（事件域）**，主题取 `topic_for`（`bms-{域}-{对象}`）；
- 主题身份 `(租户, 命名空间, 主题名)`，故按租户逐个创建；
- 命名空间未对租户启用（`350010`）跳过并告警（模块未开通，本就不该有事件）；
- 分区数只增不减；同组各主题分区数必须一致（否则多实例下同租户可能分到不同进程）；
- 管理端点当前无用户态时走平台层豁免，依赖内网隔离；请在生产网络内执行。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import cast

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.objects import BaseValueObject
from bms_core.core.service_endpoints import normalize_service_endpoints
from bms_core.events.contracts import default_event_contract_registry
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.events.topic import namespace_for, topic_for
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE, SERVICE_CLIENT_OPTION_BASE_URL
from ops._event_records import load_records, service_factory

__all__ = ["main"]

_AUDIT_TOPICS: ConcurrentStableList[str] = ConcurrentStableList(("bms-sys-operation", "bms-sys-login", "bms-sys-data"))
"""审计链三主题（同一组跨主题串行，分区数必须一致）。"""

_TOPIC_EXISTS = 350008
_NAMESPACE_INVALID = 350010
_TENANT_NOT_FOUND = 350012
_PARTITION_INVALID = 350009

_DEFAULT_AUDIT_PARTITIONS = 4
_DEFAULT_PARTITIONS = 1


@dataclass(frozen=True)
class _TopicSpec(BaseValueObject):
    """一个待供给的主题（命名空间 + 主题名 + 派生来源事件）。"""

    namespace: str
    topic: str
    event_types: ConcurrentStableList[str]


def _topic_specs() -> ConcurrentStableList[_TopicSpec]:
    """按已登记事件契约派生主题清单（同主题多事件合并）。

    Returns:
        ConcurrentStableList[_TopicSpec]: 主题清单（按命名空间 / 主题名排序）。
    """
    register_platform_event_contracts()
    grouped: ConcurrentStableDict[tuple[str, str], ConcurrentStableList[str]] = ConcurrentStableDict()
    for contract in default_event_contract_registry().contracts():
        key = (namespace_for(contract.event_type), topic_for(contract.event_type))
        events = grouped.get(key)
        if events is None:
            events = ConcurrentStableList[str]()
            grouped.set(key, events)
        events.add(contract.event_type)
    specs: ConcurrentStableList[_TopicSpec] = ConcurrentStableList()
    for key in sorted(grouped.keys()):
        specs.add(_TopicSpec(namespace=key[0], topic=key[1], event_types=grouped[key]))
    return specs


def _partitions_for(topic: str, *, audit: int, default: int) -> int:
    """取主题目标分区数（审计三主题用审计值，其余用默认值）。

    Args:
        topic: 主题名。
        audit: 审计主题分区数。
        default: 其余主题分区数。

    Returns:
        int: 目标分区数。
    """
    return audit if topic in _AUDIT_TOPICS else default


def _tenant_base_url(settings: Settings) -> str:
    """解析租户服务基址（端点覆盖 → 基址模板）。

    Args:
        settings: 应用配置。

    Returns:
        str: 基址（无尾斜线）。
    """
    endpoints = normalize_service_endpoints(settings.service_client.endpoints)
    explicit = endpoints.get("tenant")
    if explicit:
        return explicit.rstrip("/")
    template = str(settings.service_client.options.get(SERVICE_CLIENT_OPTION_BASE_URL) or DEFAULT_BASE_URL_TEMPLATE)
    return template.replace("{service}", "tenant").rstrip("/")


def _active_tenants(client: httpx.Client, settings: Settings) -> ConcurrentStableList[str]:
    """取启用租户编码（租户注册只读契约）。

    Args:
        client: HTTP 客户端。
        settings: 应用配置。

    Returns:
        ConcurrentStableList[str]: 租户编码（主键升序由服务端保证）。

    Raises:
        SystemExit: 契约不可达或响应非法（退出码 1）。
    """
    url = f"{_tenant_base_url(settings)}/api/v1/tenant-registry/active"
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        print(f"租户清单不可达：{url}（{exc}）", file=sys.stderr)
        raise SystemExit(1) from exc
    if response.status_code != 200:
        print(f"租户清单调用失败：HTTP {response.status_code}", file=sys.stderr)
        raise SystemExit(1)
    try:
        body = cast("dict[str, object]", response.json())
    except ValueError as exc:
        print("租户清单响应不是合法 JSON", file=sys.stderr)
        raise SystemExit(1) from exc
    data = body.get("data")
    raw_items: object = cast("dict[str, object]", data).get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        print("租户清单响应缺少 data.items", file=sys.stderr)
        raise SystemExit(1)
    codes: ConcurrentStableList[str] = ConcurrentStableList()
    for item in cast("list[object]", raw_items):
        if isinstance(item, dict):
            mapping = cast("dict[str, object]", item)
            code = mapping.get("code")
            if isinstance(code, str):
                codes.add(code)
    return codes


def _request(
    client: httpx.Client, method: str, url: str, tenant: str, payload: ConcurrentStableDict[str, object] | None
) -> tuple[int, ConcurrentStableDict[str, object]]:
    """发一次 msg 管理请求并解析统一响应。

    Args:
        client: HTTP 客户端。
        method: HTTP 方法。
        url: 完整地址。
        tenant: 租户编码（`X-Tenant-ID`）。
        payload: 请求体（GET 时为 None）。

    Returns:
        tuple[int, ConcurrentStableDict[str, object]]: HTTP 状态与响应体。

    Raises:
        SystemExit: 网络失败或响应非法（退出码 1）。
    """
    try:
        response = client.request(
            method,
            url,
            json=None if payload is None else dict(payload),
            headers={"X-Tenant-ID": tenant},
        )
    except httpx.HTTPError as exc:
        print(f"msg 管理端点不可达：{url}（{exc}）", file=sys.stderr)
        raise SystemExit(1) from exc
    try:
        body = response.json()
    except ValueError as exc:
        print(f"msg 管理端点响应不是 JSON：{url}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not isinstance(body, dict):
        print(f"msg 管理端点响应不是对象：{url}", file=sys.stderr)
        raise SystemExit(1)
    return response.status_code, ConcurrentStableDict(cast("dict[str, object]", body))


def _find_topic(
    client: httpx.Client, base: str, tenant: str, namespace: str, topic: str
) -> ConcurrentStableDict[str, object] | None:
    """按命名空间 + 主题名查已有主题。

    Args:
        client: HTTP 客户端。
        base: msg 基址。
        tenant: 租户编码。
        namespace: 命名空间。
        topic: 主题名。

    Returns:
        ConcurrentStableDict[str, object] | None: 主题行；不存在返回 None。
    """
    url = f"{base}/api/v1/msg/admin/topics?namespace={namespace}&keyword={topic}&page=1&size=50"
    status, body = _request(client, "GET", url, tenant, None)
    if status != 200:
        return None
    data = body.get("data")
    raw_items: object = cast("dict[str, object]", data).get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return None
    for item in cast("list[object]", raw_items):
        if not isinstance(item, dict):
            continue
        mapping = cast("dict[str, object]", item)
        if mapping.get("name") == topic:
            return ConcurrentStableDict(mapping)
    return None


def _ensure_topic(
    client: httpx.Client,
    base: str,
    tenant: str,
    spec: _TopicSpec,
    partitions: int,
    *,
    dry_run: bool,
) -> str:
    """幂等创建 / 扩容一个主题。

    Args:
        client: HTTP 客户端。
        base: msg 基址。
        tenant: 租户编码。
        spec: 主题规格。
        partitions: 目标分区数。
        dry_run: 只打印不执行。

    Returns:
        str: 结果（`created` / `exists` / `expanded` / `larger` / `namespace-disabled` / `tenant-missing`）。
    """
    if dry_run:
        print(f"[计划] {tenant} {spec.namespace}/{spec.topic} 分区 {partitions}")
        return "planned"
    status, body = _request(
        client,
        "POST",
        f"{base}/api/v1/msg/admin/topics",
        tenant,
        ConcurrentStableDict({"namespace": spec.namespace, "name": spec.topic, "partition_count": partitions}),
    )
    code = body.get("code")
    if code == 0:
        print(f"[创建] {tenant} {spec.namespace}/{spec.topic} 分区 {partitions}")
        return "created"
    if code == _NAMESPACE_INVALID:
        print(f"[跳过] {tenant} 命名空间未启用：{spec.namespace}（{spec.topic}）")
        return "namespace-disabled"
    if code == _TENANT_NOT_FOUND:
        print(f"[跳过] {tenant} 租户不存在（清单可能过期）")
        return "tenant-missing"
    if code != _TOPIC_EXISTS:
        print(f"[失败] {tenant} {spec.namespace}/{spec.topic}：HTTP {status} code={code} {body.get('message')}")
        return "failed"
    existing = _find_topic(client, base, tenant, spec.namespace, spec.topic)
    if existing is None:
        print(f"[失败] {tenant} {spec.namespace}/{spec.topic}：已存在但查询不到")
        return "failed"
    current = existing.get("partition_count")
    current_count = current if isinstance(current, int) else 0
    if current_count < partitions:
        status, body = _request(
            client,
            "POST",
            f"{base}/api/v1/msg/admin/topics/{existing.get('id')}/partitions",
            tenant,
            ConcurrentStableDict({"partition_count": partitions}),
        )
        if body.get("code") == 0:
            print(f"[扩容] {tenant} {spec.namespace}/{spec.topic}：{current_count} → {partitions}")
            return "expanded"
        if body.get("code") == _PARTITION_INVALID:
            print(f"[跳过] {tenant} {spec.namespace}/{spec.topic}：分区数非法")
            return "failed"
        print(f"[失败] {tenant} {spec.namespace}/{spec.topic}：扩分区 HTTP {status} code={body.get('code')}")
        return "failed"
    if current_count > partitions:
        print(
            f"[提示] {tenant} {spec.namespace}/{spec.topic}：现有分区 {current_count} 大于目标 "
            f"{partitions}（只增不减，保持现状）"
        )
        return "larger"
    print(f"[存在] {tenant} {spec.namespace}/{spec.topic} 分区 {current_count}")
    return "exists"


def _group_topics(service: str, *, group_prefix: str) -> ConcurrentStableDict[str, ConcurrentStableList[str]]:
    """取服务声明的组 → 主题映射（同组分区数一致性校验用）。

    Args:
        service: 服务键。
        group_prefix: 组名前缀。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableList[str]]: 组名 → 主题清单。
    """
    records = load_records(service_factory(service), group_prefix=group_prefix)
    groups: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
    for record in records:
        topic = topic_for(record.event_type)
        topics = groups.get(record.consumer)
        if topics is None:
            topics = ConcurrentStableList[str]()
            groups.set(record.consumer, topics)
        if topic not in topics:
            topics.add(topic)
    return groups


def _check(
    client: httpx.Client,
    base: str,
    specs: ConcurrentStableList[_TopicSpec],
    tenants: ConcurrentStableList[str],
    *,
    audit: int,
    default: int,
    groups: ConcurrentStableDict[str, ConcurrentStableList[str]],
) -> int:
    """只读校验：存在性、分区数、同组主题分区数一致性。

    Returns:
        int: 退出码（0 通过 / 1 有缺口）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for tenant in tenants:
        counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for spec in specs:
            target = _partitions_for(spec.topic, audit=audit, default=default)
            existing = _find_topic(client, base, tenant, spec.namespace, spec.topic)
            if existing is None:
                errors.add(f"{tenant} {spec.namespace}/{spec.topic}：主题不存在")
                continue
            raw = existing.get("partition_count")
            current = raw if isinstance(raw, int) else 0
            counts.set(spec.topic, current)
            if current < target:
                errors.add(f"{tenant} {spec.namespace}/{spec.topic}：分区 {current} < 目标 {target}")
        for group, topics in groups.items():
            values: ConcurrentStableList[int] = ConcurrentStableList()
            for topic in topics:
                value = counts.get(topic)
                if value is not None:
                    values.add(value)
            if len(values) > 1:
                errors.add(f"{tenant} 组 {group} 的主题分区数不一致：{list(topics)} → {list(values)}")
    if errors:
        for error in errors:
            print(f"[缺口] {error}", file=sys.stderr)
        return 1
    print(f"主题校验通过：{len(tenants)} 个租户 × {len(specs)} 个主题")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 sys.argv）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="ops.event_topics", description="事件主题幂等供给 / 校验")
    parser.add_argument("--check", action="store_true", help="只校验，不创建")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不发请求")
    parser.add_argument("--tenant", action="append", default=None, help="只处理指定租户（可重复）")
    parser.add_argument(
        "--partitions-audit", type=int, default=_DEFAULT_AUDIT_PARTITIONS, help="审计三主题分区数（默认 4）"
    )
    parser.add_argument("--partitions-default", type=int, default=_DEFAULT_PARTITIONS, help="其余主题分区数（默认 1）")
    parser.add_argument("--service", default="platform", help="读取哪个服务的消费组声明（亲和校验用，默认 platform）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    settings = get_settings()
    base = _msg_base(settings)
    specs = _topic_specs()
    with httpx.Client(timeout=5.0) as client:
        tenants = (
            ConcurrentStableList(cast("list[str]", args.tenant)) if args.tenant else _active_tenants(client, settings)
        )
        if not tenants:
            print("没有可处理的租户")
            return 0
        groups = _group_topics(args.service, group_prefix=settings.event_consumer.group_prefix)
        if args.check:
            return _check(
                client,
                base,
                specs,
                tenants,
                audit=args.partitions_audit,
                default=args.partitions_default,
                groups=groups,
            )
        failures = 0
        for tenant in tenants:
            for spec in specs:
                result = _ensure_topic(
                    client,
                    base,
                    tenant,
                    spec,
                    _partitions_for(spec.topic, audit=args.partitions_audit, default=args.partitions_default),
                    dry_run=args.dry_run,
                )
                if result == "failed":
                    failures += 1
    return 1 if failures else 0


def _msg_base(settings: Settings) -> str:
    """解析 msg 基址（与发布器同源）。

    Args:
        settings: 应用配置。

    Returns:
        str: 基址（无尾斜线）。
    """
    from bms_core.core.assembly import msg_base_url

    return msg_base_url(settings).rstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
