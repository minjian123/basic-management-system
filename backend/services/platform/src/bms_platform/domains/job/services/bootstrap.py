"""作业类型目录自举（启动钩子）：把本仓清单的 `[[jobs]]` 写入 `sys_job_type`。

- **来源唯一**：本仓 `deploy/registry/<service>.toml`（平台自身声明），不读产品仓文件；
- **写入语义**：`content_hash` 未变不写；本次未出现的目录行置 `retired`（不删行）；
- **失败语义**：声明校验不过 / 撞键 → 拒启；库不可用（未初始化）降级放行（目录可在下次启动补齐）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.registry.products import load_product_manifest, local_manifest_paths
from bms_platform.domains.job.repositories.job import JobTypeRepository
from bms_platform.domains.job.services.catalog import JobCatalogService

__all__ = ["bootstrap_job_types"]

_LOGGER = get_logger("bms.platform.job")


def _platform_manifest_path(service_key: str) -> Path:
    """定位平台自身清单。

    Args:
        service_key: 本服务标识。

    Returns:
        Path: 清单路径。

    Raises:
        CatalogError: 本仓清单缺失。
    """
    for path in local_manifest_paths():
        if path.name == f"{service_key}.toml":
            return path
    raise CatalogError(f"平台自身清单缺失：deploy/registry/{service_key}.toml（作业声明无处可读）")


async def bootstrap_job_types(app: FastAPI) -> None:
    """启动钩子：同步作业类型目录。

    Args:
        app: 应用实例（取配置 / 引擎注册表 / 会话工厂）。

    Raises:
        CatalogError: 清单缺失或作业声明校验失败（拒启）。
    """
    settings = app.state.settings
    if not settings.registry.register_on_startup:
        _LOGGER.info("job_type_bootstrap_skipped", reason="registry.register_on_startup=false")
        return
    service_key = str(settings.app.service or "platform")
    manifest = load_product_manifest(_platform_manifest_path(service_key))
    declarations = ConcurrentStableList(manifest.jobs)
    if not declarations:
        return
    try:
        async with (
            session_scope(
                app.state.engine_registry,
                db_key=PLATFORM_DB_KEY,
                factory=app.state.session_factory,
            ) as session,
            session.begin(),
        ):
            report = await JobCatalogService(JobTypeRepository(session)).sync(declarations, source="platform")
    except SQLAlchemyError as exc:  # 库未初始化：降级放行（目录下次启动补齐）
        _LOGGER.warning("作业类型目录写入跳过（平台库不可用）", error=str(exc))
        return
    _LOGGER.info(
        "job_type_bootstrap_done",
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        retired=report.retired,
    )
