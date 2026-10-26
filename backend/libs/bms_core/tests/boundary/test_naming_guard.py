"""登记面命名形态护栏的调用面（Kiwi 2351 / 2357）：包装可跑、规则齐备。

判定与自检向量已随 13_06 迁入 engkit（`engkit base base`，其 `--self-test` 覆盖 12 例：登记面 6 例 +
运行期登记值 6 例）；本用例只锁**本仓调用面**——脚本能按原命令跑通、规则段齐备、退出码不变。
"""

from __future__ import annotations

import subprocess
import sys
import tomllib

import pytest

from bms_core.db.migration import BACKEND_ROOT

_REPO = BACKEND_ROOT.parent
_SCRIPT = _REPO / "scripts" / "tools" / "base_check" / "check_base.py"


@pytest.mark.kiwi_id(2351)
def test_naming_guard_clean_on_repo() -> None:
    """真实仓库跑包装：登记面零问题（退出码 0）。"""
    completed = subprocess.run([sys.executable, str(_SCRIPT), str(_REPO)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.kiwi_id(2357)
def test_naming_rules_registered() -> None:
    """规则数据在本仓 `engkit.toml`（判定在 engkit，脚本不含规则）。"""
    config = tomllib.loads((_REPO / "engkit.toml").read_text(encoding="utf-8"))
    rules = config["rules"]["base"]
    assert rules["manifest"].startswith("bms文档/")
    assert rules["naming"]["tool_root"] == "scripts/tools"
    assert len(rules["runtime"]) >= 4


@pytest.mark.kiwi_id(2351)
def test_wrapper_has_no_rules() -> None:
    """包装脚本不含推导逻辑（不出现正则常量与判定函数）。"""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "engkit_boot" in text
    for token in ("re.compile", "def naming_problems", "BASE_DIRS"):
        assert token not in text
