"""集合声明护栏的调用面（Kiwi 2213 / 2326）：包装可跑、规则齐备、基线有效。

判定矩阵与自检向量已随 13_06 迁入 engkit（`engkit base bare-collections --self-test`）；本用例只锁
**本仓调用面**：原命令跑通、白名单 / 基线在配置里、包装不含判定逻辑。
"""

from __future__ import annotations

import subprocess
import sys
import tomllib

import pytest

from bms_core.db.migration import BACKEND_ROOT

_REPO = BACKEND_ROOT.parent
_SCRIPT = _REPO / "scripts" / "tools" / "base_check" / "check_bare_collections.py"


@pytest.mark.kiwi_id(2213)
def test_guard_passes_on_repo() -> None:
    """真实仓库跑包装：集合声明无新增违规（退出码 0）。"""
    completed = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_REPO)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.kiwi_id(2326)
def test_rules_registered_in_config() -> None:
    """白名单 / 判违规形态 / 基线均在本仓配置（脚本内不再出现仓专属字面）。"""
    config = tomllib.loads((_REPO / "engkit.toml").read_text(encoding="utf-8"))
    rules = config["rules"]["bare_collections"]
    assert "ConcurrentStableList" in rules["whitelist"]
    assert "list" in rules["banned"]["bare"]
    assert rules["baseline"] == "deploy/boundaries/bare_collections_baseline.json"
    assert rules["baseline_version"] == 1


@pytest.mark.kiwi_id(2213)
def test_wrapper_is_thin() -> None:
    """包装脚本只转发（无 AST 扫描与基线比对实现）。"""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "engkit_boot" in text
    for token in ("ast.walk", "write_baseline", "BARE_CONTAINERS"):
        assert token not in text
