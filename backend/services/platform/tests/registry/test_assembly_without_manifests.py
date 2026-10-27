"""装配期「无清单可装载」用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖 `BaseServiceApplicationFactory.create()` 的 `loads` 为空分支：本仓与配置都没有清单时，
装配照常完成（不记「已装载」日志、不注册任何能力视图）。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.main import ApplicationFactory


def test_assembly_survives_without_manifests(monkeypatch: pytest.MonkeyPatch) -> None:
    """无清单可装载：装配完成且能力使用声明为空（不抛错）。

    Args:
        monkeypatch: 打桩器（把清单装载替换为空结果）。
    """

    def _empty(_paths: Any) -> ConcurrentStableList[Any]:
        """清单装载替身：始终返回空（模拟无清单环境）。

        Args:
            _paths: 配置的清单路径（未使用）。

        Returns:
            ConcurrentStableList[Any]: 空清单。
        """
        return ConcurrentStableList()

    monkeypatch.setattr("bms_core.application.load_product_manifests", _empty)

    app: Any = ApplicationFactory().create(None)

    assert app.state.capability_usages == []
