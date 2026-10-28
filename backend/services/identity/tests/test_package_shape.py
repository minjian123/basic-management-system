"""服务包形态护栏：域出口可导入（D2 唯一跨域引用面）。

本服务无私有模型（`models` 子包不存在，共享模型下沉后由 `bms_core.models` 承载），故不覆盖模型清单。
"""

from tests_support.package_shape import domain_exports


def test_domain_exports_importable() -> None:
    """每个域都有可导入的公共出口，且 `__all__` 为内置 list。"""
    exports = domain_exports("bms_identity")
    assert {
        "bms_identity.domains.auth.public",
        "bms_identity.domains.identity_federation.public",
    } <= set(exports)
    for name, module in exports.items():
        assert isinstance(module.__all__, list), name
