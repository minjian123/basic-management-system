"""null.py 拆分迁移护栏测试（Kiwi 532 + 05 扩量）：42 类落点 / 旧路径不可用 / 语义与登记不变。"""

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import app as app_pkg
from app.core.capability import BaseNullObject
from app.core.plugin import BasePluggable, PluginRegistry

_BACKEND = Path(__file__).resolve().parents[2]

# (原模块, 目标 null 模块, 类名)
_MIGRATED: list[tuple[str, str, str]] = [
    ("app.archive.base", "app.archive.null", "NullArchivePolicy"),
    ("app.archive.base", "app.archive.null", "NullArchiveQueryRouter"),
    ("app.audit.hashchain", "app.audit.null", "NullHashChain"),
    ("app.captcha.base", "app.captcha.null", "NullCaptcha"),
    ("app.circuit.base", "app.circuit.null", "NullCircuitBreaker"),
    ("app.dashboard.base", "app.dashboard.null", "NullDashboardCardRegistry"),
    ("app.db.unit_of_work", "app.db.null", "NullUnitOfWork"),
    ("app.fallback.base", "app.fallback.null", "NullFallbackPolicy"),
    ("app.fieldtype.base", "app.fieldtype.null", "NullFieldTypeRegistry"),
    ("app.health.base", "app.health.null", "NullHealthCheckRegistry"),
    ("app.i18n.base", "app.i18n.null", "NullTranslator"),
    ("app.idempotency.base", "app.idempotency.null", "NullIdempotencyStore"),
    ("app.idp.base", "app.idp.null", "NullIdentityProvider"),
    ("app.llm.base", "app.llm.null", "NullLlmProvider"),
    ("app.lock.base", "app.lock.null", "NullDistributedLock"),
    ("app.masking.base", "app.masking.null", "NullMasker"),
    ("app.metrics.base", "app.metrics.null", "NullMetrics"),
    ("app.notify.base", "app.notify.null", "NullNotifier"),
    ("app.oauth.base", "app.oauth.null", "NullOAuthServer"),
    ("app.oauth.base", "app.oauth.null", "NullScopeChecker"),
    ("app.outbound.http", "app.outbound.null", "NullHttpClient"),
    ("app.outbound.webhook", "app.outbound.null", "NullWebhookSender"),
    ("app.password.base", "app.password.null", "NullPasswordPolicy"),
    ("app.permission.base", "app.permission.null", "NullPermissionChecker"),
    ("app.query.base", "app.query.null", "NullQueryProvider"),
    ("app.query.base", "app.query.null", "NullQueryProviderRegistry"),
    ("app.ratelimit.base", "app.ratelimit.null", "NullRateLimiter"),
    ("app.replay.base", "app.replay.null", "NullReplayGuard"),
    ("app.scope.base", "app.scope.null", "NullDataScope"),
    ("app.search.base", "app.search.null", "NullSearchIndex"),
    ("app.session.base", "app.session.null", "NullSessionStore"),
    ("app.sharding.base", "app.sharding.null", "NullShardingRouter"),
    ("app.storage.base", "app.storage.null", "NullObjectStorage"),
    ("app.tracing.base", "app.tracing.null", "NullTracer"),
    ("app.transfer.exporter", "app.transfer.null", "NullExporter"),
    ("app.transfer.importer", "app.transfer.null", "NullImporter"),
    ("app.workflow.base", "app.workflow.null", "NullWorkflowEngine"),
    ("app.ws.base", "app.ws.null", "NullRealtimePublisher"),
]


def _import_all() -> None:
    """导入 app 包全部模块（缓存命中后极快）。"""
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)


def _null_class_defs() -> list[tuple[str, str]]:
    """扫描 app/**/*.py 中定义的 Null* 类，返回 (相对路径, 类名)。"""
    found: list[tuple[str, str]] = []
    for path in sorted((_BACKEND / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Null"):
                found.append((str(path.relative_to(_BACKEND)), node.name))
    return found


@pytest.mark.kiwi_id(532)
def test_no_null_class_outside_null_modules() -> None:
    """落点护栏：`null.py` 之外模块不得定义 `Null*` 类。"""
    defs = _null_class_defs()
    assert len(defs) == 42
    offenders = [(path, name) for path, name in defs if not path.endswith("null.py")]
    assert not offenders, offenders


@pytest.mark.kiwi_id(532)
def test_migrated_classes_importable_and_old_paths_removed() -> None:
    """42 类可自 `app.<domain>.null` 导入且 `__module__` 指向 null 模块；旧路径不可用。"""
    _import_all()
    for old_module, null_module, name in _MIGRATED:
        module = importlib.import_module(null_module)
        cls = getattr(module, name)
        assert isinstance(cls, type)
        assert cls.__module__ == null_module
        assert issubclass(cls, BaseNullObject)
        assert not hasattr(importlib.import_module(old_module), name)


@pytest.mark.kiwi_id(532)
def test_registration_semantics_unchanged() -> None:
    """语义与登记不变：Null 仍为端口子类，注册快照的 `null` 实现均来自 `null` 模块。"""
    _import_all()
    registry = PluginRegistry()
    for cls in BasePluggable.__subclasses__():
        pending = [cls]
        while pending:
            current = pending.pop()
            if current.__module__.startswith("app."):
                registry.collect(current)
            pending.extend(current.__subclasses__())
    snapshot = registry.build()
    assert "object_storage" in snapshot
    assert snapshot["object_storage"]["null"] is importlib.import_module("app.storage.null").NullObjectStorage
    for key, bucket in snapshot.items():
        for name, impl in bucket.items():
            if name == "null":
                assert isinstance(impl, type)
                assert impl.__module__.endswith(".null"), (key, impl)
