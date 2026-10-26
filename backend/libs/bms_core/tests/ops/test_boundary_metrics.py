"""服务边界度量采集（薄包装）测试（Kiwi 2171）：CLI 级断言。

13_06 起采集与判定都在 engkit（`base boundary-metrics` + `base service-boundaries`，规则落本仓
`engkit.toml` 的 `[rules.metrics]` / `[rules.service_boundaries]`），本仓脚本只转发参数与退出码。
故本用例按 **命令行行为** 断言：真实仓库采集通过、`--out` 四段结构、指标端点不可达降级、
登记源缺失降级、包装零逻辑与规则段齐备——不再直接加载脚本内部函数（实现已不在本仓）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from bms_core.db.migration import BACKEND_ROOT

_REPO = BACKEND_ROOT.parent
_SCRIPT = _REPO / "scripts" / "tools" / "governance" / "boundary_metrics.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """运行采集薄包装（命令行行为即契约）。

    Args:
        *args: 传给脚本的参数。

    Returns:
        subprocess.CompletedProcess[str]: 运行结果（UTF-8 解码）。
    """
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.kiwi_id(2171)
def test_collect_on_repo() -> None:
    """真实仓库采集：退码 0，静态 / 例外 / 域级 / 运行时四类结论行齐备。"""
    result = _run("--root", str(_REPO))
    assert result.returncode == 0, result.stderr
    assert "服务边界与跨库访问度量" in result.stdout
    assert "服务边界越界数 0" in result.stdout
    assert "例外白名单：登记" in result.stdout
    assert "域级：布局登记文件" in result.stdout
    assert "运行时：未采集（未配置 --metrics-url" in result.stdout


@pytest.mark.kiwi_id(2171)
def test_out_json_structure(tmp_path: Path) -> None:
    """`--out` 落盘 JSON 四段结构（collected_at / static / runtime / summary）。"""
    target = tmp_path / "boundary.json"
    result = _run("--root", str(_REPO), "--out", str(target))
    assert result.returncode == 0, result.stderr
    assert f"已写入 JSON：{target}" in result.stdout
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert set(payload) == {"collected_at", "static", "runtime", "summary"}
    assert payload["static"]["passed"] is True
    assert payload["static"]["problems"] == []
    assert isinstance(payload["static"]["counts"], dict)
    assert payload["runtime"]["available"] is False
    assert payload["summary"]["boundary_violations"] == 0
    assert payload["summary"]["cross_db_access"] == 0


@pytest.mark.kiwi_id(2171)
def test_metrics_url_unreachable_degrades() -> None:
    """指标端点不可达即降级标注（不中断采集、不改退码）。"""
    result = _run("--root", str(_REPO), "--metrics-url", "http://127.0.0.1:9/metrics")
    assert result.returncode == 0, result.stderr
    assert "运行时：未采集（指标端点不可达" in result.stdout


@pytest.mark.kiwi_id(2171)
def test_fail_on_violation_does_not_misfire() -> None:
    """`--fail-on-violation` 在零越界时不误退 1（静态越界数取自分类计数求和）。"""
    result = _run("--root", str(_REPO), "--fail-on-violation")
    assert result.returncode == 0, result.stderr
    assert "服务边界越界数 0" in result.stdout


@pytest.mark.kiwi_id(2171)
def test_wrapper_is_thin_and_rules_registered() -> None:
    """包装只转发（无采集 / 判定逻辑），且本仓度量规则段齐备。"""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "forward(" in text
    for token in ("urllib", "def run_static", "def scrape_runtime", "re.compile"):
        assert token not in text, f"包装含推导 / 采集逻辑：{token}"
    rules = tomllib.loads((_REPO / "engkit.toml").read_text(encoding="utf-8"))["rules"]
    assert len(rules["metrics"]["violation_keys"]) == 13
    assert rules["metrics"]["metric_name"] == "bms_boundary_cross_access_total"
    assert "service_boundaries" in rules
