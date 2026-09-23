"""服务公开契约：启用服务枚举、快照渲染与契约校验（纯函数，不依赖任何服务包）。

- `enabled_service_records` / `service_enabled`：服务目录（`SERVICE_CATALOG`）视图。
- `render_contract_json`：公开契约（OpenAPI）确定性 JSON（同输入同文本，供 Git 比对与零漂移校验）。
- `validate_contract`：结构 + 契约版本校验（`info.version` 须等于服务目录登记的契约版本）。

快照生成（内存构建各服务应用 OpenAPI）在服务侧 CLI `backend/ops/contract_snapshot.py`
（共享库不得依赖服务包，故构建逻辑不入本模块）。
"""

import json
from collections.abc import Mapping
from typing import cast

from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ModuleStatus

__all__ = [
    "CONTRACTS_DIR",
    "contract_file_name",
    "enabled_service_records",
    "render_contract_json",
    "service_enabled",
    "validate_contract",
]

CONTRACTS_DIR = "deploy/contracts"
"""公开契约快照目录（相对仓库根；每启用服务一份 `<service_key>.json`）。"""


def contract_file_name(service_key: str) -> str:
    """公开契约快照文件名。

    Args:
        service_key: 服务标识。

    Returns:
        str: 形如 `platform.json` 的文件名。
    """
    return f"{service_key}.json"


def enabled_service_records() -> tuple[ModuleRecord, ...]:
    """启用的服务登记行（`service_key` 非空且状态启用）。

    Returns:
        tuple[ModuleRecord, ...]: 按服务目录原始顺序排列的启用服务行。
    """
    return tuple(
        record for record in SERVICE_CATALOG if record.service_key is not None and record.status == ModuleStatus.ENABLED
    )


def service_enabled(service_key: str) -> bool:
    """目标服务是否在服务目录登记且启用（服务间调用寻址前置校验）。

    Args:
        service_key: 服务标识。

    Returns:
        bool: 已登记且启用 True。
    """
    return any(
        record.service_key == service_key and record.status == ModuleStatus.ENABLED for record in SERVICE_CATALOG
    )


def render_contract_json(openapi: Mapping[str, object]) -> str:
    """把公开契约（OpenAPI 映射）渲染为确定性 JSON 文本。

    Args:
        openapi: `app.openapi()` 产物。

    Returns:
        str: 确定性 JSON（缩进 2 / 键排序 / 非 ASCII 直出 + 末尾换行）。
    """
    return json.dumps(openapi, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def validate_contract(service_key: str, openapi: Mapping[str, object], record: ModuleRecord) -> list[str]:
    """校验公开契约结构与契约版本（与登记值一致）。

    Args:
        service_key: 服务标识。
        openapi: 公开契约映射。
        record: 服务目录登记行。

    Returns:
        list[str]: 违规明细；空列表表示通过。
    """
    errors: list[str] = []
    if not isinstance(openapi.get("openapi"), str):
        errors.append(f"{service_key}：OpenAPI 缺少 openapi 版本字段")
    info = openapi.get("info")
    if not isinstance(info, dict):
        errors.append(f"{service_key}：OpenAPI 缺少 info 段")
    else:
        info_map = cast("dict[str, object]", info)
        if not info_map.get("title"):
            errors.append(f"{service_key}：OpenAPI info.title 为空")
        version = info_map.get("version")
        if version != record.contract_version:
            errors.append(f"{service_key}：契约版本不一致（OpenAPI {version!r}，登记 {record.contract_version!r}）")
    paths = openapi.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append(f"{service_key}：OpenAPI paths 为空")
    return errors
