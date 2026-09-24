"""契约门禁护栏与逻辑测试（Kiwi 2186）：基线 ↔ 服务目录 ↔ CI 配置一致，门禁 / 指标 / 基线刷新逻辑。

口径（09_03 详细设计 §4.1 / §4.6）：
- `deploy/contracts/baseline/` 基线集合 == 服务目录 `enabled_service_keys()`，且契约版本与登记一致；
- `ops.contract_gate.check`：基线 ↔ 实时契约 oasdiff 比对（桩 runner），破坏项非零 + 中文提示；
- `baseline-update` 复制当前快照为基线；`push-metrics` 指标文本格式与失败不阻断；
- `.gitlab-ci.yml` 契约门禁两 job（verify / ci-backend / 档位守卫 / 破坏数推送）、开关与基础镜像就位。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from bms_core.db.migration import BACKEND_ROOT
from bms_core.services.module_registry import enabled_service_keys
from bms_core.services.service_contract import BASELINE_DIR, contract_file_name, enabled_service_records
from ops import contract_gate

_REPO = BACKEND_ROOT.parent
_BASELINE = _REPO / BASELINE_DIR
_SWITCH = _REPO / "deploy" / "ci" / "verify" / "contract-gate"
_CI = _REPO / ".gitlab-ci.yml"
_DOCKERFILE = _REPO / "deploy" / "ci" / "Dockerfile.backend"


def _completed(command: Any, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """构造子进程结果桩。"""
    return subprocess.CompletedProcess(list(command), returncode, stdout, stderr)


def _first_service() -> str:
    """取首个启用服务标识。"""
    return str(enabled_service_keys()[0])


def _rules(job: dict[str, Any]) -> list[dict[str, Any]]:
    """取 job 的 rules 列表。"""
    return cast("list[dict[str, Any]]", job["rules"])


def _change_paths(job: dict[str, Any]) -> list[str]:
    """收集 job 规则中的 `changes.paths`。"""
    paths: list[str] = []
    for rule in _rules(job):
        changes = rule.get("changes")
        if isinstance(changes, dict):
            raw = cast("dict[str, Any]", changes).get("paths")
            if isinstance(raw, list):
                paths.extend(str(item) for item in cast("list[object]", raw))
    return paths


@pytest.mark.kiwi_id(2186)
def test_baseline_matches_enabled_services() -> None:
    """基线文件集合 == 服务目录启用服务；各基线结构合法、契约版本与登记一致。"""
    files = {path.stem for path in _BASELINE.glob("*.json")}
    assert files == set(enabled_service_keys())
    for record in enabled_service_records():
        payload = json.loads((_BASELINE / contract_file_name(str(record.service_key))).read_text(encoding="utf-8"))
        assert payload["info"]["version"] == record.contract_version


@pytest.mark.kiwi_id(2186)
def test_check_passes_without_breaking(tmp_path: Path) -> None:
    """无破坏性变更时 check 退出码 0，指标文本含 0 且末尾换行。"""
    metrics = tmp_path / "m.txt"
    rc = contract_gate.check(
        _REPO, services=[_first_service()], diff=lambda b, c, i: (0, "[]", ""), metrics_out=metrics
    )
    assert rc == 0
    text = metrics.read_text(encoding="utf-8")
    assert f'bms_contract_breaking_total{{service="{_first_service()}"}} 0\n' == text


@pytest.mark.kiwi_id(2186)
def test_check_fails_on_breaking(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """破坏性变更时 check 退出码 1、输出中文提示，指标按条目数计数。"""
    service = _first_service()
    breaking = json.dumps([{"level": "error", "text": "removed field"}, {"level": "error", "text": "removed path"}])
    metrics = tmp_path / "m.txt"
    rc = contract_gate.check(_REPO, services=[service], diff=lambda b, c, i: (1, breaking, ""), metrics_out=metrics)
    assert rc == 1
    assert "破坏性变更" in capsys.readouterr().err
    assert f'bms_contract_breaking_total{{service="{service}"}} 2\n' in metrics.read_text(encoding="utf-8")


@pytest.mark.kiwi_id(2186)
def test_check_reports_missing_baseline(tmp_path: Path) -> None:
    """基线缺件时 check 非零退出。"""
    assert contract_gate.check(tmp_path, services=["platform"]) == 1


@pytest.mark.kiwi_id(2186)
def test_check_reports_tool_failure(tmp_path: Path) -> None:
    """oasdiff 返回码异常（非 0/1）时该服务记为失败、非零退出。"""
    (tmp_path / BASELINE_DIR).mkdir(parents=True)
    (tmp_path / BASELINE_DIR / "platform.json").write_text("{}\n", encoding="utf-8")
    result = contract_gate.compare_service(tmp_path, "platform", diff=lambda b, c, i: (2, "", "boom"))
    assert result.ok is False
    assert "返回码 2" in result.error


@pytest.mark.kiwi_id(2186)
def test_baseline_update_copies_current_snapshot(tmp_path: Path) -> None:
    """baseline-update 把当前快照复制为基线；当前快照缺件时报错。"""
    current = tmp_path / "deploy" / "contracts"
    current.mkdir(parents=True)
    (current / "platform.json").write_text('{"info": {}}\n', encoding="utf-8")
    assert contract_gate.baseline_update(tmp_path, services=["platform"]) == 0
    assert (tmp_path / BASELINE_DIR / "platform.json").read_text(encoding="utf-8") == '{"info": {}}\n'
    assert contract_gate.baseline_update(tmp_path, services=["ghost"]) == 1


@pytest.mark.kiwi_id(2186)
def test_count_breaking_variants() -> None:
    """count_breaking 兼容空 / JSON 数组 / 非 JSON 回退。"""
    assert contract_gate.count_breaking("") == 0
    assert contract_gate.count_breaking("[]") == 0
    assert contract_gate.count_breaking(json.dumps([{"level": 3}, {"level": 1}])) == 1
    assert contract_gate.count_breaking(json.dumps([{"level": "error"}, {"level": "info"}])) == 1
    assert contract_gate.count_breaking("not-json\nline2") == 2


@pytest.mark.kiwi_id(2186)
def test_oasdiff_args_and_docker_diff_sequence() -> None:
    """oasdiff 参数含 breaking / ERR / json 与容器内路径；docker_diff 走 create → cp → start → rm 并回传退出码。"""
    assert contract_gate.oasdiff_args() == [
        "breaking",
        "--fail-on",
        "ERR",
        "--format",
        "json",
        "/base.json",
        "/cur.json",
    ]
    calls: list[list[str]] = []

    def fake_run(command: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if "start" in command:
            return _completed(command, 1, '[{"level": 3}]', "")
        return _completed(command, 0)

    code, out, _err = contract_gate.docker_diff(
        Path("/base/x.json"), Path("/cur/x.json"), contract_gate.OASDIFF_IMAGE, run=fake_run
    )
    assert code == 1 and "level" in out
    verbs = [call[1] for call in calls if len(call) > 1]
    assert verbs[0] == "rm" and "create" in verbs and verbs.count("cp") == 2 and "start" in verbs and verbs[-1] == "rm"
    create = next(call for call in calls if "create" in call)
    assert contract_gate.OASDIFF_IMAGE in create and "/base.json" in create and "/cur.json" in create


@pytest.mark.kiwi_id(2186)
def test_push_metrics_no_gateway_skips(tmp_path: Path) -> None:
    """未配置 Pushgateway 地址时跳过推送且不抛。"""
    metrics = tmp_path / "m.txt"
    metrics.write_text('bms_contract_breaking_total{service="platform"} 0\n', encoding="utf-8")
    assert contract_gate.push_metrics(metrics, "") == 0
    assert contract_gate.push_metrics(tmp_path / "none.txt", "http://127.0.0.1:9092") == 0


@pytest.mark.kiwi_id(2186)
def test_push_metrics_swallows_url_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pushgateway 不可达时仅提示、不抛（门禁结论不受影响）。"""
    metrics = tmp_path / "m.txt"
    metrics.write_text('bms_contract_breaking_total{service="platform"} 0\n', encoding="utf-8")

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise contract_gate.urllib.error.URLError("down")

    monkeypatch.setattr(contract_gate.urllib.request, "urlopen", fake_urlopen)
    assert contract_gate.push_metrics(metrics, "http://127.0.0.1:9092") == 0


@pytest.mark.kiwi_id(2186)
def test_ci_contract_jobs_and_switch() -> None:
    """CI 契约门禁两 job（verify / ci-backend / 档位 / 破坏数推送）与开关、基础镜像就位。"""
    ci = cast("dict[str, Any]", yaml.safe_load(_CI.read_text(encoding="utf-8")))
    assert _SWITCH.is_file()
    for name in ("contract-gate", "contract-smoke"):
        job = cast("dict[str, Any]", ci[name])
        assert job["stage"] == "verify"
        assert "ci-backend" in str(job["image"])
        exists_rules = [cast("list[str]", rule["exists"]) for rule in _rules(job) if "exists" in rule]
        assert ["deploy/ci/verify/contract-gate"] in exists_rules
        assert {"backend/**/*", "deploy/**/*"} <= set(_change_paths(job))
    gate = cast("dict[str, Any]", ci["contract-gate"])
    gate_after = "\n".join(str(line) for line in cast("list[object]", gate["after_script"]))
    assert "push-metrics" in gate_after
    assert "PUSHGATEWAY_URL" in cast("dict[str, object]", gate["variables"])
    smoke = cast("dict[str, Any]", ci["contract-smoke"])
    smoke_script = "\n".join(str(line) for line in cast("list[object]", smoke["script"]))
    assert "contract_smoke run" in smoke_script


@pytest.mark.kiwi_id(2186)
def test_ci_base_image_has_docker_cli() -> None:
    """ci-backend 基础镜像加装 docker CLI（契约门禁 job 同环境内调工具镜像）。"""
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    assert "docker-" in dockerfile
    assert "/usr/local/bin/docker" in dockerfile
