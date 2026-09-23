"""可观测性编排与配置自洽测试（Kiwi 2182）：组件 / 抓取 / 保留期 / 结构化元数据 / 一键聚合。"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from bms_core.db.migration import BACKEND_ROOT

_DEPLOY = BACKEND_ROOT.parent / "deploy"
_OBS = _DEPLOY / "observability"


def _load(path: Path) -> dict[str, Any]:
    """读取 YAML 配置（断言用）。

    Args:
        path: 配置文件路径。

    Returns:
        dict[str, Any]: 解析结果。
    """
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.kiwi_id(2182)
def test_collector_otlp_to_tempo() -> None:
    """collector 接收 OTLP 并导出 Tempo（traces 管线）。"""
    config = _load(_OBS / "otel-collector.yaml")
    assert "otlp" in config["receivers"]
    assert config["exporters"]["otlp/tempo"]["endpoint"] == "tempo:4317"
    assert config["service"]["pipelines"]["traces"]["exporters"] == ["otlp/tempo"]


@pytest.mark.kiwi_id(2182)
def test_prometheus_jobs_and_retention() -> None:
    """Prometheus 抓取含服务 / APISIX / collector；保留期 15d 经启动参数。"""
    config = _load(_OBS / "prometheus.yml")
    jobs = {job["job_name"] for job in config["scrape_configs"]}
    assert {"apisix", "otel-collector", "bms-services"} <= jobs
    compose = (_DEPLOY / "compose" / "observability.yml").read_text(encoding="utf-8")
    assert "retention.time=15d" in compose


@pytest.mark.kiwi_id(2182)
def test_tempo_retention() -> None:
    """Tempo 保留期 72h（block_retention）。"""
    config = _load(_OBS / "tempo.yaml")
    assert config["compactor"]["compaction"]["block_retention"] == "72h"


@pytest.mark.kiwi_id(2182)
def test_loki_retention_and_structured_metadata() -> None:
    """Loki 保留期 30d 且启用结构化元数据（trace_id / request_id 不作标签）。"""
    config = _load(_OBS / "loki.yaml")
    assert config["limits_config"]["retention_period"] == "30d"
    assert config["limits_config"]["allow_structured_metadata"] is True
    assert config["compactor"]["retention_enabled"] is True


@pytest.mark.kiwi_id(2182)
def test_alloy_labels_and_structured_metadata() -> None:
    """Alloy 解析 JSON：service / level 作标签，trace_id / request_id 作结构化元数据。"""
    text = (_OBS / "alloy.alloy").read_text(encoding="utf-8")
    assert "stage.structured_metadata" in text
    assert "trace_id" in text and "request_id" in text
    assert 'service = "service"' in text


@pytest.mark.kiwi_id(2182)
def test_compose_components_and_one_command_aggregate() -> None:
    """可观测组件齐备；聚合编排 `include` base / gateway / observability（一键拉起）。"""
    config = _load(_DEPLOY / "compose" / "observability.yml")
    assert set(config["services"]) == {"otel-collector", "tempo", "prometheus", "loki", "alloy", "grafana"}
    aggregate = _load(_DEPLOY / "compose" / "bms.yml")
    assert aggregate["include"] == ["base.yml", "gateway.yml", "observability.yml"]


@pytest.mark.kiwi_id(2182)
def test_grafana_datasources_provisioned() -> None:
    """Grafana 三数据源（Prometheus / Loki / Tempo）声明式 provisioning。"""
    config = _load(_OBS / "grafana" / "provisioning" / "datasources" / "bms.yaml")
    names = {item["name"] for item in config["datasources"]}
    assert names == {"Prometheus", "Loki", "Tempo"}
