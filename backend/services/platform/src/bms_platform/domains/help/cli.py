"""帮助包命令行实现：`load` / `unload` / `checksum`（08_03）。

- 装载与卸载**默认 dry-run**，`--apply` 才写库；目标必须显式 `--tenant` 或 `--all-tenants`；
- 装载前从平台库归集锚点清单，逐租户调用 `HelpPackageService`；
- 退出码：0 成功 / 1 校验或业务拒收 / 2 执行错误 / 64 参数错误；
- 命令行无请求上下文：只记结构化日志与包登记行，操作日志与字段级审计归 12_01。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import NoReturn

from sqlalchemy.exc import SQLAlchemyError

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import BizError
from bms_core.core.logging import get_logger
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_SERVICE_KEY, build_platform_db_key, build_tenant_db_key
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.help.anchors import HelpAnchorKind
from bms_core.repositories.help_anchor import list_help_anchors
from bms_core.tenant.registry import TenantRef, tenant_refs
from bms_platform.domains.help.constants import DEFAULT_STRICT
from bms_platform.domains.help.package_spec import (
    HelpPackageSpec,
    compute_checksum,
    load_package,
    write_checksum,
)
from bms_platform.domains.help.services.package import (
    HelpLoadCounts,
    HelpLoadOutcome,
    HelpPackageService,
    HelpUnloadCounts,
    HelpUnloadOutcome,
)

__all__ = ["build_parser", "main"]

_LOGGER = get_logger("bms.help")

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_FAILED = 2
_EXIT_USAGE = 64

_PRODUCT_KEY_HELP = "产品键（platform / 各产品仓产品键）"


class _Parser(argparse.ArgumentParser):
    """参数解析器：用法错误统一退出码 64（与既有 ops 通道口径一致）。"""

    def error(self, message: str) -> NoReturn:
        """输出用法并退出 64。

        Args:
            message: 错误信息。

        Raises:
            SystemExit: 固定退出码 64。
        """
        self.print_usage(sys.stderr)
        raise SystemExit(_EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = _Parser(prog="ops.help_package", description="产品帮助包装载 / 卸载 / 校验和")
    sub = parser.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load", help="装载或升级帮助包（默认 dry-run）")
    load.add_argument("--package", required=True, help="包目录或 package.yaml 路径")
    _add_target_options(load)
    load.add_argument("--apply", action="store_true", help="实际写库（缺省只预演）")
    load.add_argument(
        "--lenient",
        action="store_true",
        help=f"跳过无效文章并告警（缺省{'严格' if DEFAULT_STRICT else '宽松'}）",
    )
    load.add_argument("--json", action="store_true", help="输出 JSON")

    unload = sub.add_parser("unload", help="卸载产品帮助包（默认 dry-run）")
    unload.add_argument("--product", required=True, help=_PRODUCT_KEY_HELP)
    _add_target_options(unload)
    unload.add_argument("--apply", action="store_true", help="实际写库（缺省只预演）")
    unload.add_argument("--json", action="store_true", help="输出 JSON")

    checksum = sub.add_parser("checksum", help="计算 / 回写包校验和")
    checksum.add_argument("--package", required=True, help="包目录或 package.yaml 路径")
    checksum.add_argument("--write", action="store_true", help="回写 package.yaml 的 checksum 行")
    return parser


def _add_target_options(parser: argparse.ArgumentParser) -> None:
    """给 load / unload 加租户目标参数。

    Args:
        parser: 子命令解析器。
    """
    parser.add_argument("--tenant", action="append", default=[], help="租户编码（可重复）")
    parser.add_argument("--all-tenants", action="store_true", help="对所有未软删租户执行")


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（None 取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "checksum":
            return _run_checksum(args)
        return asyncio.run(_run_lifecycle(args))
    except BizError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return _EXIT_REFUSED
    except (SQLAlchemyError, OSError) as exc:
        _LOGGER.error("help_package_command_failed", command=args.command, error=str(exc))
        print(f"执行错误：{exc}", file=sys.stderr)
        return _EXIT_FAILED


def _run_checksum(args: argparse.Namespace) -> int:
    """执行 checksum 子命令。

    Args:
        args: 解析结果。

    Returns:
        int: 退出码。
    """
    if args.write:
        checksum = write_checksum(args.package)
        print(f"checksum: {checksum}（已回写 package.yaml）")
    else:
        print(compute_checksum(args.package))
    return _EXIT_OK


async def _run_lifecycle(args: argparse.Namespace) -> int:
    """执行 load / unload 子命令（多租户编排）。

    Args:
        args: 解析结果。

    Returns:
        int: 退出码。
    """
    _require_target(args)
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    registry = EngineRegistry(factory)
    if args.command == "load":
        return await _run_load(args, registry, factory)
    return await _run_unload(args, registry, factory)


def _require_target(args: argparse.Namespace) -> None:
    """校验租户目标参数（必须二选一）。

    Args:
        args: 解析结果。

    Raises:
        SystemExit: 参数错误（64）。
    """
    if bool(args.tenant) == bool(args.all_tenants):
        build_parser().error("必须且只能指定 --tenant 或 --all-tenants 之一")


async def _run_load(args: argparse.Namespace, registry: EngineRegistry, factory: EngineFactory) -> int:
    """装载编排。

    Args:
        args: 解析结果。
        registry: 引擎注册表。
        factory: 引擎工厂（解析租户注册库地址）。

    Returns:
        int: 退出码。
    """
    spec = load_package(args.package, lenient=args.lenient)
    anchors = await _load_anchors(registry)
    tenants = await _resolve_tenants(factory, ConcurrentStableList(args.tenant), args.all_tenants)
    results: ConcurrentStableList[tuple[str, HelpLoadOutcome]] = ConcurrentStableList()
    refused = False
    failed = False
    for ref in tenants:
        db_key = build_tenant_db_key(ref.db_basis, service=PLATFORM_SERVICE_KEY)
        try:
            outcome = await _load_for_tenant(
                registry,
                db_key,
                spec,
                anchors=anchors,
                apply=args.apply,
                lenient=args.lenient,
            )
        except BizError as exc:
            refused = True
            results.add((ref.code, _failed_load(str(exc))))
            continue
        except (SQLAlchemyError, OSError) as exc:
            failed = True
            _LOGGER.error("help_package_tenant_failed", tenant=ref.code, error=str(exc))
            results.add((ref.code, _failed_load(f"执行错误：{exc}")))
            continue
        results.add((ref.code, outcome))

    if args.json:
        print(json.dumps(_load_json(results), ensure_ascii=False, indent=2))
    else:
        _print_load(results, spec=spec, applied=args.apply)
    return _exit_code(refused=refused, failed=failed)


async def _run_unload(args: argparse.Namespace, registry: EngineRegistry, factory: EngineFactory) -> int:
    """卸载编排。

    Args:
        args: 解析结果。
        registry: 引擎注册表。
        factory: 引擎工厂（解析租户注册库地址）。

    Returns:
        int: 退出码。
    """
    tenants = await _resolve_tenants(factory, ConcurrentStableList(args.tenant), args.all_tenants)
    results: ConcurrentStableList[tuple[str, HelpUnloadOutcome]] = ConcurrentStableList()
    refused = False
    failed = False
    for ref in tenants:
        db_key = build_tenant_db_key(ref.db_basis, service=PLATFORM_SERVICE_KEY)
        try:
            outcome = await _unload_for_tenant(registry, db_key, args.product, apply=args.apply)
        except BizError as exc:
            refused = True
            results.add((ref.code, _failed_unload(str(exc))))
            continue
        except (SQLAlchemyError, OSError) as exc:
            failed = True
            _LOGGER.error("help_unload_tenant_failed", tenant=ref.code, error=str(exc))
            results.add((ref.code, _failed_unload(f"执行错误：{exc}")))
            continue
        results.add((ref.code, outcome))

    if args.json:
        print(json.dumps(_unload_json(results), ensure_ascii=False, indent=2))
    else:
        _print_unload(results, product=args.product, applied=args.apply)
    return _exit_code(refused=refused, failed=failed)


async def _load_for_tenant(
    registry: EngineRegistry,
    db_key: str,
    spec: HelpPackageSpec,
    *,
    anchors: ConcurrentStableDict[str, HelpAnchorKind],
    apply: bool,
    lenient: bool,
) -> HelpLoadOutcome:
    """在单个租户库执行装载。

    Args:
        registry: 引擎注册表。
        db_key: 租户库键。
        spec: 包规格。
        anchors: 锚点清单。
        apply: 是否写库。
        lenient: 是否跳过无效文章。

    Returns:
        HelpLoadOutcome: 结果。
    """
    if apply:
        async with session_scope(registry, db_key=db_key) as session, session.begin():
            return await HelpPackageService(session).load(spec, anchors=anchors, apply=True, lenient=lenient)
    async with session_scope(registry, db_key=db_key, read_only=True) as session:
        return await HelpPackageService(session).load(spec, anchors=anchors, apply=False, lenient=lenient)


async def _unload_for_tenant(
    registry: EngineRegistry, db_key: str, product_key: str, *, apply: bool
) -> HelpUnloadOutcome:
    """在单个租户库执行卸载。

    Args:
        registry: 引擎注册表。
        db_key: 租户库键。
        product_key: 产品键。
        apply: 是否写库。

    Returns:
        HelpUnloadOutcome: 结果。
    """
    if apply:
        async with session_scope(registry, db_key=db_key) as session, session.begin():
            return await HelpPackageService(session).unload(product_key, apply=True)
    async with session_scope(registry, db_key=db_key, read_only=True) as session:
        return await HelpPackageService(session).unload(product_key, apply=False)


async def _load_anchors(registry: EngineRegistry) -> ConcurrentStableDict[str, HelpAnchorKind]:
    """从平台库归集锚点清单。

    Args:
        registry: 引擎注册表。

    Returns:
        ConcurrentStableDict[str, HelpAnchorKind]: `help_key` → 节点类型。
    """
    db_key = build_platform_db_key(PLATFORM_SERVICE_KEY)
    async with session_scope(registry, db_key=db_key, read_only=True) as session:
        entries = await list_help_anchors(session)
    anchors: ConcurrentStableDict[str, HelpAnchorKind] = ConcurrentStableDict()
    for entry in entries:
        anchors.set(entry.help_key, entry.kind)
    return anchors


async def _resolve_tenants(
    factory: EngineFactory,
    codes: ConcurrentStableList[str],
    all_tenants: bool,
) -> ConcurrentStableList[TenantRef]:
    """解析目标租户（显式编码或全部未软删租户）。

    Args:
        factory: 引擎工厂（解析租户注册库地址）。
        codes: 显式租户编码。
        all_tenants: 是否全部租户。

    Returns:
        ConcurrentStableList[TenantRef]: 租户引用。
    """
    registry_key = build_platform_db_key(TENANT_SERVICE_KEY)
    url = factory.resolved_url(registry_key)
    refs = await tenant_refs(url)
    if all_tenants:
        return refs
    by_code: ConcurrentStableDict[str, TenantRef] = ConcurrentStableDict((ref.code, ref) for ref in refs)
    return ConcurrentStableList(by_code.get(code) or TenantRef(code=code, db_basis=code) for code in codes)


def _exit_code(*, refused: bool, failed: bool) -> int:
    """按失败类型取退出码。

    Args:
        refused: 是否有业务拒收。
        failed: 是否有执行错误。

    Returns:
        int: 退出码。
    """
    if failed:
        return _EXIT_FAILED
    if refused:
        return _EXIT_REFUSED
    return _EXIT_OK


def _failed_load(message: str) -> HelpLoadOutcome:
    """构造失败占位结果（用于汇总打印）。

    Args:
        message: 错误信息。

    Returns:
        HelpLoadOutcome: 占位结果（计数全 0，warning 携带错误）。
    """
    return HelpLoadOutcome(
        counts=HelpLoadCounts(),
        package_action="failed",
        warnings=ConcurrentStableFrozenList((message,)),
        applied=False,
    )


def _failed_unload(message: str) -> HelpUnloadOutcome:
    """构造卸载失败占位结果。

    Args:
        message: 错误信息。

    Returns:
        HelpUnloadOutcome: 占位结果。
    """
    return HelpUnloadOutcome(counts=HelpUnloadCounts(), applied=False)


def _print_load(
    results: ConcurrentStableList[tuple[str, HelpLoadOutcome]],
    *,
    spec: HelpPackageSpec,
    applied: bool,
) -> None:
    """打印装载结果。

    Args:
        results: 逐租户结果。
        spec: 包规格。
        applied: 是否实跑。
    """
    mode = "执行" if applied else "预演（未写入）"
    print(f"[{mode}] 产品 {spec.product_key} {spec.package_version}（{spec.declared_article_count} 篇）")
    for tenant, outcome in results:
        counts = outcome.counts
        print(f"- 租户 {tenant}：包状态 {outcome.package_action}")
        print(
            f"  文章：新增 {counts.articles_new} / 更新 {counts.articles_updated} / "
            f"下线 {counts.articles_offline} / 跳过 {counts.articles_skipped}"
            f"（本地覆盖 {counts.articles_skipped_override}、目标冲突 {counts.articles_skipped_conflict}）"
            f" / 不变 {counts.articles_unchanged}"
        )
        print(
            f"  分类：新增 {counts.categories_created} / 更新 {counts.categories_updated}"
            f" / 不变 {counts.categories_unchanged}"
        )
        for warning in outcome.warnings:
            print(f"  告警：{warning}")


def _print_unload(results: ConcurrentStableList[tuple[str, HelpUnloadOutcome]], *, product: str, applied: bool) -> None:
    """打印卸载结果。

    Args:
        results: 逐租户结果。
        product: 产品键。
        applied: 是否实跑。
    """
    mode = "执行" if applied else "预演（未写入）"
    print(f"[{mode}] 卸载产品 {product}")
    for tenant, outcome in results:
        counts = outcome.counts
        print(
            f"- 租户 {tenant}：下线文章 {counts.articles_offline} / 不变 {counts.articles_unchanged}"
            f" / 包行 {counts.packages_unloaded}"
        )


def _load_json(results: ConcurrentStableList[tuple[str, HelpLoadOutcome]]) -> object:
    """装载结果转 JSON 结构。

    Args:
        results: 逐租户结果。

    Returns:
        object: JSON 可序列化结构。
    """
    payload: ConcurrentStableList[object] = ConcurrentStableList()
    for tenant, outcome in results:
        counts = outcome.counts
        payload.add(
            {
                "tenant": tenant,
                "package_action": outcome.package_action,
                "applied": outcome.applied,
                "counts": {
                    "articles_new": counts.articles_new,
                    "articles_updated": counts.articles_updated,
                    "articles_offline": counts.articles_offline,
                    "articles_skipped": counts.articles_skipped,
                    "articles_skipped_override": counts.articles_skipped_override,
                    "articles_skipped_conflict": counts.articles_skipped_conflict,
                    "articles_unchanged": counts.articles_unchanged,
                    "categories_created": counts.categories_created,
                    "categories_updated": counts.categories_updated,
                    "categories_unchanged": counts.categories_unchanged,
                },
                "warnings": list(outcome.warnings),
            }
        )
    return list(payload)


def _unload_json(results: ConcurrentStableList[tuple[str, HelpUnloadOutcome]]) -> object:
    """卸载结果转 JSON 结构。

    Args:
        results: 逐租户结果。

    Returns:
        object: JSON 可序列化结构。
    """
    payload: ConcurrentStableList[object] = ConcurrentStableList()
    for tenant, outcome in results:
        counts = outcome.counts
        payload.add(
            {
                "tenant": tenant,
                "applied": outcome.applied,
                "counts": {
                    "articles_offline": counts.articles_offline,
                    "articles_unchanged": counts.articles_unchanged,
                    "packages_unloaded": counts.packages_unloaded,
                },
            }
        )
    return list(payload)
