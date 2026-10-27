"""注册表的远端读写（07B `02_06`）：产品侧上报自身声明 / 拉取平台权威快照。

口径：

- 平台是**唯一权威源**：产品只在启动期与其交互两次——先 `PUT` 上报自身清单，再 `GET` 拉全量快照；
- 快照拉回后经 `project_registry()` 投影，消费方的 `resolve_capability()` 等取用入口无需感知来源；
- 失败一律上抛（调用方转拒启）：断链在启动期暴露，不留到运行期。

> 平台进程**不使用**本模块（它本库直读，见 `declaration_bootstrap`）。
"""

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
    record_from_wire,
)
from bms_core.registry.projection import project_registry
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = [
    "DECLARATIONS_PATH",
    "SNAPSHOT_PATH",
    "fetch_declarations",
    "report_declarations",
    "snapshot_from_wire",
]

_LOGGER = get_logger("bms.registry.remote")

DECLARATIONS_PATH = "/api/v1/platform/internal/declarations"
"""注册通道路径（上报 + 快照基址）。"""

SNAPSHOT_PATH = f"{DECLARATIONS_PATH}/snapshot"
"""注册表快照路径。"""

_PLATFORM_SERVICE = "platform"
"""注册表归属服务（权威源）。"""


async def report_declarations(
    client: BaseServiceClient,
    *,
    product_key: str,
    service_key: str,
    manifest_text: str,
) -> ConcurrentStableDict[str, object]:
    """上报本产品声明（单次全量；平台按「本产品维度整体对账」）。

    协议携带**清单文本**而非结构化八段：平台用与本进程完全相同的解析器（`parse_manifest_text`）
    还原声明，避免「协议形状」与「清单结构」两套定义漂移。

    Args:
        client: 服务间调用客户端。
        product_key: 本产品键（清单归属）。
        service_key: 本服务键（须与清单服务行一致）。
        manifest_text: 清单 TOML 文本。

    Returns:
        ConcurrentStableDict[str, object]: 平台回执（逐类计数 + 警示）。

    Raises:
        CatalogError: 非 2xx、响应非法或平台拒收（含校验 / 撞键明细）。
    """
    response = await client.call(
        ServiceRequest(
            service=_PLATFORM_SERVICE,
            method="PUT",
            path=DECLARATIONS_PATH,
            json_body=ConcurrentStableDict(
                {"product_key": product_key, "service_key": service_key, "manifest_toml": manifest_text}
            ),
        )
    )
    if not 200 <= response.status_code < 300:
        raise CatalogError(f"声明上报失败（{response.status_code}）：{response.payload()}")
    body = response.payload()
    data = cast("dict[str, object]", body).get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise CatalogError(f"声明上报响应非法：{body}")
    for message in cast("list[object]", cast("dict[str, object]", data).get("warnings") or []):
        _LOGGER.warning("declaration_report_warning", detail=str(message))
    return ConcurrentStableDict(cast("dict[str, object]", data))


async def snapshot_from_wire(body: object) -> RegistrySnapshot:
    """把快照响应体还原为注册表快照（记录 + 指纹 + 声明方）。

    Args:
        body: 响应体（`{snapshot_version, declarations: {类别: [要素]}}`）。

    Returns:
        RegistrySnapshot: 注册表快照。

    Raises:
        CatalogError: 响应结构非法（缺段 / 非数组）。
    """
    data = cast("ConcurrentStableDict[str, object]", body) if isinstance(body, dict) else None
    if data is None:
        raise CatalogError("注册表快照响应非法：data 非对象")
    declarations = data.get("declarations")
    if not isinstance(declarations, dict):
        raise CatalogError("注册表快照响应非法：缺 declarations 段")
    records: ConcurrentStableDict[str, ConcurrentStableList[object]] = ConcurrentStableDict()
    hashes: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    owners: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
    for kind in DECLARATION_KINDS:
        rows = cast("dict[str, object]", declarations).get(kind) or []
        if not isinstance(rows, list):
            raise CatalogError(f"注册表快照响应非法：{kind} 段非数组")
        kind_records: ConcurrentStableList[object] = ConcurrentStableList()
        kind_hashes: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        kind_owners: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for raw in cast("list[object]", rows):
            if not isinstance(raw, dict):
                raise CatalogError(f"注册表快照响应非法：{kind} 段含非对象行")
            element = cast("dict[str, object]", raw)
            record = record_from_wire(kind, element)
            key = declaration_key(kind, record)
            kind_records.add(record)
            kind_hashes.set(key, content_hash_of(kind, record))
            kind_owners.set(key, str(element.get("product_key") or ""))
        records.set(kind, kind_records)
        hashes.set(kind, kind_hashes)
        owners.set(kind, kind_owners)
    return RegistrySnapshot(records=records, hashes=hashes, owners=owners)


async def fetch_declarations(client: BaseServiceClient) -> RegistrySnapshot:
    """拉取注册表全量快照（服务身份；含访问面路径等完整要素）。

    Args:
        client: 服务间调用客户端。

    Returns:
        RegistrySnapshot: 注册表快照（已可投影）。

    Raises:
        CatalogError: 非 2xx 或响应非法（调用方转拒启）。
    """
    response = await client.call(ServiceRequest(service=_PLATFORM_SERVICE, method="GET", path=SNAPSHOT_PATH))
    if not 200 <= response.status_code < 300:
        raise CatalogError(f"注册表快照拉取失败（{response.status_code}）")
    body = response.payload()
    data = cast("dict[str, object]", body).get("data") if isinstance(body, dict) else None
    snapshot = await snapshot_from_wire(data)
    _LOGGER.info("registry_snapshot_loaded", kinds={kind: len(snapshot.of(kind)) for kind in DECLARATION_KINDS})
    return snapshot


def apply_snapshot(snapshot: RegistrySnapshot) -> None:
    """把拉取到的快照投影进本进程视图族。

    Args:
        snapshot: 注册表快照。
    """
    project_registry(snapshot)
