"""服务目录快照读出（06_03）：经 `platform` 服务只读契约取全量清单（启动接库校验用）。"""

from bms_core.catalog.base import (
    CATALOG_SERVICE_KEY,
    CATALOG_SNAPSHOT_PATH,
    fetch_catalog_snapshot,
)

__all__ = ["CATALOG_SERVICE_KEY", "CATALOG_SNAPSHOT_PATH", "fetch_catalog_snapshot"]
