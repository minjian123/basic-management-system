"""服务包形态护栏：域出口可导入、模型清单可解析（D2 / 迁移链依赖）。"""

from bms_txn.models import MODEL_MODULES
from tests_support.package_shape import domain_exports, model_modules


def test_domain_exports_importable() -> None:
    """每个域都有可导入的公共出口，且 `__all__` 为内置 list（D2 唯一跨域引用面）。"""
    exports = domain_exports("bms_txn")
    assert "bms_txn.domains.txn.public" in exports
    for name, module in exports.items():
        assert isinstance(module.__all__, list), name


def test_model_manifest_resolvable() -> None:
    """模型清单按迁移链入口解析成功，且与 `MODEL_MODULES` 声明一致。"""
    assert list(model_modules("txn")) == [str(name) for name in MODEL_MODULES]
