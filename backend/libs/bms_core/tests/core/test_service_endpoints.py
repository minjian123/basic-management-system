"""服务端点覆盖测试：归一 / 校验 / 登记与取基址（容器按模板派生、本机按覆盖）。"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.config import ServiceClientSettings
from bms_core.core.exceptions import ConfigError
from bms_core.core.service_endpoints import (
    normalize_service_endpoints,
    register_service_endpoints,
    reset_service_endpoints,
    service_base_url,
)
from bms_core.servicecall.base import ServiceRequest, build_service_url

_TEMPLATE = "http://{service}:8000"


@pytest.fixture(autouse=True)
def _isolate_endpoints() -> Iterator[None]:
    """用例间隔离：进程级登记表先清后清（覆盖登记是跨能力域共享的单例状态）。"""
    reset_service_endpoints()
    yield
    reset_service_endpoints()


def _request(service: str = "platform") -> ServiceRequest:
    return ServiceRequest(service=service, method="GET", path="/api/v1/demo/user-roles")


def test_normalize_empty_means_no_override() -> None:
    """None / 空表 → 空覆盖（容器部署口径：完全按基址模板派生）。"""
    assert len(normalize_service_endpoints(None)) == 0
    assert len(normalize_service_endpoints(ConcurrentStableFrozenDict({}))) == 0


def test_normalize_strips_key_and_trailing_slash() -> None:
    """归一：服务键去首尾空白、基址去尾斜杠（避免拼出双斜杠）。"""
    normalized = normalize_service_endpoints(ConcurrentStableFrozenDict({" mdm ": "http://127.0.0.6:8000/"}))
    assert normalized["mdm"] == "http://127.0.0.6:8000"


def test_normalize_rejects_empty_service_key() -> None:
    """服务键为空即拒（配错了不能静默当作没配）。"""
    with pytest.raises(ConfigError, match="服务键不得为空"):
        normalize_service_endpoints(ConcurrentStableFrozenDict({"  ": "http://127.0.0.6:8000"}))


def test_normalize_rejects_non_http_base() -> None:
    """基址须 http(s) 绝对地址（服务间调用只走 HTTP(S)）。"""
    with pytest.raises(ConfigError, match="须为 http\\(s\\) 绝对地址"):
        normalize_service_endpoints(ConcurrentStableFrozenDict({"mdm": "127.0.0.6:8000"}))


def test_config_rejects_bad_endpoints() -> None:
    """配置模型装配即校验（非法端点 → 拒启，不静默回落模板）。"""
    with pytest.raises(ConfigError):
        ServiceClientSettings(endpoints=ConcurrentStableDict({"mdm": "ftp://127.0.0.6:8000"}))


def test_base_url_prefers_override_then_template() -> None:
    """取基址：已覆盖服务取覆盖，未覆盖服务按模板派生。"""
    register_service_endpoints(ConcurrentStableFrozenDict({"mdm": "http://127.0.0.6:8000"}))

    assert service_base_url("mdm", _TEMPLATE) == "http://127.0.0.6:8000"
    assert service_base_url("platform", _TEMPLATE) == "http://platform:8000"

    reset_service_endpoints()
    assert service_base_url("mdm", _TEMPLATE) == "http://mdm:8000"


def test_build_service_url_honors_override() -> None:
    """服务间调用拼址走同一份覆盖（本机裸跑不再依赖系统 hosts 别名）。"""
    register_service_endpoints(ConcurrentStableFrozenDict({"mdm": "http://127.0.0.6:8000"}))

    url = build_service_url(_request("mdm"), _TEMPLATE)

    assert url == "http://127.0.0.6:8000/api/v1/demo/user-roles"


def test_register_bad_endpoints_keeps_previous_registration() -> None:
    """登记非法覆盖即报错且不改动已生效的登记（fail-closed，不留半套）。"""
    register_service_endpoints(ConcurrentStableFrozenDict({"mdm": "http://127.0.0.6:8000"}))

    with pytest.raises(ConfigError):
        register_service_endpoints(ConcurrentStableFrozenDict({"mdm": "not-a-url"}))

    assert service_base_url("mdm", _TEMPLATE) == "http://127.0.0.6:8000"
