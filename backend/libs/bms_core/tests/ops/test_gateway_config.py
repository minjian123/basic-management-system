"""网关声明式配置 CLI 测试（render / check 零漂移）。Kiwi 2165。"""

import runpy
import sys
from pathlib import Path

import pytest

from bms_core.services.gateway_catalog import render_apisix_yaml
from ops import gateway_config


@pytest.mark.kiwi_id(2165)
def test_render_and_check_roundtrip(tmp_path: Path) -> None:
    """render 写出生成件；check 对生成件通过（零漂移）。"""
    assert gateway_config.main(["render", "--root", str(tmp_path)]) == 0
    assert gateway_config.config_path(tmp_path).read_text(encoding="utf-8") == render_apisix_yaml()
    assert gateway_config.main(["check", "--root", str(tmp_path)]) == 0


@pytest.mark.kiwi_id(2165)
def test_render_print_outputs_content(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """render --print 打印生成内容，同时写出文件。"""
    assert gateway_config.main(["render", "--print", "--root", str(tmp_path)]) == 0
    assert render_apisix_yaml() in capsys.readouterr().out
    assert gateway_config.config_path(tmp_path).is_file()


@pytest.mark.kiwi_id(2165)
def test_check_missing_file_fails(tmp_path: Path) -> None:
    """生成件缺失时 check 退出码非 0。"""
    assert gateway_config.main(["check", "--root", str(tmp_path)]) == 1


@pytest.mark.kiwi_id(2165)
def test_check_drift_fails(tmp_path: Path) -> None:
    """生成件被篡改（与服务目录漂移）时 check 退出码非 0。"""
    target = gateway_config.config_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_apisix_yaml().replace("platform", "platform-x"), encoding="utf-8")
    assert gateway_config.main(["check", "--root", str(tmp_path)]) == 1


@pytest.mark.kiwi_id(2165)
def test_committed_config_in_sync() -> None:
    """仓库内 deploy/gateway/apisix.yaml 与服务目录零漂移。"""
    assert gateway_config.check(gateway_config.REPO_ROOT) == 0


@pytest.mark.kiwi_id(2165)
def test_module_main_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.gateway_config` 入口（__main__ 守卫）可执行。"""
    assert gateway_config.render(tmp_path) == 0
    monkeypatch.setattr(sys, "argv", ["gateway_config", "check", "--root", str(tmp_path)])
    monkeypatch.delitem(sys.modules, "ops.gateway_config", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ops.gateway_config", run_name="__main__")
    assert excinfo.value.code == 0
