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
    """可观测组件齐备（含 08_02 告警 / 探针 / 阶段度量）；聚合编排 `include`（一键拉起）。"""
    config = _load(_DEPLOY / "compose" / "observability.yml")
    assert set(config["services"]) == {
        "otel-collector",
        "tempo",
        "prometheus",
        "loki",
        "alloy",
        "grafana",
        "alertmanager",
        "blackbox-exporter",
        "pushgateway",
    }
    aggregate = _load(_DEPLOY / "compose" / "bms.yml")
    assert aggregate["include"] == ["base.yml", "gateway.yml", "observability.yml"]


@pytest.mark.kiwi_id(2182)
def test_grafana_datasources_provisioned() -> None:
    """Grafana 三数据源（Prometheus / Loki / Tempo）声明式 provisioning。"""
    config = _load(_OBS / "grafana" / "provisioning" / "datasources" / "bms.yaml")
    names = {item["name"] for item in config["datasources"]}
    assert names == {"Prometheus", "Loki", "Tempo"}


@pytest.mark.kiwi_id(2183)
def test_slo_rules_anchored() -> None:
    """基座 SLO 规则齐备（探针 / 依赖 / catalog / 错误率 / 延迟 / 发件箱）且分级与阈值锚点正确。"""
    config = _load(_OBS / "rules" / "bms-slo.yml")
    rules = {rule["alert"]: rule for group in config["groups"] for rule in group["rules"]}
    assert set(rules) == {
        "BmsServiceMetricsDown",
        "BmsProbeFailing",
        "BmsDependencyNotReady",
        "BmsCatalogDegraded",
        "BmsHighErrorRate",
        "BmsCriticalErrorRate",
        "BmsSlowRequestsP99",
        "BmsOutboxBacklog",
    }
    assert rules["BmsProbeFailing"]["labels"]["severity"] == "critical"
    assert "probe_success" in rules["BmsProbeFailing"]["expr"]
    assert rules["BmsCatalogDegraded"]["labels"]["severity"] == "warning"
    assert "bms_catalog_degraded == 1" in rules["BmsCatalogDegraded"]["expr"]
    assert "> 0.001" in rules["BmsHighErrorRate"]["expr"]
    assert "> 0.05" in rules["BmsCriticalErrorRate"]["expr"]
    assert "> 0.8" in rules["BmsSlowRequestsP99"]["expr"]
    assert "> 100" in rules["BmsOutboxBacklog"]["expr"]
    # 业务链路 SLO 锚点留位登记（注释形式）
    text = (_OBS / "rules" / "bms-slo.yml").read_text(encoding="utf-8")
    for anchor in ("登录成功率", "审批提交成功率", "Socket.IO", "备份任务"):
        assert anchor in text


@pytest.mark.kiwi_id(2183)
def test_compose_alerting_probe_and_metrics_components() -> None:
    """三新组件入编排：alertmanager / blackbox-exporter / pushgateway（含规则与渲染产物挂载）。"""
    config = _load(_DEPLOY / "compose" / "observability.yml")
    services = config["services"]
    assert {"alertmanager", "blackbox-exporter", "pushgateway"} <= set(services)
    assert (
        "../observability/rendered/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro"
        in services["alertmanager"]["volumes"]
    )
    assert "../observability/rules:/etc/prometheus/rules:ro" in services["prometheus"]["volumes"]
    assert {"alertmanager-data", "pushgateway-data"} <= set(config["volumes"])


@pytest.mark.kiwi_id(2183)
def test_prometheus_alerting_probe_and_pushgateway() -> None:
    """Prometheus 接线：规则目录 / Alertmanager 地址 / blackbox 探针 job / Pushgateway 抓取。"""
    config = _load(_OBS / "prometheus.yml")
    assert config["rule_files"] == ["/etc/prometheus/rules/*.yml"]
    assert config["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"] == ["alertmanager:9093"]
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert {"bms-probe", "pushgateway", "alertmanager"} <= set(jobs)
    probe = jobs["bms-probe"]
    assert probe["metrics_path"] == "/probe"
    assert probe["params"]["module"] == ["http_2xx"]
    targets = probe["static_configs"][0]["targets"]
    assert any(target.endswith("/healthz") for target in targets)
    assert any(target.endswith("/readyz") for target in targets)
    assert jobs["pushgateway"]["honor_labels"] is True
    assert jobs["pushgateway"]["static_configs"][0]["targets"] == ["pushgateway:9091"]


@pytest.mark.kiwi_id(2183)
def test_blackbox_probe_module() -> None:
    """blackbox 模块仅 200 视为成功（/readyz 503 即探测失败信号）。"""
    config = _load(_OBS / "blackbox.yml")
    module = config["modules"]["http_2xx"]
    assert module["prober"] == "http"
    assert module["http"]["valid_status_codes"] == [200]


@pytest.mark.kiwi_id(2183)
def test_alertmanager_template_and_render_assets() -> None:
    """告警配置模板 / 渲染产物目录 / gitignore 与 env 模板口径齐备（凭据不入库）。"""
    template = (_OBS / "alertmanager.yml.tmpl").read_text(encoding="utf-8")
    for placeholder in ("$global_smtp_block", "$default_receiver_block", "$critical_receiver_block"):
        assert placeholder in template
    assert 'severity="critical"' in template
    assert (_OBS / "rendered" / ".gitkeep").is_file()
    assert "observability/rendered/alertmanager.yml" in (_DEPLOY / ".gitignore").read_text(encoding="utf-8")
    env_example = (_DEPLOY / ".env.example").read_text(encoding="utf-8")
    for key in (
        "ALERTMANAGER_PORT",
        "ALERTMANAGER_SMTP_SMARTHOST",
        "ALERTMANAGER_EMAIL_TO",
        "ALERTMANAGER_WECOM_WEBHOOK_URL",
        "PUSHGATEWAY_PORT",
        "BLACKBOX_PORT",
    ):
        assert key in env_example


@pytest.mark.kiwi_id(2183)
def test_slo_and_stage_dashboards_and_overview_variables() -> None:
    """两张新面板 + 总览变量（service / version）声明式就位。"""
    slo = _load(_OBS / "grafana" / "dashboards" / "bms-slo.json")
    assert slo["uid"] == "bms-slo"
    assert any(str(panel.get("title", "")).startswith("告警") for panel in slo["panels"])
    stage = _load(_OBS / "grafana" / "dashboards" / "bms-stage-metrics.json")
    assert stage["uid"] == "bms-stage-metrics"
    exprs = [str(target.get("expr", "")) for panel in stage["panels"] for target in panel.get("targets", [])]
    assert any("bms_release_total" in expr for expr in exprs)
    assert any("bms_contract_breaking_total" in expr for expr in exprs)
    assert any("bms_boundary_cross_access_total" in expr for expr in exprs)
    overview = _load(_OBS / "grafana" / "dashboards" / "bms-overview.json")
    variables = {item["name"] for item in overview["templating"]["list"]}
    assert variables == {"service", "version"}
