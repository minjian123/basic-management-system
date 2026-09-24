"""Schemathesis 契约冒烟编排纯函数测试（Kiwi 2186）：服务枚举 / 命令构造 / 就绪轮询 / 结果汇总。

口径（09_03 详细设计 §4.2 / §4.6）：源码直跑真实服务 + 固定 tag 容器打真实服务（零 Broker）；
只读方法（GET / HEAD）+ 有限样例 + 仅 `not_a_server_error`。测试以桩替换子进程 / 探测，不真起服务或容器。
"""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from bms_core.services.module_registry import enabled_service_keys
from ops import contract_smoke


@pytest.mark.kiwi_id(2186)
def test_service_port_and_start_command() -> None:
    """端口按序号分配；启动命令为 `uv run python -m bms_<service>`。"""
    assert contract_smoke.service_port(0) == contract_smoke.BASE_PORT
    assert contract_smoke.service_port(3) == contract_smoke.BASE_PORT + 3
    assert contract_smoke.start_service_command("platform") == ["uv", "run", "python", "-m", "bms_platform"]


@pytest.mark.kiwi_id(2186)
def test_service_env_injects_dev_and_port() -> None:
    """服务进程环境注入 dev 与指定端口。"""
    env = contract_smoke.service_env({"PATH": "/bin"}, 18005)
    assert env["BMS_ENV"] == "dev"
    assert env["BMS_SERVER__PORT"] == "18005"
    assert env["PATH"] == "/bin"


@pytest.mark.kiwi_id(2186)
def test_schemathesis_command_readonly_and_network() -> None:
    """Schemathesis 命令：固定镜像、共享 job 网络、只读方法、有限样例、仅无 5xx 检查。"""
    command = contract_smoke.schemathesis_command(
        "platform", 18000, Path("/repo/deploy/contracts"), container_ref="cid123", max_examples=7
    )
    assert contract_smoke.SCHEMATHESIS_IMAGE in command
    assert "--network" in command and "container:cid123" in command
    assert "/schemas/platform.json" in command
    assert "http://127.0.0.1:18000" in command
    assert "--max-examples" in command and "7" in command
    assert "--checks" in command and "not_a_server_error" in command
    assert "--suppress-health-check" in command
    assert command.count("--include-method") == len(contract_smoke.READ_METHODS)
    assert "GET" in command and "HEAD" in command


@pytest.mark.kiwi_id(2186)
def test_resolve_container_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    """容器引用取 $HOSTNAME（空则空串，由 run 判失败）。"""
    monkeypatch.setenv("HOSTNAME", "abc123")
    assert contract_smoke.resolve_container_ref() == "abc123"
    monkeypatch.delenv("HOSTNAME", raising=False)
    assert contract_smoke.resolve_container_ref() == ""


@pytest.mark.kiwi_id(2186)
def test_wait_for_health_retries_then_ready() -> None:
    """健康轮询：前两次失败、第三次成功即就绪。"""
    calls: list[str] = []

    def probe(url: str) -> object:
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.URLError("not ready")
        return object()

    assert contract_smoke.wait_for_health(18000, probe=probe, sleep=lambda _s: None) is True
    assert len(calls) == 3


@pytest.mark.kiwi_id(2186)
def test_wait_for_health_timeout() -> None:
    """健康轮询超时返回 False。"""

    def probe(url: str) -> object:
        raise urllib.error.URLError("down")

    assert contract_smoke.wait_for_health(18000, attempts=2, probe=probe, sleep=lambda _s: None) is False


@pytest.mark.kiwi_id(2186)
def test_summarize_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    """结果汇总：全通过 0；任一失败 1。"""
    ok = contract_smoke.SmokeResult("platform", True)
    assert contract_smoke.summarize([ok]) == 0
    bad = contract_smoke.SmokeResult("identity", False, "返回码 1")
    assert contract_smoke.summarize([ok, bad]) == 1
    assert "identity" in capsys.readouterr().out


@pytest.mark.kiwi_id(2186)
def test_run_requires_container_ref() -> None:
    """无法解析 job 容器引用时 run 直接失败（不静默跳过）。"""
    assert contract_smoke.run(Path("/repo"), services=["platform"], container_ref="") == 1


@pytest.mark.kiwi_id(2186)
def test_enabled_services_iterable() -> None:
    """服务枚举来源为服务目录启用服务（非空）。"""
    assert list(enabled_service_keys())
