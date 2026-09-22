"""null.py 拆分迁移护栏测试（Kiwi 532 + 05 扩量）：42 类落点 / 旧路径不可用 / 语义与登记不变。"""

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import bms_core as app_pkg
from bms_core.core.capability import BaseNullObject
from bms_core.core.plugin import BasePluggable, PluginRegistry

_BACKEND = Path(__file__).resolve().parents[4]
_CORE = _BACKEND / "libs" / "bms_core" / "src" / "bms_core"

# (原模块, 目标 null 模块, 类名)
_MIGRATED: list[tuple[str, str, str]] = [
    ("bms_core.archive.base", "bms_core.archive.null", "NullArchivePolicy"),
    ("bms_core.archive.base", "bms_core.archive.null", "NullArchiveQueryRouter"),
    ("bms_core.audit.hashchain", "bms_core.audit.null", "NullHashChain"),
    ("bms_core.captcha.base", "bms_core.captcha.null", "NullCaptcha"),
    ("bms_core.circuit.base", "bms_core.circuit.null", "NullCircuitBreaker"),
    ("bms_core.dashboard.base", "bms_core.dashboard.null", "NullDashboardCardRegistry"),
    ("bms_core.db.unit_of_work", "bms_core.db.null", "NullUnitOfWork"),
    ("bms_core.fallback.base", "bms_core.fallback.null", "NullFallbackPolicy"),
    ("bms_core.fieldtype.base", "bms_core.fieldtype.null", "NullFieldTypeRegistry"),
    ("bms_core.health.base", "bms_core.health.null", "NullHealthCheckRegistry"),
    ("bms_core.i18n.base", "bms_core.i18n.null", "NullTranslator"),
    ("bms_core.idempotency.base", "bms_core.idempotency.null", "NullIdempotencyStore"),
    ("bms_core.idp.base", "bms_core.idp.null", "NullIdentityProvider"),
    ("bms_core.llm.base", "bms_core.llm.null", "NullLlmProvider"),
    ("bms_core.lock.base", "bms_core.lock.null", "NullDistributedLock"),
    ("bms_core.masking.base", "bms_core.masking.null", "NullMasker"),
    ("bms_core.metrics.base", "bms_core.metrics.null", "NullMetrics"),
    ("bms_core.notify.base", "bms_core.notify.null", "NullNotifier"),
    ("bms_core.oauth.base", "bms_core.oauth.null", "NullOAuthServer"),
    ("bms_core.oauth.base", "bms_core.oauth.null", "NullScopeChecker"),
    ("bms_core.outbound.http", "bms_core.outbound.null", "NullHttpClient"),
    ("bms_core.outbound.webhook", "bms_core.outbound.null", "NullWebhookSender"),
    ("bms_core.password.base", "bms_core.password.null", "NullPasswordPolicy"),
    ("bms_core.permission.base", "bms_core.permission.null", "NullPermissionChecker"),
    ("bms_core.query.base", "bms_core.query.null", "NullQueryProvider"),
    ("bms_core.query.base", "bms_core.query.null", "NullQueryProviderRegistry"),
    ("bms_core.ratelimit.base", "bms_core.ratelimit.null", "NullRateLimiter"),
    ("bms_core.replay.base", "bms_core.replay.null", "NullReplayGuard"),
    ("bms_core.scope.base", "bms_core.scope.null", "NullDataScope"),
    ("bms_core.search.base", "bms_core.search.null", "NullSearchIndex"),
    ("bms_core.session.base", "bms_core.session.null", "NullSessionStore"),
    ("bms_core.sharding.base", "bms_core.sharding.null", "NullShardingRouter"),
    ("bms_core.storage.base", "bms_core.storage.null", "NullObjectStorage"),
    ("bms_core.tracing.base", "bms_core.tracing.null", "NullTracer"),
    ("bms_core.transfer.exporter", "bms_core.transfer.null", "NullExporter"),
    ("bms_core.transfer.importer", "bms_core.transfer.null", "NullImporter"),
    ("bms_core.workflow.base", "bms_core.workflow.null", "NullWorkflowEngine"),
    ("bms_core.ws.base", "bms_core.ws.null", "NullRealtimePublisher"),
]


def _import_all() -> None:
    """导入 app 包全部模块（缓存命中后极快）。"""
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="bms_core."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)


def _null_class_defs() -> list[tuple[str, str]]:
    """扫描 `bms_core/**/*.py` 中定义的 Null* 类，返回 (相对包路径, 类名)。"""
    found: list[tuple[str, str]] = []
    for path in sorted(_CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Null"):
                found.append((path.relative_to(_CORE).as_posix(), node.name))
    return found


@pytest.mark.kiwi_id(532)
def test_no_null_class_outside_null_modules() -> None:
    """落点护栏：`null.py` 之外模块不得定义 `Null*` 类。"""
    defs = _null_class_defs()
    assert defs, "未扫描到 Null* 类（扫描路径可能失效）"
    offenders = [(path, name) for path, name in defs if not path.endswith("null.py")]
    assert not offenders, offenders
    # 交叉一致：扫描到的 Null* 类均可自所属 null 模块导入（防清单与代码脱节）
    missing: list[str] = []
    for path, name in defs:
        module_name = "bms_core." + path.removesuffix(".py").replace("/", ".")
        if not hasattr(importlib.import_module(module_name), name):
            missing.append(f"{module_name}.{name}")
    assert not missing, missing


@pytest.mark.kiwi_id(532)
def test_migrated_classes_importable_and_old_paths_removed() -> None:
    """迁移类可自 `app.<domain>.null` 导入且 `__module__` 指向 null 模块；旧路径不可用。"""
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
            if current.__module__.startswith("bms_core."):
                registry.collect(current)
            pending.extend(current.__subclasses__())
    snapshot = registry.build()
    assert "object_storage" in snapshot
    assert snapshot["object_storage"]["null"] is importlib.import_module("bms_core.storage.null").NullObjectStorage
    for key, bucket in snapshot.items():
        for name, impl in bucket.items():
            if name == "null":
                assert isinstance(impl, type)
                assert impl.__module__.endswith(".null"), (key, impl)
