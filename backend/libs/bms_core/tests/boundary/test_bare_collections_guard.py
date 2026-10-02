"""裸无序集合护栏归零回归（Kiwi 2224）：全链集合声明零命中、基线条目归零、护栏复跑「新增 0 / 残留 0」。

护栏脚本以 importlib 直接加载（与 `tests/ops/test_render_alertmanager.py` 同模式），只调用其 `collect`
与 `check` 并读取基线快照；断言口径见 08_02 详细设计 §5 用例 3（存量归零与护栏收紧）。
"""

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "base-check" / "check-bare-collections.py"
_spec = importlib.util.spec_from_file_location("check_bare_collections", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_bare_collections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_bare_collections)

_BASELINE = _REPO_ROOT / "deploy" / "boundaries" / "bare_collections_baseline.json"


@pytest.mark.kiwi_id(2224)
def test_bare_collections_hits_zero() -> None:
    """存量归零：全链（`libs` / `services` / `ops` / `scripts/tools`）集合声明命中 0 处（各区域均为 0）。"""
    assert len(check_bare_collections.collect(_REPO_ROOT)) == 0


@pytest.mark.kiwi_id(2224)
def test_bare_collections_baseline_zero() -> None:
    """基线台账归零：`bare_collections_baseline.json` 条目计数合计为 0（无残留）。"""
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    entries = payload["entries"]
    assert sum(int(entry["count"]) for entry in entries) == 0


@pytest.mark.kiwi_id(2224)
def test_bare_collections_check_clean() -> None:
    """护栏复跑：`check` 无问题，新增 0 / 残留 0、基线条目 0。"""
    check_bare_collections.problems.clear()
    check_bare_collections.counts.clear()
    check_bare_collections.check(_REPO_ROOT)
    assert list(check_bare_collections.problems) == []
    assert check_bare_collections.counts["baseline_entries"] == 0
    assert check_bare_collections.counts["added"] == 0
    assert check_bare_collections.counts["stale"] == 0
