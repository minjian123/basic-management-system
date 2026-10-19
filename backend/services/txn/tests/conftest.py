"""pytest 公共夹具：配置环境隔离（免外部依赖）。

公共隔离（清 `BMS_` 环境变量 / 关库连接串模板 / 关可观测与 Redis 真实提供者）由测试公共基座
`bms_core.testing.fixtures` 提供（13_04）；本文件只追加交易服务的专属覆盖。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.config import get_settings
from bms_core.testing.fixtures import isolate_settings as bms_isolate_settings

__all__ = ("bms_isolate_settings",)


@pytest.fixture(autouse=True)
def isolate_settings(bms_isolate_settings: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """服务专属隔离：在公共隔离之后追加就绪探针回落空注册表。

    Args:
        bms_isolate_settings: 公共隔离夹具（保证「先清环境、后设服务变量」的顺序）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    # 就绪探针回落空注册表（单测不连数据库 / Redis）
    monkeypatch.setenv("BMS_HEALTH_CHECK_REGISTRY__PROVIDER", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
