"""服务目录健康项测试（Kiwi 2177）：`catalog` 非必需项只标记降级、不参与整体就绪判定。

覆盖 06_01 启动接库校验降级口径的可观测侧：

- `CatalogHealthCheck.required is False`：快照可达 → 该项 `ok=True`；
- 快照不可达（契约 503）→ 该项 `ok=False` 且 `error` 为异常类名，但**整体 `report.ok` 仍为 True**；
- 对照：必需项失败仍使整体不就绪（非必需标记不削弱必需项口径）。
"""

import pytest
from fastapi import FastAPI

from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.health.base import BaseHealthCheck, HealthCheckResult
from bms_core.health.checks import CatalogHealthCheck
from bms_core.health.registry import HealthCheckRegistry
from bms_core.services.module_registry import SERVICE_CATALOG


class _OkCheck(BaseHealthCheck):
    """测试用必需项（恒通过）。"""

    @property
    def key(self) -> str:
        """检查项键。"""
        return "database"

    def describe(self) -> str:
        """元信息描述。"""
        return "恒通过必需项"

    async def check(self) -> HealthCheckResult:
        """恒通过。"""
        return HealthCheckResult(name=self.key, ok=True)


class _DownCheck(BaseHealthCheck):
    """测试用必需项（恒失败）。"""

    @property
    def key(self) -> str:
        """检查项键。"""
        return "redis"

    def describe(self) -> str:
        """元信息描述。"""
        return "恒失败必需项"

    async def check(self) -> HealthCheckResult:
        """恒失败（异常由聚合层收敛为异常类名）。"""
        raise ConnectionError("redis 不可达")


def _stub_snapshot(monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None) -> None:
    """以桩替换服务目录快照取数（模拟本地权威 / 契约两种结果）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        error: 非空表示抛出该异常（模拟契约不可达）。
    """

    async def _load(app: object) -> list[object]:
        if error is not None:
            raise error
        return [*SERVICE_CATALOG]

    monkeypatch.setattr("bms_core.catalog.loader.load_catalog_snapshot", _load)


def test_catalog_check_is_optional_and_ok() -> None:
    """`catalog` 为非必需项；快照可达时该项与整体均就绪。"""
    check = CatalogHealthCheck(FastAPI())
    assert check.key == "catalog"
    assert check.required is False
    assert "非必需项" in check.describe()


async def test_catalog_check_failure_keeps_overall_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照不可达：`catalog` 项标记降级（ok=False + 异常类名），整体仍就绪（不产生 503）。"""
    _stub_snapshot(monkeypatch, error=ServiceUnavailableError("服务目录快照契约调用失败（503）"))
    registry = HealthCheckRegistry()
    registry.register(_OkCheck())
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is True
    assert [item.name for item in report.checks] == ["database", "catalog"]
    assert report.checks[1].ok is False
    assert report.checks[1].error == "ServiceUnavailableError"


async def test_catalog_check_ok_when_snapshot_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """快照可达：`catalog` 项 ok=True（与启动校验同源取数）。"""
    _stub_snapshot(monkeypatch)
    registry = HealthCheckRegistry()
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is True
    assert report.checks[0].ok is True
    assert report.checks[0].error is None


async def test_required_check_failure_still_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """对照：必需项失败仍使整体不就绪（非必需标记不削弱必需项口径）。"""
    _stub_snapshot(monkeypatch, error=ServiceUnavailableError("契约不可达"))
    registry = HealthCheckRegistry()
    registry.register(_DownCheck())
    registry.register(CatalogHealthCheck(FastAPI()))

    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0].ok is False
    assert report.checks[0].error == "ConnectionError"
