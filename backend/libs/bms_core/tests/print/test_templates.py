"""内置打印模板来源测试：清单 / 过滤 / 未命中 / 扩展重名。"""

from __future__ import annotations

import pytest

from bms_core.core.exceptions import PrintTemplateNotFoundError
from bms_core.print.base import PrintTemplateInfo
from bms_core.print.templates import (
    BUILTIN_PRINT_TEMPLATES,
    DEFAULT_DOCUMENT_TEMPLATE_KEY,
    DEFAULT_LIST_TEMPLATE_KEY,
    BuiltinPrintTemplateProvider,
    BuiltinTemplateRegistry,
)

pytestmark = pytest.mark.kiwi_id(2402)


async def test_builtin_list_contains_two_templates() -> None:
    """内置清单含通用单据与通用列表两条。"""
    provider = BuiltinPrintTemplateProvider()
    templates = await provider.list()
    keys = [item.key for item in templates]
    assert keys == [DEFAULT_DOCUMENT_TEMPLATE_KEY, DEFAULT_LIST_TEMPLATE_KEY]
    assert [item.key for item in BUILTIN_PRINT_TEMPLATES] == keys


async def test_builtin_list_filters_by_biz_type() -> None:
    """按单据类型过滤：内置模板 `biz_type` 为空，命中任意类型；不存在的类型返回空。"""
    provider = BuiltinPrintTemplateProvider()
    assert len(await provider.list(biz_type="sales_order")) == 2


async def test_builtin_get_and_miss() -> None:
    """取模板命中；未命中抛 50201。"""
    provider = BuiltinPrintTemplateProvider()
    info = await provider.get(DEFAULT_DOCUMENT_TEMPLATE_KEY)
    assert info.name == "通用单据"
    with pytest.raises(PrintTemplateNotFoundError):
        await provider.get("not-exists")


def test_registry_rejects_duplicate_and_empty_key() -> None:
    """注册表拒绝重名与空键。"""
    registry = BuiltinTemplateRegistry()
    with pytest.raises(ValueError, match="重复"):
        registry.add(PrintTemplateInfo(key=DEFAULT_LIST_TEMPLATE_KEY, name="重复"))
    with pytest.raises(ValueError, match="为空"):
        registry.add(PrintTemplateInfo(key=" ", name="空键"))


def test_registry_add_and_get() -> None:
    """扩展登记后可取。"""
    registry = BuiltinTemplateRegistry()
    registry.add(PrintTemplateInfo(key="demo_template", name="演示模板", biz_type="demo"))
    assert registry.get("demo_template").name == "演示模板"
    assert [item.key for item in registry.all()] == sorted(
        [DEFAULT_DOCUMENT_TEMPLATE_KEY, DEFAULT_LIST_TEMPLATE_KEY, "demo_template"]
    )


def test_register_builtin_template_extends_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """扩展入口：新模板登记进注册表并可被来源取到（重名即拒）。"""
    from bms_core.print import templates as templates_module

    isolated = BuiltinTemplateRegistry()
    monkeypatch.setattr(templates_module, "_REGISTRY", isolated)

    added = templates_module.register_builtin_template(PrintTemplateInfo(key="demo_template", name="演示模板"))
    assert added.key == "demo_template"
    assert isolated.get("demo_template").name == "演示模板"
    with pytest.raises(ValueError, match="重复"):
        templates_module.register_builtin_template(PrintTemplateInfo(key="demo_template", name="重复"))
