"""服务边界度量采集脚本测试（Kiwi 2171）：静态计数 / 运行期降级 / 违规退码。"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "governance" / "boundary_metrics.py"
_spec = importlib.util.spec_from_file_location("boundary_metrics", _SCRIPT)
assert _spec is not None and _spec.loader is not None
boundary_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(boundary_metrics)


@pytest.mark.kiwi_id(2171)
def test_scrape_runtime_degrades_without_url() -> None:
    """未配置指标端点时降级标注。"""
    result = boundary_metrics.scrape_runtime(None)
    assert result["available"] is False
    assert "reason" in result


@pytest.mark.kiwi_id(2171)
def test_run_static_on_clean_repo() -> None:
    """真实仓库静态校验无越界并返回计数与明细键。"""
    result = boundary_metrics.run_static(_REPO_ROOT)
    assert "error" not in result
    counts = result["counts"]
    assert counts["cross_service_access_violation"] == 0
    assert counts["table_name_conflict"] == 0


@pytest.mark.kiwi_id(2171)
def test_violation_counts_and_fail_flag(tmp_path: Path) -> None:
    """临时仓库构造跨服务库访问 → 计数非零、--fail-on-violation 退码 1。"""
    service = tmp_path / "backend" / "services" / "org" / "src" / "bms_org"
    service.mkdir(parents=True)
    (service / "__init__.py").write_text("", encoding="utf-8")
    (service / "repository.py").write_text('SQL = "select * from sys_dict_type"\n', encoding="utf-8")

    result = boundary_metrics.run_static(tmp_path)
    assert result["counts"]["cross_service_access_violation"] >= 1
    assert boundary_metrics.main(["--root", str(tmp_path), "--fail-on-violation"]) == 1
    assert boundary_metrics.main(["--root", str(tmp_path)]) == 0
