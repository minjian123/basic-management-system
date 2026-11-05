"""部署编排护栏（Kiwi 2391）：每服务 / 每副本 worker_id 唯一 + 作业 worker 容器命令。"""

from pathlib import Path
from typing import cast

import pytest
import yaml

pytestmark = pytest.mark.kiwi_id(2391)

_COMPOSE = Path(__file__).resolve().parents[5] / "deploy" / "compose" / "services.yml"


def _services() -> dict[str, dict[str, object]]:
    """解析服务编排文件。

    Returns:
        dict[str, dict[str, object]]: 服务定义。
    """
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    return cast("dict[str, dict[str, object]]", data["services"])


def test_every_service_has_unique_worker_id() -> None:
    """每个容器都注入 `BMS_APP__WORKER_ID`，且默认值两两不同、非 0。"""
    services = _services()
    values: list[str] = []
    for name, service in services.items():
        env = cast("dict[str, object]", service.get("environment") or {})
        value = str(env.get("BMS_APP__WORKER_ID") or "")
        assert value, f"{name} 未注入 BMS_APP__WORKER_ID"
        assert value not in values, f"{name} 的 worker_id 与其他容器重复：{value}"
        values.append(value)
    assert len(values) == len(services)
    assert all(":-0}" not in value for value in values)


def test_job_workers_use_service_entrypoints() -> None:
    """作业 worker 容器以 `python -m bms_<service>.jobs` 启动、不暴露端口，健康检查走心跳模块。"""
    services = _services()
    expected = {
        "platform-jobs": "bms_platform.jobs",
        "file-jobs": "bms_file.jobs",
        "report-jobs": "bms_report.jobs",
    }
    for name, module in expected.items():
        service = services[name]
        command = service.get("command")
        assert command == ["python", "-m", module]
        assert service.get("expose") == []
        assert service.get("container_name") == f"bms-{name}"
        healthcheck = cast("dict[str, object]", service.get("healthcheck") or {})
        # worker 不起 HTTP 端口：健康检查用容器本地心跳文件，不能沿用镜像的 /healthz
        assert healthcheck.get("test") == ["CMD", "python", "-m", "bms_core.jobs.heartbeat", "--check"]
