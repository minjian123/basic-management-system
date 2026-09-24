"""CI 父-子流水线配置自洽测试（Kiwi 2184）：服务目录 ↔ trigger job ↔ 子模板 ↔ 镜像构建四处一致。

口径（09_01 详细设计 §4.8）：
- 父流水线 trigger job 集合 == 服务目录 `enabled_service_keys()`（无缺件 / 无多余）；
- `backend-test` 全量测试规则只守共享 / 工作区路径（不含 `backend/services`）；
- 子模板 `deploy/ci/templates/backend-service.yml` 结构（test / build / release、resource_group、
  不可中断发布、按服务镜像、Trivy 扫描、发布度量推送）；
- 模板常量与父流水线同源（REGISTRY_IMAGE_PREFIX）、镜像档开关与 Dockerfile 就位。
"""

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from bms_core.db.migration import BACKEND_ROOT
from bms_core.services.module_registry import enabled_service_keys

_REPO = BACKEND_ROOT.parent
_CI_PATH = _REPO / ".gitlab-ci.yml"
_TEMPLATE_PATH = _REPO / "deploy" / "ci" / "templates" / "backend-service.yml"
_IMAGE_SWITCH = _REPO / "deploy" / "ci" / "verify" / "image"
_DOCKERFILE = BACKEND_ROOT / "Dockerfile"


def _load(path: Path) -> dict[str, Any]:
    """读取 YAML 配置。

    Args:
        path: 配置文件路径。

    Returns:
        dict[str, Any]: 解析结果。
    """
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)


def _trigger_jobs(ci: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """取父流水线 trigger 调度 job（stage = trigger 且含 trigger 关键字；排除 `.` 前缀隐藏模板）。

    Args:
        ci: `.gitlab-ci.yml` 解析结果。

    Returns:
        dict[str, dict[str, Any]]: job 名 → job 定义。
    """
    jobs: dict[str, dict[str, Any]] = {}
    for name, job in ci.items():
        if name.startswith("."):
            continue
        job_map = cast("dict[str, Any]", job) if isinstance(job, dict) else None
        if job_map is None:
            continue
        if job_map.get("stage") == "trigger" and "trigger" in job_map:
            jobs[name] = job_map
    return jobs


def _rule_paths(rules: list[dict[str, Any]]) -> list[str]:
    """收集 rules 中全部 changes.paths（含 compare_to 兜底规则）。

    Args:
        rules: job 的 rules 列表。

    Returns:
        list[str]: 路径模式列表。
    """
    paths: list[str] = []
    for rule in rules:
        changes = rule.get("changes")
        if not isinstance(changes, dict):
            continue
        raw_paths = cast("dict[str, Any]", changes).get("paths")
        if isinstance(raw_paths, list):
            paths.extend(str(item) for item in cast("list[Any]", raw_paths))
    return paths


@pytest.mark.kiwi_id(2184)
def test_trigger_jobs_cover_enabled_services() -> None:
    """trigger job 集合与服务目录已启用服务一致；每 job 引用公共模板、depend 等待、按服务路径调度。"""
    ci = _load(_CI_PATH)
    jobs = _trigger_jobs(ci)
    services = {str(job["variables"]["SERVICE"]) for job in jobs.values()}
    assert services == set(enabled_service_keys())
    for job in jobs.values():
        service = str(job["variables"]["SERVICE"])
        trigger = job["trigger"]
        assert trigger["include"] == [{"local": "deploy/ci/templates/backend-service.yml"}]
        assert trigger["strategy"] == "depend"
        paths = _rule_paths(job["rules"])
        assert f"backend/services/{service}/**/*" in paths
        assert any(rule.get("if") == '$CI_PIPELINE_SOURCE == "merge_request_event"' for rule in job["rules"])
        assert any("compare_to" in (rule.get("changes") or {}) for rule in job["rules"])


@pytest.mark.kiwi_id(2184)
def test_parent_backend_test_rules_are_shared_paths_only() -> None:
    """全量测试只守共享 / 工作区路径；单体镜像 job 已移除；trigger 阶段已入 stages。"""
    ci = _load(_CI_PATH)
    paths = _rule_paths(ci["backend-test"]["rules"])
    assert {"backend/libs/**/*", "backend/ops/**/*", "deploy/**/*", ".gitlab-ci.yml"} <= set(paths)
    assert not any(path.startswith("backend/services") for path in paths)
    assert "backend-image" not in ci
    assert "container-scanning" not in ci
    assert ci["stages"] == ["prepare", "lint", "test", "trigger", "build", "verify"]


@pytest.mark.kiwi_id(2184)
def test_service_template_structure() -> None:
    """子模板：parent_pipeline 来源、三阶段、工程级测试 + 本服务包覆盖率门禁。"""
    template = _load(_TEMPLATE_PATH)
    assert template["workflow"]["rules"] == [{"if": '$CI_PIPELINE_SOURCE == "parent_pipeline"'}]
    assert template["stages"] == ["test", "build", "release"]
    test_script = "\n".join(str(line) for line in template["service-test"]["script"])
    assert 'cd "services/$SERVICE"' in test_script
    assert '--cov="bms_$SERVICE"' in test_script
    assert "--cov-fail-under=70" in test_script


@pytest.mark.kiwi_id(2184)
def test_service_build_and_release_jobs() -> None:
    """build 按服务镜像（SHA 标签、镜像档守卫）；release 推送 + Trivy 扫描 + 度量推送 + 串行不可中断。"""
    template = _load(_TEMPLATE_PATH)
    build = template["service-build"]
    assert build["needs"] == ["service-test"]
    assert build["rules"][0]["exists"] == ["deploy/ci/verify/image"]
    build_script = "\n".join(str(line) for line in build["script"])
    assert '--build-arg SERVICE="$SERVICE"' in build_script
    assert "bms-$SERVICE:$CI_COMMIT_SHORT_SHA" in build_script
    assert "-f backend/Dockerfile backend/" in build_script

    release = template["service-release"]
    assert release["needs"] == ["service-build"]
    assert release["resource_group"] == "bms-release-$SERVICE"
    assert release["interruptible"] is False
    assert release["rules"][0]["exists"] == ["deploy/ci/verify/image"]
    release_script = "\n".join(str(line) for line in release["script"])
    assert "docker push" in release_script
    assert "aquasec/trivy:0.74.0" in release_script
    assert ":latest" not in release_script
    assert "TRIVY_DB_REPOSITORY=ghcr.nju.edu.cn/aquasecurity/trivy-db:2" in release_script
    assert "trivy-cache:/root/.cache/trivy" in release_script
    assert "--provenance=false" in build_script
    assert "--severity CRITICAL,HIGH" in release_script
    after_script = "\n".join(str(line) for line in release["after_script"])
    assert "CI_JOB_STATUS" in after_script
    assert "bms_release_total" in after_script
    assert "PUSHGATEWAY_URL" in after_script


@pytest.mark.kiwi_id(2184)
def test_template_constants_and_image_assets() -> None:
    """模板常量与父流水线同源；镜像档开关与参数化 Dockerfile 就位。"""
    ci = _load(_CI_PATH)
    template = _load(_TEMPLATE_PATH)
    assert template["variables"]["REGISTRY_IMAGE_PREFIX"] == ci["variables"]["REGISTRY_IMAGE_PREFIX"]
    assert template["variables"]["REGISTRY_HOST"] == "192.168.0.107:5050"
    assert str(template["variables"]["PUSHGATEWAY_URL"]).startswith("http")
    assert _IMAGE_SWITCH.is_file()
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG SERVICE" in dockerfile
    assert "COPY services/${SERVICE}/src services/${SERVICE}/src" in dockerfile
    assert "python -m bms_${SERVICE}" in dockerfile
    assert "uv sync --frozen" in dockerfile
