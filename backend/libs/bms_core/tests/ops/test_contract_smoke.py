"""Schemathesis 契约冒烟编排纯函数测试（Kiwi 2186）：已构建镜像起容器 / 命令构造 / 就绪轮询 / 执行序列。

口径（09_03 详细设计 §4.2 / §4.6）：用**已构建服务镜像**起真实容器 + Schemathesis 容器
`--network container:<服务容器>` 打；只读 GET/HEAD + 每操作 1 例 + 仅 `not_a_server_error`；
排除基础设施端点。测试以桩替换子进程，不真起容器。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from ops import contract_smoke


def _completed(command: Any, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """构造子进程结果桩。"""
    return subprocess.CompletedProcess(list(command), returncode, stdout, stderr)


@pytest.mark.kiwi_id(2186)
def test_container_name_and_schemathesis_args() -> None:
    """容器名固定；参数含容器内 schema 路径、127.0.0.1:8000、只读方法、排除探针。"""
    assert contract_smoke.service_container_name("platform") == "bms-smoke-platform"
    command = contract_smoke.schemathesis_args("platform", max_examples=1)
    assert "/tmp/platform.json" in command
    assert f"http://127.0.0.1:{contract_smoke.SERVICE_PORT}" in command
    assert "--max-examples" in command and "1" in command
    assert "--checks" in command and "not_a_server_error" in command
    assert "--suppress-health-check" in command
    assert command.count("--include-method") == len(contract_smoke.READ_METHODS)
    assert command.count("--exclude-path") == len(contract_smoke.EXCLUDED_PATHS)
    assert "GET" in command and "HEAD" in command and "/readyz" in command


@pytest.mark.kiwi_id(2186)
def test_service_up_healthy() -> None:
    """起容器 → 轮询 healthy 即就绪；镜像标签随命令传入。"""
    calls: list[list[str]] = []
    inspect_n = {"n": 0}

    def fake_run(command: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if "inspect" in command:
            inspect_n["n"] += 1
            return _completed(command, 0, "starting" if inspect_n["n"] == 1 else "healthy")
        return _completed(command, 0)

    assert contract_smoke.service_up("platform", "reg/bms-platform:abc", run=fake_run, sleep=lambda _s: None) is True
    run_cmd = next(call for call in calls if call[1] == "run")
    assert "BMS_ENV=dev" in run_cmd and "reg/bms-platform:abc" in run_cmd
    assert inspect_n["n"] == 2


@pytest.mark.kiwi_id(2186)
def test_service_up_start_failure_and_timeout() -> None:
    """起容器失败即 False；就绪超时 False。"""

    def fail_run(command: Any) -> subprocess.CompletedProcess[str]:
        return _completed(command, 1, "", "boom") if command[1] == "run" else _completed(command, 0)

    assert contract_smoke.service_up("platform", "img", run=fail_run, sleep=lambda _s: None) is False

    def never_healthy(command: Any) -> subprocess.CompletedProcess[str]:
        return _completed(command, 0, "starting" if "inspect" in command else "")

    assert contract_smoke.service_up("platform", "img", run=never_healthy, sleep=lambda _s: None, attempts=2) is False


@pytest.mark.kiwi_id(2186)
def test_service_down_runs_rm() -> None:
    """停止服务容器执行 `docker rm -f <容器>`。"""
    calls: list[list[str]] = []
    contract_smoke.service_down("platform", run=lambda c: (calls.append(list(c)), _completed(c, 0))[1])
    assert calls[0][1:4] == ["rm", "-f", "bms-smoke-platform"]


@pytest.mark.kiwi_id(2186)
def test_docker_schemathesis_sequence() -> None:
    """Schemathesis：create（--network container:服务容器 + 固定镜像）→ cp → start → rm。"""
    calls: list[list[str]] = []

    def fake_run(command: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if "start" in command:
            return _completed(command, 0, "ok", "")
        return _completed(command, 0)

    code, out, _err = contract_smoke.docker_schemathesis(
        "platform",
        Path("/repo/deploy/contracts/platform.json"),
        service_container="bms-smoke-platform",
        run=fake_run,
    )
    assert code == 0 and out == "ok"
    verbs = [call[1] for call in calls if len(call) > 1]
    assert verbs[0] == "rm" and "create" in verbs and verbs.count("cp") == 1 and "start" in verbs and verbs[-1] == "rm"
    create = next(call for call in calls if "create" in call)
    assert contract_smoke.SCHEMATHESIS_IMAGE in create
    assert create[create.index("--network") + 1] == "container:bms-smoke-platform"
    cp = next(call for call in calls if call[1] == "cp")
    assert cp[-1].endswith(":/tmp/platform.json")


@pytest.mark.kiwi_id(2186)
def test_run_reports_service_not_ready() -> None:
    """服务容器未就绪时 run 失败并清理。"""
    calls: list[list[str]] = []

    def fake_run(command: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if command[1] == "run":
            return _completed(command, 1, "", "cannot start")
        return _completed(command, 0)

    assert (
        contract_smoke.run(Path("/repo"), service="platform", image="img", run_cmd=fake_run, sleep=lambda _s: None) == 1
    )
    assert any(call[1:3] == ["rm", "-f"] for call in calls)


@pytest.mark.kiwi_id(2186)
def test_run_success_and_failure() -> None:
    """就绪后 Schemathesis 返回 0 → run 通过；返回码非 0 → run 失败。"""
    exit_holder = {"code": 0}

    def fake_run(command: Any) -> subprocess.CompletedProcess[str]:
        if "inspect" in command:
            return _completed(command, 0, "healthy")
        if "start" in command:
            return _completed(command, exit_holder["code"], "out", "")
        return _completed(command, 0)

    assert (
        contract_smoke.run(Path("/repo"), service="platform", image="img", run_cmd=fake_run, sleep=lambda _s: None) == 0
    )
    exit_holder["code"] = 1
    assert (
        contract_smoke.run(Path("/repo"), service="platform", image="img", run_cmd=fake_run, sleep=lambda _s: None) == 1
    )
