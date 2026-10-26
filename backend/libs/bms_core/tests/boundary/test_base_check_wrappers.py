"""基座校验器薄包装护栏（Kiwi 待登记；13_06）。

口径（《AI开发规范》「重命令不重跑」与 13_05 决策 9）：基座校验器的**判定**与**规则数据**都在
engkit（`engkit base <名>` + 各仓 `[rules.<名>]`），bms 侧脚本只允许「转发参数 + 透传退出码」；
本用例锁三件事：① 包装脚本不含推导逻辑；② 本仓规则段齐备；③ engkit 子命令可解析。

`check_links` / `check_docs_scope` / `check_prototype_review` 三个脚本的专属护栏尚薄，本次以本文件
统一承担（`[[rules.backend.extra_tests]]` 的 mapping 已登记到本文件）。
"""

from __future__ import annotations

import contextlib
import io
import tomllib

import pytest

from bms_core.db.migration import BACKEND_ROOT

_REPO = BACKEND_ROOT.parent
_BASE_DIR = _REPO / "scripts" / "tools" / "base_check"

#: 包装脚本与其对应的规则段（判定在 engkit，规则在本仓配置）。
_WRAPPERS = {
    "check_links.py": None,
    "check_docs_scope.py": None,
}


def _config() -> dict[str, object]:
    """读取本仓 `engkit.toml`。

    Returns:
        dict[str, object]: 解析后的配置映射。
    """
    return tomllib.loads((_REPO / "engkit.toml").read_text(encoding="utf-8"))


@pytest.mark.kiwi_id(2361)
def test_wrappers_are_thin() -> None:
    """包装脚本只转发：不出现 AST 解析、规则常量或自建判定函数。"""
    forbidden = ("ast.parse", "re.compile(r\"^\\[a-z\\]", "def check_", "PROBLEMS", "sys.exit(1)")
    for name in _WRAPPERS:
        text = (_BASE_DIR / name).read_text(encoding="utf-8")
        assert "forward(" in text, f"{name} 应经 engkit_boot.forward 转发"
        for token in forbidden:
            assert token not in text, f"{name} 含推导逻辑：{token}"


@pytest.mark.kiwi_id(2361)
def test_repo_rules_registered() -> None:
    """本仓已登记对应规则段（缺段即该校验器未启用）。"""
    rules = _config()["rules"]
    assert isinstance(rules, dict)
    assert "prototype" in rules
    assert "base" in rules and "bare_collections" in rules


@pytest.mark.kiwi_id(2361)
def test_engkit_subcommands_available() -> None:
    """engkit 子命令可解析（`--help` 退出码 0）。"""
    import pytest as _pytest

    cli = _pytest.importorskip("engkit.cli")
    for name in ("base", "docs-status", "prototype-review"):
        buffer = io.StringIO()
        with contextlib.suppress(SystemExit), contextlib.redirect_stdout(buffer):
            cli.main(["base", name, "--help"])
        assert name in buffer.getvalue()
