"""业务域归属内核（07C `04_03`）：域段解析、本实例承载域、令牌域声明与入站归属判定。

- **域段解析**（`domain_of_path`）：内部路径 `/api/v1/{域段}/...` → 业务域标识；非登记域段返回
  `UNKNOWN_DOMAIN`。日志 / 指标 / 审计的域标签一律经本模块派生（中间件统一注入，业务代码不重复打标）。
- **本实例承载域**（`instance_domains` / `domains_of_units`）：默认拓扑快照 ∩ 本实例承载单元
  （`02_02` 登记的 `[topology].units`）——「本单元启用哪些域」的**唯一来源**：配置只声明单元，
  域由拓扑解析（不另声明域集合，避免两处不一致）。
- **令牌域声明**（`claimed_domains`）：服务 JWT `domains` claim（空格分隔）的解析；签发侧入口为
  `ServiceTokenSpec.domains`（本实例承载域由 `instance_domains()` 派生，非请求参数）。
- **入站归属判定**（`check_domain_attribution`）：第一道——本实例是否启用该域、调用方是否声明该域；
  第二道（能力分配）仍归 `collaboration/grant.py::check_capability_access`。
- **审计域标注**（`domain_of_table`）：表 → 业务域（读表归属登记 `table_record`），审计记录带
  `domain_key`，可按域检索「这个域的写操作都有哪些」。

口径：域标识只在**域登记面**（`deploy/boundaries/domain_layout.json` 的 `domains[]`，装载后经
`domain_service_view()` 暴露）声明；本模块只读，不另建域清单。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import cast

from bms_core.collaboration.grant import capability_domain
from bms_core.collaboration.topology import (
    DEFAULT_TOPOLOGY_TENANT,
    instance_units,
    topology_snapshot,
)
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import PermissionError
from bms_core.core.logging import get_logger
from bms_core.oauth.token import SERVICE_DOMAIN_CLAIM, SERVICE_DOMAIN_SEPARATOR
from bms_core.services.module_registry import domain_service_view
from bms_core.services.table_registry import table_record

__all__ = [
    "DOMAIN_CLAIM",
    "DOMAIN_SEPARATOR",
    "UNKNOWN_DOMAIN",
    "check_domain_attribution",
    "claimed_domains",
    "domain_of_path",
    "domain_of_table",
    "domains_of_units",
    "enabled_domains",
    "instance_domains",
]

DOMAIN_CLAIM = SERVICE_DOMAIN_CLAIM
"""服务 JWT 的业务域声明键（claim 名；值为空格分隔的域标识列表）。"""

DOMAIN_SEPARATOR = SERVICE_DOMAIN_SEPARATOR
"""域声明分隔符（与 `scope` claim 同口径，便于网关与日志侧统一解析）。"""

UNKNOWN_DOMAIN = "unknown"
"""无法归属到业务域的请求 / 记录的域标签（指标与日志统一用它，便于告警与过滤）。"""

_LOGGER = "bms_core.collaboration.domain_scope"
"""日志通道名。"""

_DOMAIN_PATH_RE = re.compile(r"^/api/v1/([a-z][a-z0-9_]*)(?:/|$)")
"""内部接口路径的域段（`/api/v1/{域段}/...`；网关剥离外部命名空间后的形态）。"""


def domain_of_path(path: str) -> str:
    """按内部接口路径取业务域标识（日志 / 指标 / 审计的域标签来源）。

    Args:
        path: 请求路径（内部形态 `/api/v1/{域段}/...`；外部命名空间路径按非域段处理）。

    Returns:
        str: 业务域标识；路径不含已登记域段时返回 `UNKNOWN_DOMAIN`。
    """
    matched = _DOMAIN_PATH_RE.match(path or "")
    if matched is None:
        return UNKNOWN_DOMAIN
    domain = matched.group(1)
    return domain if domain in domain_service_view() else UNKNOWN_DOMAIN


def domains_of_units(units: ConcurrentStableFrozenList[str]) -> ConcurrentStableFrozenList[str]:
    """取给定部署单元集合承载的**已启用**业务域（默认拓扑快照为解析权威）。

    Args:
        units: 部署单元标识集合。

    Returns:
        ConcurrentStableFrozenList[str]: 业务域标识（插入序）；快照未装载或集合为空时为空集。
    """
    snapshot = topology_snapshot(DEFAULT_TOPOLOGY_TENANT)
    if snapshot is None or not units:
        return ConcurrentStableFrozenList[str]()
    domains: ConcurrentStableList[str] = ConcurrentStableList()
    for domain, entry in snapshot.entries.items():
        if not entry.enabled or entry.unit_key not in units:
            continue
        domains.add(domain)
    return ConcurrentStableFrozenList(domains)


def instance_domains() -> ConcurrentStableFrozenList[str]:
    """本实例承载的业务域（本实例承载单元 ∩ 拓扑启用域）。

    配置只声明单元（`[topology].units`），域由拓扑解析——本函数是「本实例启用哪些域」的唯一来源：
    路由生成、令牌 `domains` 声明、审计标注与入站域归属判定都取它。

    Returns:
        ConcurrentStableFrozenList[str]: 业务域标识（插入序）；拓扑未装载时为空集
        （空集表示「无法判定」，入站判定按全启用处理，见 `check_domain_attribution`）。
    """
    return domains_of_units(instance_units())


def enabled_domains() -> ConcurrentStableFrozenList[str]:
    """平台启用的业务域全集（默认拓扑启用域；拓扑未装载时回落域登记面）。

    Args:
        无。

    Returns:
        ConcurrentStableFrozenList[str]: 业务域标识（插入序）。
    """
    snapshot = topology_snapshot(DEFAULT_TOPOLOGY_TENANT)
    if snapshot is None:
        return ConcurrentStableFrozenList(domain_service_view().keys())
    return ConcurrentStableFrozenList(domain for domain, entry in snapshot.entries.items() if entry.enabled)


def claimed_domains(claim: object) -> ConcurrentStableFrozenList[str]:
    """解析服务 JWT 的域声明（空格分隔字符串或序列；去重保序）。

    Args:
        claim: 声明原值（`domains` claim；签发侧写空格分隔字符串）。

    Returns:
        ConcurrentStableFrozenList[str]: 域标识集合；缺失 / 非法形态为空集。
    """
    raw: ConcurrentStableList[object] = ConcurrentStableList()
    if isinstance(claim, str):
        raw.update(claim.split(DOMAIN_SEPARATOR))
    elif isinstance(claim, Sequence) and not isinstance(claim, (str, bytes, bytearray)):
        raw.update(cast("ConcurrentStableList[object]", claim))
    domains: ConcurrentStableList[str] = ConcurrentStableList()
    for item in raw:
        text = str(item).strip()
        if text and text not in domains:
            domains.add(text)
    return ConcurrentStableFrozenList(domains)


def check_domain_attribution(
    capability: str,
    claimed: ConcurrentStableFrozenList[str],
    *,
    consumer: str,
) -> str:
    """入站域归属判定（第一道）：本实例启用该域 + 调用方声明该域。

    能力的提供方域取能力目录登记（`capability_domain`）——与能力分配记录的 provider 维度同源，
    不按能力名的字符串前缀猜。

    Args:
        capability: 端点声明的能力名。
        claimed: 调用方服务 JWT 的域声明（`claimed_domains` 产物）。
        consumer: 调用方服务标识（服务 JWT 签发方）。

    Returns:
        str: 能力所属业务域（判定通过）。

    Raises:
        PermissionError: 本实例不承载该域（未启用）/ 调用方未声明该域 / 声明为空（30001 / 403）。
        CatalogError: 能力未在目录登记（配置漂移，拒启级）。
    """
    domain = capability_domain(capability)
    enabled = instance_domains()
    if enabled and domain not in enabled:
        _warn(
            "domain_not_enabled",
            domain=domain,
            capability=capability,
            consumer=consumer,
        )
        raise PermissionError(
            f"业务域未在本实例启用：{domain}（能力 {capability}；消费方 {consumer}；"
            "请检查 [topology].units 与默认拓扑）"
        )
    if not claimed:
        _warn("domain_claim_missing", domain=domain, capability=capability, consumer=consumer)
        raise PermissionError(
            f"服务身份缺少业务域声明（{DOMAIN_CLAIM}）：{capability}（消费方 {consumer}；"
            "调用方须升级到带域声明的服务令牌签发版本）"
        )
    if domain not in claimed:
        _warn(
            "domain_claim_mismatch",
            domain=domain,
            capability=capability,
            consumer=consumer,
            claimed=list(claimed),
        )
        raise PermissionError(
            f"调用方未声明业务域：{domain}（能力 {capability}；消费方 {consumer}；已声明 {'、'.join(claimed)}）"
        )
    return domain


def domain_of_table(table: str) -> str:
    """表 → 业务域（审计记录的 `domain_key` 来源）。

    Args:
        table: 逻辑表名。

    Returns:
        str: 业务域标识；表未登记归属时返回 `UNKNOWN_DOMAIN`。
    """
    record = table_record(table)
    return record.domain if record is not None and record.domain else UNKNOWN_DOMAIN


def _warn(event: str, **fields: object) -> None:
    """记一条结构化告警（域归属被拒；不含令牌等敏感值）。

    Args:
        event: 事件名。
        **fields: 结构化字段。
    """
    get_logger(_LOGGER).warning(event, **fields)
