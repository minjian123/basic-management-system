"""值对象存量归位（批次 1，09_03，Kiwi 2216）。

依据《后端基类清单》§10「体系根清单」与 09_01 直继承护栏
（`scripts/tools/base-check/check-backend-base.py`）：

- 批次 1 的 110 个不可变值对象一律改挂 `BaseValueObject`，不再直继承 `BaseObject`；
- 仍只有 7 个体系根允许直继承 `BaseObject`（白名单以《后端基类清单》§10 为准）；
- 直继承存量基线递减至 50 条且不含 `value_object`（余量＝数据契约 3 + 框架对象 47）。

冻结台账 `VALUE_OBJECT_BATCH` 即批次 1 的归位清单（取自基线路径与类名），
后续批次归位只允许「台账条目继续改挂」，不得把已归位的值对象改回 `BaseObject`。
"""

import ast
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[4]
_ROOT = _BACKEND.parent
_BASELINE = _ROOT / "deploy" / "boundaries" / "direct_base_object_baseline.json"
_MANIFEST = _ROOT / "bms文档" / "后端基类清单.md"
_SOURCE_DIRS = (_BACKEND / "libs", _BACKEND / "services", _BACKEND / "ops")
_SYSTEM_ROOTS = frozenset(
    {
        "BaseValueObject",
        "BaseDataContract",
        "BaseFrameworkObject",
        "BaseSorted",
        "BaseRepository",
        "BaseService",
        "UnitOfWork",
    }
)
_ROOT_BASES_MARKER = "体系根清单"

VALUE_OBJECT_BATCH: tuple[tuple[str, str], ...] = (
    ("backend/libs/bms_core/src/bms_core/api/base.py", "AuthContext"),
    ("backend/libs/bms_core/src/bms_core/archive/base.py", "ArchiveResult"),
    ("backend/libs/bms_core/src/bms_core/audit/hashchain.py", "ChainVerifyResult"),
    ("backend/libs/bms_core/src/bms_core/audit/hashchain.py", "HashChainEntry"),
    ("backend/libs/bms_core/src/bms_core/boundary/assess.py", "OwnershipViolation"),
    ("backend/libs/bms_core/src/bms_core/boundary/base.py", "OwnershipStats"),
    ("backend/libs/bms_core/src/bms_core/boundary/exceptions.py", "OwnershipException"),
    ("backend/libs/bms_core/src/bms_core/boundary/sql.py", "TableRef"),
    ("backend/libs/bms_core/src/bms_core/captcha/base.py", "CaptchaChallenge"),
    ("backend/libs/bms_core/src/bms_core/captcha/base.py", "CaptchaCredential"),
    ("backend/libs/bms_core/src/bms_core/captcha/base.py", "CaptchaScenePolicy"),
    ("backend/libs/bms_core/src/bms_core/captcha/default.py", "CaptchaImageOptions"),
    ("backend/libs/bms_core/src/bms_core/captcha/default.py", "CaptchaSliderOptions"),
    ("backend/libs/bms_core/src/bms_core/captcha/default.py", "CaptchaSmsOptions"),
    ("backend/libs/bms_core/src/bms_core/chat/base.py", "ChatStreamHandle"),
    ("backend/libs/bms_core/src/bms_core/config/seed.py", "SeedConfig"),
    ("backend/libs/bms_core/src/bms_core/core/assembly.py", "PluginWiring"),
    ("backend/libs/bms_core/src/bms_core/core/service.py", "ServiceIdentity"),
    ("backend/libs/bms_core/src/bms_core/db/admin.py", "DatabaseTarget"),
    ("backend/libs/bms_core/src/bms_core/db/inventory.py", "DbCount"),
    ("backend/libs/bms_core/src/bms_core/db/keys.py", "DbKey"),
    ("backend/libs/bms_core/src/bms_core/db/migration.py", "MigrationChain"),
    ("backend/libs/bms_core/src/bms_core/db/registry.py", "PoolBudgetRow"),
    ("backend/libs/bms_core/src/bms_core/db/tenant.py", "TenantContext"),
    ("backend/libs/bms_core/src/bms_core/db/tenant_registry.py", "TenantSnapshot"),
    ("backend/libs/bms_core/src/bms_core/dict/seed.py", "SeedAttr"),
    ("backend/libs/bms_core/src/bms_core/dict/seed.py", "SeedItem"),
    ("backend/libs/bms_core/src/bms_core/dict/seed.py", "SeedType"),
    ("backend/libs/bms_core/src/bms_core/edge/base.py", "EdgeIdentity"),
    ("backend/libs/bms_core/src/bms_core/edge/base.py", "EdgeTrustDecision"),
    ("backend/libs/bms_core/src/bms_core/events/contracts.py", "EventContract"),
    ("backend/libs/bms_core/src/bms_core/events/contracts.py", "EventFieldSpec"),
    ("backend/libs/bms_core/src/bms_core/events/contracts.py", "EventSubscription"),
    ("backend/libs/bms_core/src/bms_core/health/base.py", "HealthCheckReport"),
    ("backend/libs/bms_core/src/bms_core/health/base.py", "HealthCheckResult"),
    ("backend/libs/bms_core/src/bms_core/idp/base.py", "IdentityClaims"),
    ("backend/libs/bms_core/src/bms_core/idp/base.py", "IdentityToken"),
    ("backend/libs/bms_core/src/bms_core/idp/base.py", "IdentityUser"),
    ("backend/libs/bms_core/src/bms_core/idp/base.py", "IdpProbeResult"),
    ("backend/libs/bms_core/src/bms_core/idp/registry.py", "IdentityProviderSpec"),
    ("backend/libs/bms_core/src/bms_core/idp/schema.py", "_KeyRule"),
    ("backend/libs/bms_core/src/bms_core/idp/state/base.py", "IdpFlowState"),
    ("backend/libs/bms_core/src/bms_core/llm/base.py", "ChatMessage"),
    ("backend/libs/bms_core/src/bms_core/llm/base.py", "ChatResult"),
    ("backend/libs/bms_core/src/bms_core/llm/base.py", "EmbeddingResult"),
    ("backend/libs/bms_core/src/bms_core/llm/base.py", "OcrResult"),
    ("backend/libs/bms_core/src/bms_core/masking/base.py", "MaskRule"),
    ("backend/libs/bms_core/src/bms_core/masking/default.py", "MaskSpec"),
    ("backend/libs/bms_core/src/bms_core/masking/default.py", "MaskerOptions"),
    ("backend/libs/bms_core/src/bms_core/notify/base.py", "NotificationMessage"),
    ("backend/libs/bms_core/src/bms_core/notify/base.py", "SendResult"),
    ("backend/libs/bms_core/src/bms_core/oauth/base.py", "ClientCredentials"),
    ("backend/libs/bms_core/src/bms_core/oauth/base.py", "OAuthToken"),
    ("backend/libs/bms_core/src/bms_core/oauth/keys.py", "TokenKey"),
    ("backend/libs/bms_core/src/bms_core/oauth/oidc_provider.py", "AccessTokenSpec"),
    ("backend/libs/bms_core/src/bms_core/oauth/oidc_provider.py", "IdTokenSpec"),
    ("backend/libs/bms_core/src/bms_core/oauth/oidc_provider.py", "OidcAccessClaims"),
    ("backend/libs/bms_core/src/bms_core/oauth/token.py", "ServiceTokenSpec"),
    ("backend/libs/bms_core/src/bms_core/oauth/user_token.py", "UserTokenPair"),
    ("backend/libs/bms_core/src/bms_core/oauth/user_token.py", "UserTokenSpec"),
    ("backend/libs/bms_core/src/bms_core/oauth/verify.py", "VerifiedToken"),
    ("backend/libs/bms_core/src/bms_core/outbound/http.py", "HttpResponse"),
    ("backend/libs/bms_core/src/bms_core/outbound/webhook.py", "WebhookResult"),
    ("backend/libs/bms_core/src/bms_core/outbox/base.py", "DeadLetterRecord"),
    ("backend/libs/bms_core/src/bms_core/outbox/base.py", "DispatchResult"),
    ("backend/libs/bms_core/src/bms_core/outbox/base.py", "OutboxRecord"),
    ("backend/libs/bms_core/src/bms_core/query/base.py", "QueryResult"),
    ("backend/libs/bms_core/src/bms_core/ratelimit/base.py", "RateLimitDecision"),
    ("backend/libs/bms_core/src/bms_core/ratelimit/base.py", "RateLimitRule"),
    ("backend/libs/bms_core/src/bms_core/replay/base.py", "ReplayDecision"),
    ("backend/libs/bms_core/src/bms_core/saga/base.py", "SagaDefinition"),
    ("backend/libs/bms_core/src/bms_core/saga/base.py", "SagaStep"),
    ("backend/libs/bms_core/src/bms_core/saga/base.py", "SagaStepOutcome"),
    ("backend/libs/bms_core/src/bms_core/schemas/cursor.py", "CursorPayload"),
    ("backend/libs/bms_core/src/bms_core/scope/base.py", "ScopeCondition"),
    ("backend/libs/bms_core/src/bms_core/search/base.py", "SearchDocument"),
    ("backend/libs/bms_core/src/bms_core/search/base.py", "SearchHit"),
    ("backend/libs/bms_core/src/bms_core/search/base.py", "SearchQuery"),
    ("backend/libs/bms_core/src/bms_core/search/base.py", "SearchResult"),
    ("backend/libs/bms_core/src/bms_core/servicecall/base.py", "ServiceCallPolicy"),
    ("backend/libs/bms_core/src/bms_core/servicecall/base.py", "ServiceRequest"),
    ("backend/libs/bms_core/src/bms_core/servicecall/base.py", "ServiceResponse"),
    ("backend/libs/bms_core/src/bms_core/services/module_registry.py", "ModuleRecord"),
    ("backend/libs/bms_core/src/bms_core/services/table_registry.py", "TableRecord"),
    ("backend/libs/bms_core/src/bms_core/storage/base.py", "PresignedUrl"),
    ("backend/libs/bms_core/src/bms_core/storage/base.py", "StoredObject"),
    ("backend/libs/bms_core/src/bms_core/tracing/base.py", "SpanContext"),
    ("backend/libs/bms_core/src/bms_core/transfer/base.py", "ColumnSpec"),
    ("backend/libs/bms_core/src/bms_core/transfer/importer.py", "ImportResult"),
    ("backend/libs/bms_core/src/bms_core/transfer/importer.py", "RowError"),
    ("backend/libs/bms_core/src/bms_core/workflow/base.py", "ProcessDefinition"),
    ("backend/libs/bms_core/src/bms_core/workflow/base.py", "ProcessInstance"),
    ("backend/libs/bms_core/src/bms_core/workflow/base.py", "WorkflowTask"),
    ("backend/libs/bms_core/src/bms_core/ws/base.py", "RealtimeEvent"),
    ("backend/ops/init_tenant.py", "InitResult"),
    ("backend/ops/migrate_tenants.py", "MigrationSummary"),
    ("backend/ops/migrate_tenants.py", "MigrationTask"),
    ("backend/ops/provision_tenant.py", "ProvisionTask"),
    ("backend/services/identity/src/bms_identity/services/auth.py", "LoginOutcome"),
    ("backend/services/identity/src/bms_identity/services/auth.py", "RefreshOutcome"),
    ("backend/services/identity/src/bms_identity/services/jit.py", "ExternalIdentity"),
    ("backend/services/identity/src/bms_identity/services/jit.py", "JitResult"),
    ("backend/services/identity/src/bms_identity/services/oidc_provider.py", "AuthorizeResult"),
    ("backend/services/identity/src/bms_identity/services/oidc_provider.py", "OidcCode"),
    ("backend/services/identity/src/bms_identity/services/oidc_provider.py", "TokenResult"),
    ("backend/services/identity/src/bms_identity/services/oidc_provider.py", "UserInfoResult"),
    ("backend/services/identity/src/bms_identity/services/session.py", "SessionRevokeResult"),
    ("backend/services/identity/src/bms_identity/services/session_issuer.py", "IssuedSession"),
    ("backend/services/identity/src/bms_identity/services/sso.py", "SsoAuthorizeResult"),
    ("backend/services/identity/src/bms_identity/services/sso.py", "SsoLoginResult"),
)


def _iter_source_files() -> Iterator[Path]:
    """产出受护栏约束的源文件（排除 `tests` / `__pycache__`，与基座护栏同口径）。

    Yields:
        Path: 源文件路径。
    """
    for source_dir in _SOURCE_DIRS:
        for path in sorted(source_dir.rglob("*.py")):
            parts = path.parts
            if "__pycache__" in parts or "tests" in parts:
                continue
            yield path


def _direct_base_object_inheritors() -> Iterator[tuple[str, str]]:
    """产出直接继承 `BaseObject` 的类（`(相对仓库路径, 类名)`）。

    Yields:
        tuple[str, str]: 相对仓库根的路径与类名。
    """
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(ast.unparse(base) == "BaseObject" for base in node.bases):
                yield rel, node.name


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
            return [ast.unparse(base) for base in node.bases]
    return []


def _baseline_entries() -> Sequence[tuple[str, str, str]]:
    """读取直继承存量基线快照（`(文件, 类名, 拟归位体系)`）。

    Returns:
        Sequence[tuple[str, str, str]]: 基线条目。
    """
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return [(str(entry["file"]), str(entry["class"]), str(entry["target_system"])) for entry in payload["entries"]]


def _manifest_system_roots() -> Sequence[str]:
    """解析《后端基类清单》§10「体系根清单」小节的体系根（护栏白名单权威来源）。

    Returns:
        Sequence[str]: 体系根类名（稳定序）。
    """
    text = _MANIFEST.read_text(encoding="utf-8")
    section = text[text.index("## 10.") : text.index("## 11.")]
    roots: list[str] = []
    for raw_line in section[section.index(_ROOT_BASES_MARKER) :].splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("- "):
            break
        roots.append(line.split("`")[1])
    return roots


@pytest.mark.kiwi_id(2216)
def test_value_object_batch_is_frozen_and_complete() -> None:
    """批次台账冻结：110 项且无重复（归位清单以本台账为准）。"""
    assert len(VALUE_OBJECT_BATCH) == 110
    assert len(set(VALUE_OBJECT_BATCH)) == 110


@pytest.mark.kiwi_id(2216)
def test_value_object_batch_declares_base_value_object() -> None:
    """归位完整性：批次 110 处均声明 `BaseValueObject`，且不再直继承 `BaseObject`。"""
    offenders: list[str] = []
    for rel, name in VALUE_OBJECT_BATCH:
        bases = _class_bases(rel, name)
        if bases != ["BaseValueObject"]:
            offenders.append(f"{rel}::{name} → {bases}")
    assert not offenders, "批次 1 值对象须改挂 BaseValueObject；违规：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2216)
def test_system_roots_still_directly_inherit_base_object() -> None:
    """体系根边界：白名单 = 清单 §10「体系根清单」的 7 个，且仍直接继承 `BaseObject`。"""
    found = {name for _rel, name in _direct_base_object_inheritors()}
    assert set(_manifest_system_roots()) == _SYSTEM_ROOTS
    assert found >= _SYSTEM_ROOTS
    assert not (_SYSTEM_ROOTS & {name for _rel, name in VALUE_OBJECT_BATCH})


@pytest.mark.kiwi_id(2216)
def test_direct_inheritance_stays_within_roots_and_baseline() -> None:
    """直继承合法性：全域扫描结果与「体系根 ∪ 基线快照」严格一致（无新增、无残留）。"""
    found = set(_direct_base_object_inheritors())
    allowed = {(rel, name) for rel, name, _system in _baseline_entries()}
    assert {item for item in found if item[1] not in _SYSTEM_ROOTS} == allowed


@pytest.mark.kiwi_id(2216)
def test_direct_baseline_decreased_without_value_object() -> None:
    """基线递减：50 条（框架对象 47 + 数据契约 3）且不含 `value_object`。"""
    entries = _baseline_entries()
    assert len(entries) == 50
    assert {system for _rel, _name, system in entries} == {"framework_object", "data_contract"}
