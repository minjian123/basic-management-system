"""pytest 公共夹具：配置环境隔离（免外部依赖）。

口径同各服务工程：清除 `BMS_` 环境变量、关闭库连接串模板与可观测 / Redis 真实提供者，
使单元与冒烟用例零外部依赖（/readyz 回落空注册表、不连 Redis / 不导出链路）。
"""

import os
from collections.abc import Iterator

import pytest

from bms_core.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清除 `BMS_` 环境变量与 `.env` 读取，重置配置单例。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)
    # 测试会话固定关闭库连接串模板：dev 默认启用「每服务每租户」模板，会让显式 URL 失效。
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # 就绪探针回落空注册表（单测不连数据库 / Redis）
    monkeypatch.setenv("BMS_HEALTH_CHECK_REGISTRY__PROVIDER", "")
    # 可观测真实提供者关闭（避免全局 TracerProvider / 后台导出线程与网络噪声）
    monkeypatch.setenv("BMS_METRICS__PROVIDER", "")
    monkeypatch.setenv("BMS_TRACER__PROVIDER", "")
    # Redis 基础能力（03_04）：单测零外部依赖
    monkeypatch.setenv("BMS_REDIS__PROVIDER", "")
    monkeypatch.setenv("BMS_REDIS__REQUIRED", "false")
    monkeypatch.setenv("BMS_IDEMPOTENCY__PROVIDER", "")
    monkeypatch.setenv("BMS_CONSISTENCY_BARRIER__PROVIDER", "")
    # 服务间调用 / 会话存储 / 限流真实实现关闭：单测不真实外呼
    monkeypatch.setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    monkeypatch.setenv("BMS_SESSION_STORE__PROVIDER", "")
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
