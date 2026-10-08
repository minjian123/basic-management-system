"""网关声明式配置 CLI 测试（render / check 零漂移 + 请求体上限三方一致）。Kiwi 2165 / 2264。"""

import runpy
import sys
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.services.gateway_catalog import render_apisix_yaml
from ops import gateway_config


def _seed_body_size(
    root: Path,
    *,
    template_variable: bool = True,
    compose_default: str | None = "32m",
    apisix_value: str = "32m",
    env_value: str = "32m",
) -> None:
    """在临时仓库根写出请求体上限四方文件（04-1-2）。

    Args:
        root: 临时仓库根。
        template_variable: 模板是否以变量化声明（False 即硬编码，用于负例）。
        compose_default: 编排缺省值（None 即不给缺省，用于负例）。
        apisix_value: APISIX 配置值。
        env_value: 环境变量模板值。
    """
    template = root / gateway_config.NGINX_TEMPLATE_RELATIVE
    template.parent.mkdir(parents=True, exist_ok=True)
    size_line = "client_max_body_size ${GATEWAY_MAX_BODY_SIZE};" if template_variable else "client_max_body_size 32m;"
    template.write_text(f"server {{\n    location /api/ {{\n        {size_line}\n    }}\n}}\n", encoding="utf-8")

    compose = root / gateway_config.COMPOSE_GATEWAY_RELATIVE
    compose.parent.mkdir(parents=True, exist_ok=True)
    default_expr = (
        f"${{GATEWAY_MAX_BODY_SIZE:-{compose_default}}}" if compose_default is not None else "${GATEWAY_MAX_BODY_SIZE}"
    )
    compose.write_text(
        f"services:\n  gateway-nginx:\n    environment:\n      GATEWAY_MAX_BODY_SIZE: {default_expr}\n",
        encoding="utf-8",
    )

    apisix = root / gateway_config.APISIX_CONFIG_RELATIVE
    apisix.write_text(f'nginx_config:\n  http:\n    client_max_body_size: "{apisix_value}"\n', encoding="utf-8")

    env_example = root / gateway_config.ENV_EXAMPLE_RELATIVE
    env_example.parent.mkdir(parents=True, exist_ok=True)
    env_example.write_text(f"GATEWAY_MAX_BODY_SIZE={env_value}\n", encoding="utf-8")


@pytest.mark.kiwi_id(2165)
def test_render_and_check_roundtrip(tmp_path: Path) -> None:
    """render 写出生成件；check 对生成件通过（零漂移 + 请求体上限三方一致）。"""
    _seed_body_size(tmp_path)
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0
    assert gateway_config.config_path(tmp_path).read_text(encoding="utf-8") == render_apisix_yaml()
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 0


@pytest.mark.kiwi_id(2165)
def test_render_print_outputs_content(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """render --print 打印生成内容，同时写出文件。"""
    assert gateway_config.main(ConcurrentStableList(["render", "--print", "--root", str(tmp_path)])) == 0
    assert render_apisix_yaml() in capsys.readouterr().out
    assert gateway_config.config_path(tmp_path).is_file()


@pytest.mark.kiwi_id(2165)
def test_check_missing_file_fails(tmp_path: Path) -> None:
    """生成件缺失时 check 退出码非 0。"""
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_check_drift_fails(tmp_path: Path) -> None:
    """生成件被篡改（与服务目录漂移）时 check 退出码非 0。"""
    target = gateway_config.config_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_apisix_yaml().replace("platform", "platform-x"), encoding="utf-8")
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_committed_config_in_sync() -> None:
    """仓库内 deploy/gateway/apisix.yaml 与服务目录零漂移。"""
    assert gateway_config.check(gateway_config.REPO_ROOT) == 0


@pytest.mark.kiwi_id(2167)
def test_check_blocks_hardcoded_ip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check 在服务发现校验失败（硬编码 IP）时退出码非 0。"""
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0

    def _fake(config: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str]:
        return ConcurrentStableList(["上游 platform 节点为硬编码 IP：10.0.0.5:8000"])

    monkeypatch.setattr(gateway_config, "validate_service_discovery", _fake)
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_module_main_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.gateway_config` 入口（__main__ 守卫）可执行。"""
    _seed_body_size(tmp_path)
    assert gateway_config.render(tmp_path) == 0
    monkeypatch.setattr(sys, "argv", ["gateway_config", "check", "--root", str(tmp_path)])
    monkeypatch.delitem(sys.modules, "ops.gateway_config", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ops.gateway_config", run_name="__main__")
    assert excinfo.value.code == 0


@pytest.mark.kiwi_id(2264)
def test_body_size_repo_passes_and_parse_size() -> None:
    """仓库内请求体上限三方一致且 ≥ 文件上传整包上限；体积字面量解析支持 k/m/g 与纯字节。"""
    assert gateway_config.validate_body_size(gateway_config.REPO_ROOT) == []

    assert gateway_config.parse_size("32m") == 32 * 1024 * 1024
    assert gateway_config.parse_size("1024k") == 1024 * 1024
    assert gateway_config.parse_size("1g") == 1024 * 1024 * 1024
    assert gateway_config.parse_size("20971520") == gateway_config.UPLOAD_MAX_SIZE_BYTES
    assert gateway_config.parse_size("32mq") is None
    assert gateway_config.parse_size("") is None


@pytest.mark.kiwi_id(2264)
def test_body_size_template_literal_rejected(tmp_path: Path) -> None:
    """边缘模板硬编码请求体上限（未变量化）即违规。"""
    _seed_body_size(tmp_path, template_variable=False)

    problems = gateway_config.validate_body_size(tmp_path)

    assert any("GATEWAY_MAX_BODY_SIZE" in item for item in problems)
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2264)
def test_body_size_cross_file_mismatch_rejected(tmp_path: Path) -> None:
    """APISIX / 环境变量模板与编排缺省值不一致即违规。"""
    _seed_body_size(tmp_path, apisix_value="24m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("APISIX 请求体上限" in item and "不一致" in item for item in problems)

    _seed_body_size(tmp_path, env_value="64m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("环境变量模板" in item for item in problems)


@pytest.mark.kiwi_id(2264)
def test_body_size_missing_default_or_below_upload_limit_rejected(tmp_path: Path) -> None:
    """编排未给缺省值、或上限低于文件上传整包上限（20MB）即违规。"""
    _seed_body_size(tmp_path, compose_default=None)
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("须为 GATEWAY_MAX_BODY_SIZE 提供缺省值" in item for item in problems)

    _seed_body_size(tmp_path, compose_default="16m", apisix_value="16m", env_value="16m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("小于文件上传整包上限 20MB" in item for item in problems)


@pytest.mark.kiwi_id(2264)
def test_check_reports_body_size_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check 在请求体上限口径违规时退出码非 0 且给出说明。"""
    _seed_body_size(tmp_path, apisix_value="8m")
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0

    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1
    assert "请求体上限校验失败" in capsys.readouterr().err
