"""库数量统计测试（Kiwi 1078）：预期口径、活跃口径与 `bms_db_count` 指标记录。"""

from typing import cast

import pytest

from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.inventory import db_count_rows, db_counts_by_kind, db_counts_from_keys
from bms_core.db.registry import EngineRegistry
from bms_core.metrics.base import BaseMetrics


class _Recorder:
    """伪指标器：仅记录 gauge 调用（用于断言库数量指标记录）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.calls: list[tuple[str, float, dict[str, str]]] = []

    async def gauge(self, name: str, *, value: float, labels: dict[str, str] | None = None) -> None:
        """记录一次 gauge 调用。

        Args:
            name: 指标名。
            value: 指标值。
            labels: 标签集。
        """
        self.calls.append((name, value, dict(labels or {})))


@pytest.mark.kiwi_id(2178)
def test_db_count_expected_and_active() -> None:
    """预期口径：平台服务库 = 服务数、服务租户库 = 服务数 × 租户数、归档 1；活跃口径按库键统计。"""
    count = db_count_rows(("platform", "tenant", "org"), ("demo", "acme"))
    assert count.platform == 3
    assert count.tenant == 6
    assert count.archive == 1
    assert count.total == 10
    assert "共 10 个库" in count.describe()

    active = db_counts_by_kind(["platform", "tenant_demo", "tenant_acme", "tenant_org_demo", "archive", "zzz_bad"])
    assert active == {"platform": 1, "tenant": 3, "archive": 1}

    active_count = db_counts_from_keys(["platform", "tenant_demo"])
    assert (active_count.platform, active_count.tenant, active_count.archive) == (1, 1, 1)


@pytest.mark.kiwi_id(2178)
async def test_registry_records_db_count() -> None:
    """引擎注册表：新建 / 回收租户引擎后记录 `bms_db_count`（标签含 `kind` 与 `service`）。"""
    settings = get_settings()
    settings.database.tenants.url = "sqlite+aiosqlite:///:memory:"
    settings.database.tenants.url_template = ""
    settings.app.service = "ai"
    recorder = _Recorder()

    registry = EngineRegistry(
        EngineFactory(settings),
        metrics=cast("BaseMetrics", recorder),
        metrics_service="ai",
    )
    try:
        await registry.get("tenant_demo")
        assert ("bms_db_count", 1.0, {"kind": "tenant", "service": "ai"}) in recorder.calls
        assert registry.db_counts() == {"tenant": 1}

        await registry.release("tenant_demo")
        assert registry.db_counts() == {}
        # 回收后无活跃租户库 → 不再产生新的记录（避免 0 值噪声）
        assert [value for _, value, labels in recorder.calls if labels.get("kind") == "tenant"] == [1.0]
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2178)
async def test_registry_without_metrics_is_noop() -> None:
    """未装配指标器时记录为空操作（不报错、不副作用）。"""
    settings = get_settings()
    settings.database.tenants.url = "sqlite+aiosqlite:///:memory:"
    settings.database.tenants.url_template = ""

    registry = EngineRegistry(EngineFactory(settings))
    try:
        await registry.record_db_counts()
        await registry.get("tenant_demo")
        assert registry.db_counts() == {"tenant": 1}
    finally:
        await registry.aclose()
