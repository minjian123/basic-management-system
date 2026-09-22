"""CI 模块注册校验脚本测试（Kiwi 28）。"""

import pytest

import ops.check_modules as check_modules


@pytest.mark.kiwi_id(28)
def test_check_modules_passes() -> None:
    """平台域占位清单：校验通过、退出码 0。"""
    assert check_modules.main([]) == 0


@pytest.mark.kiwi_id(28)
def test_check_modules_fails_on_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """冲突清单：打印明细、退出码 1。"""

    class BadRegistry:
        """返回冲突明细的测试替身。"""

        def validate(self) -> list[str]:
            """返回固定冲突明细。"""
            return ["table_prefix 重复：pur_"]

    monkeypatch.setattr(check_modules, "ModuleRegistry", BadRegistry)
    assert check_modules.main([]) == 1
