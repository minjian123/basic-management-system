"""打印导出装配工厂：模板来源选择（内置 / 外部 provider）与渲染器装配。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bms_core.core import assembly
from bms_core.core.assembly import StoragePrintExporterFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.print.base import BasePrintTemplateProvider
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.templates import BuiltinPrintTemplateProvider

pytestmark = pytest.mark.kiwi_id(2402)


def _settings_with_template_provider(provider: str):
    """复制全局配置并替换模板来源实现名。

    Args:
        provider: 模板来源插件名。

    Returns:
        Settings: 替换后的配置。
    """
    settings = get_settings()
    return settings.model_copy(
        update={"print_template": settings.print_template.model_copy(update={"provider": provider})}
    )


def _patch_resolver(
    monkeypatch: pytest.MonkeyPatch,
    *,
    templates: BasePrintTemplateProvider | None = None,
) -> ConcurrentStableList[str]:
    """替换插件解析：对象存储恒返回替身，模板来源按需返回替身并记录调用。

    Args:
        monkeypatch: monkeypatch 夹具。
        templates: 模板来源替身（None 表示不该解析模板来源）。

    Returns:
        ConcurrentStableList[str]: 解析调用记录（`插件键:实现名`）。
    """
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _fake(plugin_key: str, plugin_name: str, *, expected_version: str | None = None) -> object:
        calls.add(f"{plugin_key}:{plugin_name}")
        if plugin_key == "object_storage":
            return SimpleNamespace(name="storage-stub")
        assert templates is not None, "内置分支不应解析模板来源插件"
        return templates

    monkeypatch.setattr(assembly, "resolve_plugin", _fake)
    return calls


def test_factory_uses_builtin_templates_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺省（builtin）直接用内置模板来源，不经插件解析。"""
    calls = _patch_resolver(monkeypatch)
    factory = StoragePrintExporterFactory(_settings_with_template_provider("builtin"))
    exporter = factory.create()

    assert isinstance(exporter, StoragePrintExporter)
    assert list(calls) == ["object_storage:local"]


def test_factory_resolves_external_template_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置非 builtin 时经插件解析取外部模板来源（不静默回落内置）。"""
    stub: BasePrintTemplateProvider = BuiltinPrintTemplateProvider()
    calls = _patch_resolver(monkeypatch, templates=stub)
    factory = StoragePrintExporterFactory(_settings_with_template_provider("custom_templates"))
    exporter = factory.create()

    assert isinstance(exporter, StoragePrintExporter)
    assert list(calls) == ["object_storage:local", "print_template:custom_templates"]
