"""平台自身声明的注册装配（07B `02_06`）：启动钩子。

- **何时执行**：platform 服务启动钩子——早于「能力使用声明校验」与「授权基线同步」，
  因为声明是它们的前置（视图与授权都从注册表派生）；
- **注册内容**：平台自身八类声明 = `SERVICE_CATALOG`（服务行常量）+ 本仓 `deploy/registry/platform.toml`
  （产品档案 / 产品路由 / 数据源 / 能力 / 种子 / 错误码 / 使用声明）；**不读别的产品仓文件**；
- **落库 + 投影**：走与产品上报同一条 `DeclarationRegistryService.register()`（同一套校验与对账），
  落库后按注册表快照重建进程内视图；
- **失败语义**：校验 / 冲突 / 撞键一律**拒启**；库不可用（未初始化）降级放行并打标记——
  与 `02_04` 的授权同步同口径（取用路径仍 fail-closed）。
"""

from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.registry.declarations import DeclarationPayload, from_manifest
from bms_core.registry.products import load_product_manifest, local_manifest_paths
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord
from bms_platform.domains.platform_registry.services.declaration_registry import DeclarationRegistryService

__all__ = ["bootstrap_platform_declarations"]

_LOGGER = get_logger("bms.platform.declaration")


def _platform_manifest_path(service_key: str) -> Path:
    """定位平台自身清单（本仓 `deploy/registry/<服务键>.toml`）。

    Args:
        service_key: 本服务标识（`[app].service`）。

    Returns:
        Path: 平台清单路径。

    Raises:
        CatalogError: 本仓清单缺失（平台自身声明无处可读，拒绝启动）。
    """
    for path in local_manifest_paths():
        if path.name == f"{service_key}.toml":
            return path
    raise CatalogError(f"平台自身声明缺失：deploy/registry/{service_key}.toml（本仓清单未发现）")


async def bootstrap_platform_declarations(app: FastAPI) -> None:
    """启动钩子：注册平台自身八类声明并重建权威视图。

    Args:
        app: 应用实例（取配置 / 引擎注册表 / 会话工厂）。

    Raises:
        CatalogError: 声明校验不过、跨产品撞键或落库失败（拒启）。
    """
    settings = app.state.settings
    if not settings.registry.register_on_startup:
        # 单测 / 单仓自检：由用例显式调注册端点，避免启动期按「声明即全量」退役夹具行
        _LOGGER.info("declaration_register_skipped", reason="registry.register_on_startup=false")
        return
    service_key = str(settings.app.service or "platform")
    manifest_path = _platform_manifest_path(service_key)
    manifest = load_product_manifest(manifest_path)
    payload = from_manifest(manifest)
    if payload.product_key != service_key:
        raise CatalogError(f"平台清单归属与服务标识不一致：清单 {payload.product_key}，服务 {service_key}")
    payload = with_platform_services(payload)
    try:
        async with session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session:
            report = await DeclarationRegistryService(session).register(payload)
            # 事务边界归调用方（`session_scope` 只建会话）：不 commit 则本次注册随会话释放回滚，
            # 表现为「日志显示注册成功、库里查不到行」，并让后续产品进程经 HTTP 拉取时对账全红。
            await session.commit()
    except SQLAlchemyError as exc:
        # 库未初始化：与「授权声明同步」同口径降级放行（记 WARNING + 打标记），取用仍 fail-closed
        _LOGGER.warning("declaration_register_unavailable", error=type(exc).__name__, detail=str(exc))
        app.state.declaration_register_degraded = True
        return
    except CatalogError:
        raise
    except Exception as exc:
        raise CatalogError(f"平台声明注册失败：{type(exc).__name__}: {exc}") from exc
    _LOGGER.info(
        "declaration_registered",
        product_key=report.product_key,
        created=dict(report.created),
        updated=dict(report.updated),
        retired=dict(report.retired),
    )
    for message in report.warnings:
        _LOGGER.warning("declaration_register_warning", detail=message)


def with_platform_services(payload: DeclarationPayload) -> DeclarationPayload:
    """把平台自身服务行（`SERVICE_CATALOG` 常量）并入注册载荷。

    平台各模块在 `SERVICE_CATALOG` 中是代码常量（`sys` / `identity` / …），不走清单；
    注册把它们作为「平台自身声明」的一部分提交，`sys_module` 的行由此单一入口写入。

    Args:
        payload: 清单解析出的载荷。

    Returns:
        DeclarationPayload: 补入服务行后的载荷（服务行排在清单服务行之前）。
    """
    # 只并入**平台自身**的服务行（`product_key` 为空）：`SERVICE_CATALOG` 里还含产品模块
    # （`pur` / `pay` / …），那些行归各自产品声明，平台代声明会与产品注册撞键
    services: ConcurrentStableList[ModuleRecord] = ConcurrentStableList(
        record for record in SERVICE_CATALOG if not record.product_key
    )
    for record in payload.services:
        if record.module_key not in {item.module_key for item in services}:
            services.add(record)
    return DeclarationPayload(
        product_key=payload.product_key,
        service_key=payload.service_key,
        contract_version=payload.contract_version,
        products=payload.products,
        services=ConcurrentStableFrozenList(services),
        product_routes=payload.product_routes,
        data_sources=payload.data_sources,
        collaborations=payload.collaborations,
        seeds=payload.seeds,
        errcodes=payload.errcodes,
        usages=payload.usages,
        domains=payload.domains,
    )
