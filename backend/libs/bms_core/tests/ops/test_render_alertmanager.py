"""Alertmanager 配置渲染脚本测试（Kiwi 2183）：条件通道 / 缺参跳过 / 幂等与 --check。

渲染脚本以 importlib 直接加载（与 `test_boundary_metrics.py` 同模式），只调用其纯函数与 `main`；
`ALERTMANAGER_*` 进程环境变量在本文件内一律清除，渲染结果只由显式传入的 `.env` 内容决定。
"""

import importlib.util
import os
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "observability" / "render_alertmanager.py"
_spec = importlib.util.spec_from_file_location("render_alertmanager", _SCRIPT)
assert _spec is not None and _spec.loader is not None
render_alertmanager = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_alertmanager)

_TEMPLATE = _REPO_ROOT / "deploy" / "observability" / "alertmanager.yml.tmpl"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """清除进程内的 `ALERTMANAGER_*` 变量（避免环境差异影响断言）。"""
    for key in list(os.environ):
        if key.startswith("ALERTMANAGER_"):
            monkeypatch.delenv(key)


def _render(values: dict[str, str]) -> dict[str, Any]:
    """渲染模板并解析为字典（断言用）。"""
    text = render_alertmanager.render(_TEMPLATE.read_text(encoding="utf-8"), values)
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)


def _receiver_keys(config: dict[str, Any], name: str) -> list[str]:
    """取指定 receiver 的配置键（除 name 外）。"""
    receiver = next(item for item in config["receivers"] if item["name"] == name)
    return sorted(key for key in receiver if key != "name")


@pytest.mark.kiwi_id(2183)
def test_no_credentials_renders_noop_receivers() -> None:
    """无凭据：receiver 无通道配置（no-op，告警仅 Alertmanager UI 可见），路由与抑制结构齐备。"""
    config = _render({})
    assert [(item["name"], _receiver_keys(config, item["name"])) for item in config["receivers"]] == [
        ("default", []),
        ("critical", []),
    ]
    assert "smtp_smarthost" not in config.get("global", {})
    assert config["route"]["receiver"] == "default"
    assert config["route"]["routes"][0]["receiver"] == "critical"
    assert config["inhibit_rules"][0]["equal"] == ["alertname", "service"]


@pytest.mark.kiwi_id(2183)
def test_email_and_webhook_channels() -> None:
    """邮件 + webhook 凭据齐备：global SMTP / 两 receiver / 严重级 webhook 与路由。"""
    config = _render(
        {
            "ALERTMANAGER_SMTP_SMARTHOST": "smtp.example.com:587",
            "ALERTMANAGER_SMTP_FROM": "am@example.com",
            "ALERTMANAGER_SMTP_USERNAME": "am@example.com",
            "ALERTMANAGER_SMTP_PASSWORD": "secret",
            "ALERTMANAGER_EMAIL_TO": "ops@example.com",
            "ALERTMANAGER_WECOM_WEBHOOK_URL": "https://qyapi.example.com/hook?key=xxx",
            "ALERTMANAGER_DINGTALK_WEBHOOK_URL": "https://oapi.example.com/robot/send?access_token=yyy",
        }
    )
    assert config["global"]["smtp_smarthost"] == "smtp.example.com:587"
    assert config["global"]["smtp_auth_username"] == "am@example.com"
    assert config["global"]["smtp_auth_password"] == "secret"
    assert _receiver_keys(config, "default") == ["email_configs"]
    assert _receiver_keys(config, "critical") == ["email_configs", "webhook_configs"]
    default = next(item for item in config["receivers"] if item["name"] == "default")
    assert default["email_configs"][0]["to"] == "ops@example.com"
    critical = next(item for item in config["receivers"] if item["name"] == "critical")
    urls = [item["url"] for item in critical["webhook_configs"]]
    assert urls == [
        "https://qyapi.example.com/hook?key=xxx",
        "https://oapi.example.com/robot/send?access_token=yyy",
    ]


@pytest.mark.kiwi_id(2183)
def test_email_skipped_without_recipient(capsys: pytest.CaptureFixture[str]) -> None:
    """SMTP 主机已配置但缺发件人 / 收件人：邮件跳过（输出提示），其余结构仍可渲染。"""
    config = _render({"ALERTMANAGER_SMTP_SMARTHOST": "smtp.example.com:587"})
    assert _receiver_keys(config, "default") == []
    assert "邮件通道跳过" in capsys.readouterr().out


@pytest.mark.kiwi_id(2183)
def test_main_idempotent_and_check(tmp_path: Path) -> None:
    """`main` 渲染幂等（同输入同输出）；`--check` 一致退 0、产物缺失退 1。"""
    env_file = tmp_path / ".env"
    env_file.write_text("ALERTMANAGER_EMAIL_TO=ops@example.com\n", encoding="utf-8")
    out = tmp_path / "rendered" / "alertmanager.yml"
    args = ["--env-file", str(env_file), "--template", str(_TEMPLATE), "--out", str(out)]

    assert render_alertmanager.main(args) == 0
    first = out.read_text(encoding="utf-8")
    assert render_alertmanager.main(args) == 0
    assert out.read_text(encoding="utf-8") == first
    assert render_alertmanager.main(["--check", *args]) == 0

    out.unlink()
    assert render_alertmanager.main(["--check", *args]) == 1
