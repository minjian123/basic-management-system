"""注册表启动装配（07B `02_06`）：产品进程「上报自身声明 + 拉取权威快照」。

- **平台进程**：跳过（平台自己就是权威源，由 `declaration_bootstrap` 直接本库注册）；
- **产品进程**：读**本仓**清单 → `PUT` 上报 → `GET` 拉全量快照 → 投影进视图族；
- **失败语义**：任一步失败即抛（调用方转拒启）——断链在启动期暴露，不留到运行期；
- **开关**：`registry.register_on_startup`（测试环境关闭，用例显式调注册端点）。
"""

from pathlib import Path

from fastapi import FastAPI

from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.registry.declarations import from_manifest
from bms_core.registry.products import local_manifest_paths, parse_manifest_text
from bms_core.registry.projection import project_registry
from bms_core.registry.remote import fetch_declarations, report_declarations

__all__ = ["bootstrap_declarations"]

_LOGGER = get_logger("bms.registry.boot")

_PLATFORM_SERVICE = "platform"
"""权威源服务键（平台进程跳过远端交互）。"""


async def bootstrap_declarations(app: FastAPI) -> None:
    """产品进程启动钩子：上报自身声明并拉取权威快照投影。

    Args:
        app: 应用实例（取配置 / 服务身份 / 服务间客户端）。

    Raises:
        CatalogError: 清单缺失、上报被拒或快照拉取失败（拒启）。
    """
    settings: Settings = app.state.settings
    if not settings.registry.register_on_startup:
        _LOGGER.info("declaration_bootstrap_skipped", reason="registry.register_on_startup=false")
        return
    identity = app.state.service_identity
    service_key = str(getattr(identity, "name", "") or settings.app.service)
    if service_key == _PLATFORM_SERVICE:
        # 平台自己就是权威：本库直读注册（`declaration_bootstrap`），不走 HTTP
        return
    manifest_path = _manifest_path_for(service_key)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    payload = from_manifest(parse_manifest_text(manifest_text, source=str(manifest_path)))
    client = app.state.service_client
    report = await report_declarations(
        client,
        product_key=payload.product_key,
        service_key=payload.service_key,
        manifest_text=manifest_text,
    )
    _LOGGER.info("declaration_reported", product_key=payload.product_key, report=dict(report))
    project_registry(await fetch_declarations(client))


def _manifest_path_for(service_key: str) -> Path:
    """在本仓清单里定位本服务所属清单（按 `[[services]].service_key` 匹配）。

    Args:
        service_key: 本服务键。

    Returns:
        Path: 清单路径。

    Raises:
        CatalogError: 本仓清单缺失或没有声明本服务（拒启，避免带着空视图启动）。
    """
    candidates = list(local_manifest_paths())
    if not candidates:
        raise CatalogError("本仓清单缺失：deploy/registry/*.toml（无法上报自身声明）")
    for path in candidates:
        manifest = parse_manifest_text(path.read_text(encoding="utf-8"), source=str(path))
        if any(record.service_key == service_key for record in manifest.services):
            return path
    raise CatalogError(f"本仓清单未声明服务 {service_key}：{[p.name for p in candidates]}")
