"""作业 worker 心跳用例（Kiwi 2422）：文件写入 / 超时判定 / CLI / 配置一致性。"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import JobSettings
from bms_core.jobs import heartbeat as hb
from bms_core.jobs.heartbeat import (
    DEFAULT_HEARTBEAT_PATH,
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    check_heartbeat,
    heartbeat_age,
    main,
    write_heartbeat,
)

pytestmark = pytest.mark.kiwi_id(2422)


def test_write_heartbeat_creates_and_refreshes(tmp_path: Path) -> None:
    """文件缺失时创建（含父目录），已存在时刷新 mtime。"""
    target = tmp_path / "nested" / "beat"
    write_heartbeat(target)
    assert target.is_file()

    os.utime(target, (0, 0))
    write_heartbeat(target)
    assert target.stat().st_mtime > 0


def test_check_heartbeat_missing_stale_and_boundary(tmp_path: Path) -> None:
    """文件缺失 / 超时判不健康；年龄等于阈值仍算新鲜。"""
    target = tmp_path / "beat"
    assert heartbeat_age(target) is None
    assert check_heartbeat(target) is False

    write_heartbeat(target)
    assert check_heartbeat(target, timeout_seconds=30) is True

    os.utime(target, (0, 0))
    assert check_heartbeat(target, timeout_seconds=30) is False

    modified = target.stat().st_mtime
    assert check_heartbeat(target, timeout_seconds=0, now=modified) is True


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：缺失 / 超时退出 1，健康退出 0，并给出原因。"""
    target = tmp_path / "beat"
    assert main(ConcurrentStableList(["--path", str(target)])) == 1
    assert "不存在" in capsys.readouterr().err

    write_heartbeat(target)
    assert main(ConcurrentStableList(["--path", str(target), "--check"])) == 0

    os.utime(target, (0, 0))
    assert main(ConcurrentStableList(["--path", str(target), "--timeout", "1"])) == 1
    assert "超时" in capsys.readouterr().err


def test_main_reads_sys_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """不传 argv 时取 `sys.argv`（容器健康检查的实际调用形态）。"""
    target = tmp_path / "beat"
    write_heartbeat(target)
    monkeypatch.setattr("sys.argv", ["heartbeat", "--path", str(target)])
    assert main() == 0


def test_module_entrypoint_runs_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`python -m bms_core.jobs.heartbeat` 入口执行检查并以退出码返回（容器健康检查的实际形态）。"""
    target = tmp_path / "beat"
    write_heartbeat(target)
    monkeypatch.setattr(sys, "argv", ["heartbeat", "--path", str(target)])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("bms_core.jobs.heartbeat", run_name="__main__")
    assert excinfo.value.code == 0


def test_parser_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """路径 / 超时可经 `BMS_JOBS__HEARTBEAT_*` 覆盖。"""
    monkeypatch.setenv("BMS_JOBS__HEARTBEAT_PATH", "/tmp/custom-beat")
    monkeypatch.setenv("BMS_JOBS__HEARTBEAT_TIMEOUT_SECONDS", "12.5")
    args = hb.build_parser().parse_args([])
    assert args.path == "/tmp/custom-beat"
    assert args.timeout == 12.5


def test_job_settings_defaults_match_heartbeat_constants() -> None:
    """`[jobs]` 默认值与心跳模块常量一致（防两处默认值漂移）。"""
    settings = JobSettings()
    assert settings.heartbeat_path == DEFAULT_HEARTBEAT_PATH
    assert settings.heartbeat_timeout_seconds == DEFAULT_HEARTBEAT_TIMEOUT_SECONDS


def test_job_settings_rejects_timeout_not_greater_than_poll() -> None:
    """心跳超时须大于轮询间隔，否则配置校验直接报错。"""
    with pytest.raises(ValidationError):
        JobSettings(poll_interval_seconds=10, heartbeat_timeout_seconds=10)
