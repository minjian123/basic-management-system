"""框架对象 / 数据契约体系归位测试（Kiwi 2217）。

冻结台账 `OBJECT_BATCH` 即 09_05「框架对象与数据契约存量归位」的归位清单，按批次追加：
批次 ① 数据契约 3 → 批次 ② `bms_core` 框架类 30 → 批次 ③ 服务侧 17。
后续批次只允许「台账条目继续改挂」，不得把已归位对象改回 `BaseObject`。
"""

import ast
import dataclasses
import inspect
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from bms_core.api.middleware import (
    BaseMiddleware,
    EdgeGuardMiddleware,
    ReadOnlyMiddleware,
    RequestLoggingMiddleware,
    TenantMiddleware,
    TraceIdMiddleware,
)
from bms_core.audit.base import FieldChange
from bms_core.core.exceptions import BizError
from bms_core.core.holder import ValueHolder
from bms_core.core.objects import BaseFrameworkObject
from bms_core.events.base import EventEnvelope
from bms_core.sharding.base import ShardBinding

_BACKEND = Path(__file__).resolve().parents[4]
_ROOT = _BACKEND.parent
_BASELINE = _ROOT / "deploy" / "boundaries" / "direct_base_object_baseline.json"

OBJECT_BASES = frozenset(
    {
        "BaseDataContract",
        "BaseFrameworkObject",
        "BaseValueObject",
        "BaseProviderRegistry",
        "BaseCollection",
        "BaseConcurrent",
        "BaseCacheSnapshot",
        "BaseScopedRepository",
        "BaseRepository",
        "BaseHttpClient",
        "BaseServiceClient",
        "CacheRegion",
        "BaseMiddleware",
        "BaseAsyncSorted",
    }
)
"""允许的归位父基类（体系根 + 既有能力域基类）；新增基类须扩入本集合并在《后端基类清单》§10 登记。"""

OBJECT_BATCH: tuple[tuple[str, str, str], ...] = (
    ("backend/libs/bms_core/src/bms_core/audit/base.py", "FieldChange", "BaseDataContract"),
    ("backend/libs/bms_core/src/bms_core/events/base.py", "EventEnvelope", "BaseDataContract"),
    ("backend/libs/bms_core/src/bms_core/sharding/base.py", "ShardBinding", "BaseDataContract"),
    ("backend/libs/bms_core/src/bms_core/api/middleware.py", "TraceIdMiddleware", "BaseMiddleware"),
    ("backend/libs/bms_core/src/bms_core/api/middleware.py", "TenantMiddleware", "BaseMiddleware"),
    ("backend/libs/bms_core/src/bms_core/api/middleware.py", "ReadOnlyMiddleware", "BaseMiddleware"),
    ("backend/libs/bms_core/src/bms_core/api/middleware.py", "EdgeGuardMiddleware", "BaseMiddleware"),
    ("backend/libs/bms_core/src/bms_core/api/middleware.py", "RequestLoggingMiddleware", "BaseMiddleware"),
    ("backend/libs/bms_core/src/bms_core/api/base.py", "RouterRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/config/service.py", "ConfigService", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/id.py", "SnowflakeGenerator", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/locking.py", "LockGuard", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/locking.py", "ReadWriteLock", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/plugin.py", "PluginRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/redis_collections.py", "RedisSnapshot", "BaseCacheSnapshot"),
    ("backend/libs/bms_core/src/bms_core/core/redis_collections.py", "RedisSortedDict", "BaseAsyncSorted"),
    ("backend/libs/bms_core/src/bms_core/core/redis_collections.py", "RedisSortedSet", "BaseAsyncSorted"),
    ("backend/libs/bms_core/src/bms_core/core/resources.py", "ResourceManager", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/service.py", "ServiceRuntime", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/db/sync.py", "SyncSession", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/db/sync.py", "_SyncTransaction", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/db/tenant_remote.py", "RemoteTenantSource", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/dict/query.py", "DictQueryService", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/dict/service.py", "DictService", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/events/contracts.py", "EventContractRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/idp/jwks.py", "JwksCache", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/idp/registry.py", "IdentityProviderRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/outbox/consumed.py", "ProcessedEventStore", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/services/module_registry.py", "ModuleRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/services/table_registry.py", "TableOwnershipRegistry", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/transfer/null.py", "_EmptyExporterStream", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/holder.py", "ValueHolder", "BaseFrameworkObject"),
    ("backend/libs/bms_core/src/bms_core/core/exceptions.py", "BizError", "BaseFrameworkObject"),
    ("backend/services/identity/src/bms_identity/services/clients.py", "ClientSecret", "BaseFrameworkObject"),
    ("backend/services/identity/src/bms_identity/services/clients.py", "ClientService", "BaseFrameworkObject"),
    (
        "backend/services/identity/src/bms_identity/services/identity_providers.py",
        "IdentityProviderService",
        "BaseFrameworkObject",
    ),
    ("backend/services/identity/src/bms_identity/services/jit.py", "JitService", "BaseFrameworkObject"),
    ("backend/services/identity/src/bms_identity/services/auth.py", "LoginService", "BaseFrameworkObject"),
    (
        "backend/services/identity/src/bms_identity/services/oidc_provider.py",
        "OidcProviderService",
        "BaseFrameworkObject",
    ),
    ("backend/services/identity/src/bms_identity/services/org_client.py", "OrgCredentialClient", "BaseFrameworkObject"),
    (
        "backend/services/identity/src/bms_identity/services/password_reset.py",
        "PasswordResetService",
        "BaseFrameworkObject",
    ),
    (
        "backend/services/identity/src/bms_identity/services/provider_registry.py",
        "ProviderRegistry",
        "BaseFrameworkObject",
    ),
    ("backend/services/identity/src/bms_identity/services/session.py", "SessionService", "BaseFrameworkObject"),
    ("backend/services/identity/src/bms_identity/services/session_issuer.py", "SessionIssuer", "BaseFrameworkObject"),
    ("backend/services/identity/src/bms_identity/services/sso.py", "SsoService", "BaseFrameworkObject"),
    ("backend/services/org/src/bms_org/services/account_lock.py", "AccountLockService", "BaseFrameworkObject"),
    ("backend/services/org/src/bms_org/services/users.py", "UserProfileService", "BaseFrameworkObject"),
    ("backend/services/org/src/bms_org/services/users.py", "UserResetTargetService", "BaseFrameworkObject"),
    (
        "backend/services/tenant/src/bms_tenant/repositories/tenant_registry.py",
        "TenantRegistryRepository",
        "BaseFrameworkObject",
    ),
    ("backend/services/tenant/src/bms_tenant/sources/tenant_source.py", "LocalTenantSource", "BaseFrameworkObject"),
)
"""已归位台账（批次 ① 数据契约 3 + ②a `bms_core` 框架类 28 + ②b 2 + ③ 服务侧 17）——（源文件, 类名, 归位父基类）。

08_05（2026-09-29）集合体系收链：`RedisSortedDict` / `RedisSortedSet` 由 `BaseFrameworkObject`
改挂集合体系异步有序层 `BaseAsyncSorted`（回归集合链）；`RedisSnapshot` 改挂集合体系
通用缓存层 `BaseCacheSnapshot`（随 08 域集合体系唯一链收口）。"""

BASELINE_REMAINING = 0
"""基线剩余条目数（批次 ① 后 47 → ②a 后 19 → ②b 后 17 → ③ 后 **0**）。
0 ＝ 需求 09-1 验收目标「除体系根外零直继承」达成。"""


def _class_bases(rel: str, name: str) -> Sequence[str]:
    """取指定类声明的父类名列表（源码内 `class X(...)` 的括号内容）。

    Args:
        rel: 相对仓库根的源文件路径。
        name: 类名。

    Returns:
        Sequence[str]: 父类名（按声明顺序）；未找到该类时为空。
    """
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            # 去泛型参数：`BaseAsyncSorted[tuple[KeyT, ValueT]]` → `BaseAsyncSorted`
            return [ast.unparse(base).split("[")[0] for base in node.bases]
    return []


def _baseline_entries() -> Sequence[tuple[str, str, str]]:
    """读取直继承存量基线快照（`(文件, 类名, 拟归位体系)`）。

    Returns:
        Sequence[tuple[str, str, str]]: 基线条目。
    """
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return [(str(entry["file"]), str(entry["class"]), str(entry["target_system"])) for entry in payload["entries"]]


@pytest.mark.kiwi_id(2217)
def test_object_batch_declares_expected_base() -> None:
    """归位完整性：台账条目均声明**单一**目标父基类（体系根 / 能力域基类），且不再直继承 `BaseObject`。"""
    offenders: list[str] = []
    for rel, name, expected in OBJECT_BATCH:
        bases = _class_bases(rel, name)
        # 归位目标须在首位；除 `Exception`（`BizError` 多父类特例）外不允许其它父类。
        extra = set(bases[1:]) - {"Exception"}
        if bases[:1] != [expected] or extra or expected not in OBJECT_BASES:
            offenders.append(f"{rel}::{name} → {bases}（期望 {expected}）")
    assert not offenders, "台账条目须挂目标体系根 / 能力域基类；违规：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2217)
def test_object_batch_removed_from_baseline() -> None:
    """基线即台账：台账条目已不在基线快照中，且基线条目数随批次递减。"""
    baseline = {(rel, name) for rel, name, _system in _baseline_entries()}
    still_present = [f"{rel}::{name}" for rel, name, _expected in OBJECT_BATCH if (rel, name) in baseline]
    assert not still_present, "已归位条目仍留在基线快照（须用 --update-baseline 递减）：\n" + "\n".join(still_present)
    assert len(baseline) == BASELINE_REMAINING, f"基线条目数应为 {BASELINE_REMAINING}，实际 {len(baseline)}"


@pytest.mark.kiwi_id(2217)
def test_base_middleware_common_segment_holds() -> None:
    """新增能力域基类：`BaseMiddleware` 的公共段（抽象 ASGI `__call__`）在 5 个成员上成立。"""
    assert getattr(BaseMiddleware.__call__, "__isabstractmethod__", False) is True
    for member in (
        EdgeGuardMiddleware,
        ReadOnlyMiddleware,
        RequestLoggingMiddleware,
        TenantMiddleware,
        TraceIdMiddleware,
    ):
        assert issubclass(member, BaseMiddleware)
        assert {"scope", "receive", "send"} <= set(inspect.signature(member.__call__).parameters)


@pytest.mark.kiwi_id(2217)
def test_biz_error_keeps_exception_semantics() -> None:
    """错误体系根归位后语义不变：`BizError` 仍是 `Exception`（可 `raise` / `except`），并带框架对象标识。"""
    assert issubclass(BizError, Exception)
    assert issubclass(BizError, BaseFrameworkObject)
    assert BizError.object_kind == "biz_error"
    assert isinstance(BizError(code=1, message="x"), Exception)
    with pytest.raises(BizError):
        raise BizError(code=2)


@pytest.mark.kiwi_id(2217)
def test_value_holder_moved_to_own_module() -> None:
    """`ValueHolder` 迁出根系模块后仍可构造与写回（行为零变更），且不再是根系直继承。"""
    holder = ValueHolder("v")
    assert holder.value == "v"
    assert not any(base.__name__ == "BaseObject" for base in ValueHolder.__bases__)


@pytest.mark.kiwi_id(2217)
def test_data_contract_batch_is_mutable_dataclass() -> None:
    """数据类体系语义：`BaseDataContract` 归位项为**可变** dataclass（非 frozen）。"""
    offenders: list[str] = []
    for cls in (FieldChange, EventEnvelope, ShardBinding):
        params = getattr(cls, "__dataclass_params__", None)
        if not dataclasses.is_dataclass(cls) or params is None or params.frozen:
            offenders.append(cls.__name__)
    assert not offenders, "数据契约体系成员须为可变 dataclass（非 frozen）：\n" + "\n".join(offenders)
