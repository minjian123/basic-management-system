"""服务编排 / 抓取 / 发布配置自洽测试（Kiwi 2185）：服务目录 ↔ 编排 ↔ 抓取 ↔ 发布 CLI 一致。

口径（09_02 详细设计 §4.10）：
- `deploy/compose/services.yml` 服务集合 == 服务目录 `enabled_service_keys()`；
  服务名（Compose DNS）取 `{service_key}`、镜像名 `bms-{service}`、标签 `BMS_TAG_<SERVICE>`（禁 latest）；
- 仅内部网络（expose 8000，不映射宿主端口）、依赖 redis / mysql、边界白名单挂载；
- `prometheus.yml` 抓取 / 探针目标集合 == 服务目录（`{service_key}:8000`）；
- 运行镜像含迁移能力（`COPY alembic/` + `ops/`）；
- `bms.yml` 聚合 services.yml；`scripts/tools/deploy/release.py` 服务清单与目录一致。
"""

import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from bms_core.db.migration import BACKEND_ROOT
from bms_core.services.module_registry import enabled_service_keys

_REPO = BACKEND_ROOT.parent
_SERVICES_YML = _REPO / "deploy" / "compose" / "services.yml"
_BMS_YML = _REPO / "deploy" / "compose" / "bms.yml"
_PROMETHEUS = _REPO / "deploy" / "observability" / "prometheus.yml"
_BLACKBOX = _REPO / "deploy" / "observability" / "blackbox.yml"
_ENV_EXAMPLE = _REPO / "deploy" / ".env.example"
_IMAGE_SWITCH = _REPO / "deploy" / "ci" / "verify" / "image"
_RELEASE_CLI = _REPO / "scripts" / "tools" / "deploy" / "release.py"
_DOCKERFILE = BACKEND_ROOT / "Dockerfile"
_DOCKERIGNORE = BACKEND_ROOT / ".dockerignore"

_spec = importlib.util.spec_from_file_location("release_cli", _RELEASE_CLI)
assert _spec is not None and _spec.loader is not None
release_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_cli)


def _load(path: Path) -> dict[str, Any]:
    """读取 YAML 配置。"""
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)


def _scrape_targets(prom: dict[str, Any], job_name: str) -> tuple[list[str], dict[str, Any]]:
    """取指定 job 的抓取目标列表与 job 定义。"""
    for job in cast("list[dict[str, Any]]", prom["scrape_configs"]):
        if job.get("job_name") == job_name:
            targets: list[str] = []
            for static in job["static_configs"]:
                targets.extend(str(item) for item in static.get("targets", []))
            return targets, job
    raise AssertionError(f"未找到抓取 job：{job_name}")


@pytest.mark.kiwi_id(2185)
def test_services_compose_covers_enabled_services() -> None:
    """编排服务集合 == 服务目录；服务名 / 镜像名 / 标签变量一致；禁 latest。"""
    compose = _load(_SERVICES_YML)
    services = compose["services"]
    assert set(services) == set(enabled_service_keys())
    for key in enabled_service_keys():
        image = str(services[key]["image"])
        assert image.endswith(f"/bms-{key}:${{BMS_TAG_{key.upper()}:?BMS_TAG_{key.upper()} required}}")
        assert "latest" not in image
        assert services[key]["container_name"] == f"bms-{key}"


@pytest.mark.kiwi_id(2185)
def test_services_compose_network_and_mounts() -> None:
    """仅内部网络、依赖基础设施、边界白名单挂载与环境变量就位。"""
    compose = _load(_SERVICES_YML)
    base = compose["x-service-base"]
    assert base["expose"] == ["8000"]
    assert "ports" not in base
    assert base["depends_on"] == ["redis", "mysql"]
    assert "../boundaries:/opt/deploy/boundaries:ro" in base["volumes"]
    env = base["environment"]
    assert env["BMS_DATA_OWNERSHIP__EXCEPTIONS_FILE"] == "/opt/deploy/boundaries/data_ownership_exceptions.json"
    assert env["BMS_REDIS__URL"] == "redis://redis:6379/0"
    assert env["BMS_TRACER__OTLP_ENDPOINT"] == "http://otel-collector:4318"
    assert env["BMS_SERVICE_CLIENT__PROVIDER"] == "http"
    assert "http://{service}:8000" in env["BMS_SERVICE_CLIENT__OPTIONS"]


@pytest.mark.kiwi_id(2185)
def test_prometheus_targets_switch_to_compose_dns() -> None:
    """抓取 / 探针目标切 {service_key}:8000 全量登记（无宿主机残留）。"""
    prom = _load(_PROMETHEUS)
    services_targets, _ = _scrape_targets(prom, "bms-services")
    assert set(services_targets) == {f"{key}:8000" for key in enabled_service_keys()}
    probe_targets, probe_job = _scrape_targets(prom, "bms-probe")
    expected_probe = {f"http://{key}:8000/{probe}" for key in enabled_service_keys() for probe in ("healthz", "readyz")}
    assert set(probe_targets) == expected_probe
    assert probe_job["params"]["module"] == ["http_2xx"]
    assert "host.docker.internal" not in "\n".join(services_targets + probe_targets)


@pytest.mark.kiwi_id(2185)
def test_blackbox_module_requires_200() -> None:
    """blackbox 模块 http_2xx 仅 200 成功（/readyz 未就绪即 503 视为失败）。"""
    blackbox = _load(_BLACKBOX)
    assert blackbox["modules"]["http_2xx"]["http"]["valid_status_codes"] == [200]


@pytest.mark.kiwi_id(2185)
def test_image_contains_migration_capability() -> None:
    """运行镜像含 alembic / ops（迁移容器复用）；.dockerignore 不排除二者。"""
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY alembic ./alembic" in dockerfile
    assert "COPY ops ./ops" in dockerfile
    assert "alembic.ini" in dockerfile
    dockerignore = _DOCKERIGNORE.read_text(encoding="utf-8")
    assert "alembic" not in dockerignore
    assert "ops" not in dockerignore


@pytest.mark.kiwi_id(2185)
def test_bms_aggregation_and_env_example() -> None:
    """bms.yml 聚合 services.yml；环境变量模板与镜像档就位；release CLI 服务清单同源。"""
    bms = _load(_BMS_YML)
    assert "services.yml" in bms["include"]
    assert _IMAGE_SWITCH.is_file()
    env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in (
        "REGISTRY_IMAGE_PREFIX",
        "BMS_DATABASE__PLATFORM__URL_TEMPLATE",
        "BMS_DATABASE__TENANTS__URL_TEMPLATE",
        "BMS_DEPLOY_TENANTS",
        "BMS_KEEP_SHA_TAGS",
    ):
        assert key in env_text
    assert tuple(release_cli.SERVICES) == tuple(enabled_service_keys())
