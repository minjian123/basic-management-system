"""CI 服务契约校验：路由覆盖 + 不可见白名单 + 响应 schema 完整性。

用法::

    uv run python -m ops.check_contracts                 # 全部启用服务
    uv run python -m ops.check_contracts --service identity

口径（任务 06_01 / 06_03 详细设计 / 需求 06-3 / 06-4 / 《后端开发规范》契约节）：

- **断言 A（覆盖）**：计入契约的实现路由 ⊆ 公开契约 `paths`——防「实现有、契约无」的漏登；
- **断言 B（不可见白名单）**：被排除出契约的实现路由 ⊆ `INVISIBLE_ROUTE_WHITELIST`
  （框架内置文档端点 + `/metrics`）——防业务端点被人为隐藏出契约；
- **断言 C（无空 schema）**：公开契约 `components.schemas` 中不存在空对象条目
  （白名单 `EMPTY_SCHEMA_ALLOWLIST` 缺省空集）——防空 schema 使响应契约失真；
- **断言 D（引用型响应 schema 完整）**：每个操作的 2xx（含 `2XX`）`application/json` schema，
  凡为 `$ref` 引用者必须可解析（可达 `components.schemas` 条目）且非空——防模型派生响应契约
  缺失字段信息（内联 schema 来自未声明响应模型的原始 `Response` 端点，不判定、归后续任务）；
- 实现路由经**内存构建**应用提取（不启 lifespan、不连库），兼容 FastAPI 惰性路由（鸭子类型）；
- 通过退出码 0；违规 / 构建失败 / 未提取到路由退出码 1（明细逐条打印）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.service_contract import (
    empty_schema_entries,
    hidden_route_violations,
    response_schema_gaps,
    route_coverage_gaps,
    service_route_sets,
)
from ops.contract_snapshot import build_app


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(
        description="服务契约校验（实现路由 ⊆ 公开契约 paths + 不可见白名单 + 响应 schema 完整性）"
    )
    parser.add_argument("--service", default="", help="单个服务标识（缺省校验全部启用服务）")
    return parser


def _contract_openapi(app: Any) -> ConcurrentStableDict[str, object]:
    """取公开契约映射（鸭子类型规整为字符串键插入序映射）。

    `openapi()` 产物只需具备 `items()`，兼容内置 dict 与基座集合类（桩应用 / 服务应用均适用）。

    Args:
        app: 服务应用对象。

    Returns:
        ConcurrentStableDict[str, object]: 公开契约映射（无 `openapi()` 产出时为空映射）。
    """
    contract: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    openapi = app.openapi()
    items = getattr(openapi, "items", None)
    if callable(items):
        for key, value in items():
            contract.set(str(key), value)
    return contract


def _contract_paths(contract: ConcurrentStableDict[str, object]) -> ConcurrentStableSet[str]:
    """取公开契约映射的 `paths` 键集合。

    Args:
        contract: 公开契约映射。

    Returns:
        ConcurrentStableSet[str]: 契约路径集合（无 `paths` 段时为空集）。
    """
    paths: ConcurrentStableSet[str] = ConcurrentStableSet()
    raw = contract.get("paths")
    keys = getattr(raw, "keys", None)
    if callable(keys):
        for key in keys():
            paths.add(str(key))
    return paths


def check_service(service_key: str) -> ConcurrentStableList[str]:
    """校验单个服务的路由覆盖、不可见白名单与响应 schema 完整性。

    Args:
        service_key: 服务标识。

    Returns:
        ConcurrentStableList[str]: 违规明细；空列表表示通过。
    """
    try:
        app = build_app(service_key)
    except RuntimeError as exc:
        return ConcurrentStableList([f"{service_key}：应用构建失败（{exc}）"])
    visible, invisible = service_route_sets(app)
    if not visible and not invisible:
        return ConcurrentStableList([f"{service_key}：未提取到任何实现路由（路由结构可能变更，防漏检判失败）"])
    contract = _contract_openapi(app)
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for path in route_coverage_gaps(visible, _contract_paths(contract)):
        errors.add(f"{service_key}：实现路由未进入公开契约 → {path}")
    for path in hidden_route_violations(invisible):
        errors.add(f"{service_key}：实现路由被排除出公开契约且不在白名单 → {path}")
    for name in empty_schema_entries(contract):
        errors.add(f"{service_key}：公开契约存在空 schema 条目 → {name}")
    for gap in response_schema_gaps(contract):
        errors.add(f"{service_key}：成功响应 schema 不可用 → {gap}")
    return errors


def check_all(services: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """逐服务校验路由覆盖。

    Args:
        services: 目标服务集合。

    Returns:
        ConcurrentStableList[str]: 违规明细（聚合）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for service_key in services:
        errors.update(check_service(service_key))
    return errors


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：校验路由覆盖与不可见白名单。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    services: ConcurrentStableList[str] = ConcurrentStableList(enabled_service_keys())
    if args.service:
        services = ConcurrentStableList([cast("str", args.service)])
    errors = check_all(services)
    if errors:
        for error in errors:
            print(f"[契约] {error}")
        print(f"[契约] 校验失败（{len(errors)} 项）")
        return 1
    print(
        f"[契约] 校验通过（{len(services)} 个服务：实现路由全部进入契约，不可见路由均在白名单，"
        "公开契约无空 schema 且引用型响应 schema 均可解析）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
