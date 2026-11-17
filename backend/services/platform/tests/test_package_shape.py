"""服务包形态护栏：域出口可导入（D2 唯一跨域引用面）。

只断言**本任务所属域**的出口形态与导出清单；平台其余域的 `public.py` 是否声明 `__all__`
不属本任务范围（既有缺口未收口，故不对全量域做强制断言）。
"""

from typing import cast

from tests_support.package_shape import domain_exports

_FORM_DESIGN_EXPORTS = (
    "EffectiveLayoutView",
    "ExtFieldSummary",
    "FieldSpec",
    "FormMetadataPort",
    "ImportColumn",
    "ImportColumnProvider",
    "OptionSetPort",
    "PermissionPort",
)


def test_domain_exports_importable() -> None:
    """每个域都有可导入的公共出口；表单定制域另须导出登记清单内全部符号。"""
    exports = domain_exports("bms_platform")
    assert "bms_platform.domains.form_design.public" in exports
    public = exports["bms_platform.domains.form_design.public"]
    exported = cast("list[str]", public.__all__)
    assert isinstance(exported, list)
    assert exported == list(_FORM_DESIGN_EXPORTS)
    for name in _FORM_DESIGN_EXPORTS:
        assert getattr(public, name, None) is not None, name
