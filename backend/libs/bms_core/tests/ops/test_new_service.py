"""服务脚手架脚本测试（Kiwi 见任务测试记录）：生成骨架齐备且生成的服务可导入启动。"""

import importlib
import sys
from pathlib import Path

import pytest

from scripts.new_service import generate

_LAYERS = ("services", "repositories", "models", "schemas")


@pytest.mark.kiwi_id(1204)
def test_generate_creates_full_skeleton(tmp_path: Path) -> None:
    """生成目录齐备：pyproject + 五层 + 入口 + 冒烟用例。"""
    project = generate("payment", "收付款", base=tmp_path)
    package = project / "src" / "bms_payment"
    assert (project / "pyproject.toml").is_file()
    assert (package / "__init__.py").is_file()
    assert (package / "main.py").is_file()
    assert (package / "asgi.py").is_file()
    assert (package / "api" / "router.py").is_file()
    for layer in _LAYERS:
        assert (package / layer / "__init__.py").is_file()
    assert (project / "tests" / "test_service_boot.py").is_file()
    assert 'name = "bms-payment"' in (project / "pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.kiwi_id(1204)
def test_generated_service_imports_and_boots(tmp_path: Path) -> None:
    """生成的 `bms_<名>` 可导入并构造应用（依赖 `bms_core` 真实解析）。"""
    generate("payment", "收付款", base=tmp_path)
    src = str(tmp_path / "payment" / "src")
    sys.path.insert(0, src)
    try:
        module = importlib.import_module("bms_payment.main")
        app = module.ApplicationFactory().create(None)
        assert "收付款" in app.title
    finally:
        sys.path.remove(src)
        for name in [key for key in sys.modules if key == "bms_payment" or key.startswith("bms_payment.")]:
            del sys.modules[name]


@pytest.mark.kiwi_id(1204)
def test_invalid_or_duplicate_name_rejected(tmp_path: Path) -> None:
    """非法名 / 保留名 / 重名即拒绝。"""
    with pytest.raises(ValueError, match="服务名非法"):
        generate("Bad-Name", "坏名", base=tmp_path)
    with pytest.raises(ValueError, match="服务名保留"):
        generate("platform", "平台", base=tmp_path)
    generate("payment", "收付款", base=tmp_path)
    with pytest.raises(ValueError, match="已存在"):
        generate("payment", "收付款", base=tmp_path)
