"""登记面命名形态护栏（Kiwi 2351）：真实仓库零问题、自检 6 例（1 正例 + 4 反例 + 中文名豁免）全通过。

护栏实现见 `scripts/tools/base_check/check_base.py` 第 6 项 `naming_problems`（只扫登记面——
工具目录与脚本名、前端包目录与包名、迁移清单目录；不扫源码文本 / 注释 / 前端路由 / CSS / 文档）。
本用例以 importlib 直接加载脚本调用纯函数，口径见 01_07 详细设计 §3.4 / §4 用例 1~6。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "base_check" / "check_base.py"
_spec = importlib.util.spec_from_file_location("check_base", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_base)


@pytest.mark.kiwi_id(2351)
def test_naming_clean_on_repo() -> None:
    """真实仓库登记面零问题：无连字符工具目录 / 脚本名 / 包目录 / 包名 / 清单目录。"""
    assert check_base.naming_problems(_REPO_ROOT) == []


@pytest.mark.kiwi_id(2351)
def test_naming_self_test_cases() -> None:
    """自检 6 例全部符合预期（反例均被拦、中文名脚本豁免、正例通过）。"""
    assert check_base.naming_self_test() == 0


@pytest.mark.kiwi_id(2351)
def test_naming_regex_forms() -> None:
    """形态判定本身：snake_case 通过、连字符与大写开头被拒（判据不随实现漂移）。"""
    assert check_base.DIR_IDENT_RE.match("ui_ep")
    assert not check_base.DIR_IDENT_RE.match("ui-ep")
    assert not check_base.DIR_IDENT_RE.match("UI_ep")
    assert check_base.SCRIPT_STEM_RE.match("check_base2")
    assert not check_base.SCRIPT_STEM_RE.match("check-base")
