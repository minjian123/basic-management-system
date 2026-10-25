"""登记面命名形态护栏（Kiwi 2351 / 2357）：真实仓库零问题、自检 11 例全通过。

护栏实现见 `scripts/tools/base_check/check_base.py` 第 6 项：`naming_problems` 扫登记目录 / 包名 /
脚本名（Kiwi 2351），`runtime_identifier_problems` 扫运行期登记值——控件语义键、业务 / 动作码
`pattern`、自建图标码正则（Kiwi 2357，任务 `01_08`）。只扫登记面，不扫源码文本 / 注释 / 前端路由 /
CSS / 文档；本用例以 importlib 直接加载脚本调用纯函数。
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
    """自检 11 例全部符合预期（登记面 6 例 + 运行期登记值 5 例）。"""
    assert check_base.NAMING_CASES == 11
    assert check_base.naming_self_test() == 0


@pytest.mark.kiwi_id(2351)
def test_naming_regex_forms() -> None:
    """形态判定本身：snake_case 通过、连字符与大写开头被拒（判据不随实现漂移）。"""
    assert check_base.DIR_IDENT_RE.match("ui_ep")
    assert not check_base.DIR_IDENT_RE.match("ui-ep")
    assert not check_base.DIR_IDENT_RE.match("UI_ep")
    assert check_base.SCRIPT_STEM_RE.match("check_base2")
    assert not check_base.SCRIPT_STEM_RE.match("check-base")


@pytest.mark.kiwi_id(2357)
def test_runtime_identifier_clean_on_repo() -> None:
    """运行期登记值零问题：控件语义键 / 业务动作码 pattern / 自建图标码正则均为 snake_case。"""
    assert check_base.runtime_identifier_problems(_REPO_ROOT) == []


@pytest.mark.kiwi_id(2357)
def test_runtime_identifier_regex_forms() -> None:
    """运行期判据：snake_case 形态常量与 kebab 反例（判据不随实现漂移）。"""
    assert check_base.DIR_IDENT_RE.match("dict_multi")
    assert not check_base.DIR_IDENT_RE.match("dict-multi")
    assert check_base.SNAKE_PATTERN == r"^[a-z][a-z0-9_]*$"
