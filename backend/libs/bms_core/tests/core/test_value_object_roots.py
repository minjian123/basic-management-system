"""值对象存量归位（批次 1，09_03，Kiwi 2216）。

依据《后端基类清单》§10「体系根清单」与 09_01 直继承护栏
（`scripts/tools/base-check/check-backend-base.py`）：

- 批次 1 的 110 个不可变值对象改挂 `BaseValueObject`（不再直继承 `BaseObject`），其中
  `ChatStreamHandle` 经复核为**运行时句柄**（含 `AsyncIterator` 字段、非数据对象）→ 迁 `BaseFrameworkObject`，
  故本台账为 **109 处**；
- 仍只有 7 个体系根允许直继承 `BaseObject`（白名单以《后端基类清单》§10 为准）；
- 直继承存量基线递减至 50 条且不含 `value_object`（余量＝数据契约 3 + 框架对象 47）。

冻结台账 `VALUE_OBJECT_BATCH` 即批次 1 的归位清单（取自基线路径与类名），
后续批次归位只允许「台账条目继续改挂」，不得把已归位的值对象改回 `BaseObject`。
"""

import ast
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from bms_core.api.base import AuthContext
from bms_core.boundary.assess import OwnershipViolation
from bms_core.boundary.base import OwnershipStats
from bms_core.boundary.exceptions import OwnershipException
from bms_core.captcha.base import CaptchaChallenge, CaptchaCredential
from bms_core.captcha.default import CaptchaImageOptions, CaptchaSliderOptions, CaptchaSmsOptions
from bms_core.chat.base import ChatStreamHandle
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import (
    BaseAuthorizeUrlResultContract,
    BaseCaptchaContract,
    BaseDecisionContract,
    BaseDeliveryResultContract,
    BaseEventRecordContract,
    BaseFieldRuleContract,
    BaseFieldSpecContract,
    BaseFrameworkObject,
    BaseHealthResultContract,
    BaseHttpResponseContract,
    BaseI18nSeedContract,
    BaseIdentityProfileContract,
    BaseLlmResultContract,
    BaseLoginResultContract,
    BaseOidcTokenSpecContract,
    BaseOpsReportContract,
    BaseOptionsContract,
    BaseOwnershipContract,
    BaseProcessContract,
    BaseRefreshableTokenContract,
    BaseRegistryRecordContract,
    BaseRequestIdentityContract,
    BaseSearchContract,
    BaseSecretMaterialContract,
    BaseSnapshotRoundTripContract,
    BaseTallyContract,
    BaseTenantViewContract,
    BaseTokenClaimsContract,
    BaseTokenContract,
    BaseTokenSpecContract,
    BaseValueObject,
)
from bms_core.db.admin import DatabaseTarget
from bms_core.db.inventory import DbCount
from bms_core.db.registry import PoolBudgetRow
from bms_core.db.tenant import TenantContext
from bms_core.db.tenant_registry import TenantSnapshot
from bms_core.dict.seed import SeedItem, SeedType
from bms_core.edge.base import EdgeIdentity, EdgeTrustDecision
from bms_core.events.contracts import EventContract, EventFieldSpec, EventSubscription
from bms_core.health.base import HealthCheckReport, HealthCheckResult
from bms_core.idp.base import IdentityClaims, IdentityToken, IdentityUser
from bms_core.llm.base import ChatResult, EmbeddingResult, OcrResult
from bms_core.masking.base import MaskRule
from bms_core.masking.default import MaskerOptions
from bms_core.notify.base import SendResult
from bms_core.oauth.base import ClientCredentials, OAuthToken
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.oidc_provider import AccessTokenSpec, IdTokenSpec, OidcAccessClaims
from bms_core.oauth.token import ServiceTokenSpec
from bms_core.oauth.user_token import UserTokenPair
from bms_core.oauth.verify import VerifiedToken
from bms_core.outbound.http import HttpResponse
from bms_core.outbound.webhook import WebhookResult
from bms_core.outbox.base import DeadLetterRecord, DispatchResult, OutboxRecord
from bms_core.ratelimit.base import RateLimitDecision
from bms_core.replay.base import ReplayDecision
from bms_core.scope.base import ScopeCondition
from bms_core.search.base import SearchDocument, SearchQuery
from bms_core.servicecall.base import ServiceResponse
from bms_core.services.module_registry import ModuleRecord
from bms_core.services.table_registry import TableRecord
from bms_core.transfer.base import ColumnSpec
from bms_core.workflow.base import ProcessDefinition, ProcessInstance

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
        "BaseCollection",
        "BaseRepository",
        "BaseService",
        "UnitOfWork",
    }
)
_ROOT_BASES_MARKER = "体系根清单"

VALUE_OBJECT_BASES = frozenset(
    {
        "BaseValueObject",
        "BaseAuthorizeUrlResultContract",
        "BaseCaptchaContract",
        "BaseDecisionContract",
        "BaseDeliveryResultContract",
        "BaseEventRecordContract",
        "BaseFieldRuleContract",
        "BaseFieldSpecContract",
        "BaseHealthResultContract",
        "BaseHttpResponseContract",
        "BaseI18nSeedContract",
        "BaseIdentityProfileContract",
        "BaseLlmResultContract",
        "BaseLoginResultContract",
        "BaseOidcTokenSpecContract",
        "BaseOptionsContract",
        "BaseOpsReportContract",
        "BaseOwnershipContract",
        "BaseProcessContract",
        "BaseRefreshableTokenContract",
        "BaseRegistryRecordContract",
        "BaseRequestIdentityContract",
        "BaseSearchContract",
        "BaseSecretMaterialContract",
        "BaseSnapshotRoundTripContract",
        "BaseTallyContract",
        "BaseTenantViewContract",
        "BaseTokenClaimsContract",
        "BaseTokenContract",
        "BaseTokenSpecContract",
    }
)
"""值对象体系合法直系父基类（体系根 + 已落地角色链层）；每批新层落地时同步扩入。"""

ROLE_CHAINS: tuple[tuple[type, tuple[type, ...]], ...] = (
    (BaseOptionsContract, (CaptchaImageOptions, CaptchaSliderOptions, CaptchaSmsOptions, MaskerOptions)),
    (BaseTokenContract, (OAuthToken, UserTokenPair, IdentityToken)),
    (BaseRefreshableTokenContract, (UserTokenPair, IdentityToken)),
    (BaseTokenSpecContract, (ServiceTokenSpec, AccessTokenSpec, IdTokenSpec)),
    (BaseOidcTokenSpecContract, (AccessTokenSpec, IdTokenSpec)),
    (BaseTokenClaimsContract, (VerifiedToken, OidcAccessClaims, IdentityClaims)),
    (BaseSecretMaterialContract, (ClientCredentials, TokenKey)),
    (BaseRequestIdentityContract, (AuthContext, EdgeIdentity)),
    (BaseIdentityProfileContract, (IdentityUser,)),
    (BaseTenantViewContract, (TenantContext, TenantSnapshot)),
    (BaseLoginResultContract, ()),
    (BaseAuthorizeUrlResultContract, ()),
    (BaseDecisionContract, (RateLimitDecision, ReplayDecision, EdgeTrustDecision)),
    (BaseFieldSpecContract, (ColumnSpec, EventFieldSpec)),
    (BaseProcessContract, (ProcessDefinition, ProcessInstance)),
    (BaseRegistryRecordContract, (ModuleRecord, TableRecord)),
    (BaseI18nSeedContract, (SeedItem, SeedType)),
    (BaseOpsReportContract, (DatabaseTarget, DbCount, PoolBudgetRow)),
    (BaseHealthResultContract, (HealthCheckResult, HealthCheckReport)),
    (BaseTallyContract, (DispatchResult, OwnershipStats)),
    (BaseFieldRuleContract, (MaskRule, ScopeCondition)),
    (BaseCaptchaContract, (CaptchaChallenge, CaptchaCredential)),
    (BaseSearchContract, (SearchQuery, SearchDocument)),
    (BaseSnapshotRoundTripContract, (EventContract, EventSubscription)),
    (BaseEventRecordContract, (OutboxRecord, DeadLetterRecord)),
    (BaseLlmResultContract, (ChatResult, EmbeddingResult, OcrResult)),
    (BaseHttpResponseContract, (HttpResponse, ServiceResponse)),
    (BaseDeliveryResultContract, (SendResult, WebhookResult)),
    (BaseOwnershipContract, (OwnershipViolation, OwnershipException)),
)
"""角色链台账（层 → 成员）：仅登记**基座侧**成员——服务侧成员（`TokenResult` / `IssuedSession` 等）
由 `VALUE_OBJECT_BATCH` 的「单一父基类」断言覆盖（`bms_identity` 在基座用例环境不可导入）。"""

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
    ("backend/libs/bms_core/src/bms_core/masking/text.py", "MaskSpec"),
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


def _class_bases(rel: str, name: str) -> ConcurrentStableList[str]:
    """取指定类声明的父类名列表（源码内 `class X(...)` 的括号内容）。

    Args:
        rel: 相对仓库根的源文件路径。
        name: 类名。

    Returns:
        ConcurrentStableList[str]: 父类名（按声明顺序）；未找到该类时为空。
    """
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ConcurrentStableList(ast.unparse(base) for base in node.bases)
    return ConcurrentStableList()


def _baseline_entries() -> ConcurrentStableList[tuple[str, str, str]]:
    """读取直继承存量基线快照（`(文件, 类名, 拟归位体系)`）。

    Returns:
        ConcurrentStableList[tuple[str, str, str]]: 基线条目。
    """
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return ConcurrentStableList(
        (str(entry["file"]), str(entry["class"]), str(entry["target_system"])) for entry in payload["entries"]
    )


def _manifest_system_roots() -> ConcurrentStableList[str]:
    """解析《后端基类清单》§10「体系根清单」小节的体系根（护栏白名单权威来源）。

    Returns:
        ConcurrentStableList[str]: 体系根类名（稳定序）。
    """
    text = _MANIFEST.read_text(encoding="utf-8")
    section = text[text.index("## 10.") : text.index("## 11.")]
    roots: ConcurrentStableList[str] = ConcurrentStableList()
    for raw_line in section[section.index(_ROOT_BASES_MARKER) :].splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("- "):
            break
        roots.add(line.split("`")[1])
    return roots


@pytest.mark.kiwi_id(2216)
def test_value_object_batch_is_frozen_and_complete() -> None:
    """批次台账冻结：109 项且无重复（归位清单以本台账为准；`ChatStreamHandle` 已迁出）。"""
    assert len(VALUE_OBJECT_BATCH) == 106
    assert len(set(VALUE_OBJECT_BATCH)) == 106


@pytest.mark.kiwi_id(2216)
def test_value_object_batch_declares_value_object_base() -> None:
    """归位完整性：批次 109 处均声明**单一**值对象体系父基类（体系根或已落地角色链层）。"""
    offenders: ConcurrentStableList[str] = ConcurrentStableList()
    for rel, name in VALUE_OBJECT_BATCH:
        bases = _class_bases(rel, name)
        if len(bases) != 1 or bases[0] not in VALUE_OBJECT_BASES:
            offenders.add(f"{rel}::{name} → {bases}")
    assert not offenders, "批次 1 值对象须挂值对象体系（体系根或角色链层）；违规：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2216)
def test_value_object_base_names_are_real_layers() -> None:
    """台账口径自洽：`VALUE_OBJECT_BASES` 列出的角色链层确实是值对象体系内的类。"""
    layers = {"BaseValueObject": BaseValueObject, **{layer.__name__: layer for layer, _members in ROLE_CHAINS}}
    assert set(layers) == set(VALUE_OBJECT_BASES)
    for layer in layers.values():
        assert issubclass(layer, BaseValueObject)


@pytest.mark.kiwi_id(2216)
def test_options_chain_layer_contract() -> None:
    """选项链层：成员挂 `BaseOptionsContract`，公共段 `from_options` 为抽象入口。"""
    for member in (CaptchaImageOptions, CaptchaSliderOptions, CaptchaSmsOptions, MaskerOptions):
        assert issubclass(member, BaseOptionsContract)
        assert dataclasses.is_dataclass(member)
    assert getattr(BaseOptionsContract.from_options, "__isabstractmethod__", False) is True


@pytest.mark.kiwi_id(2216)
def test_role_chain_members_inherit_their_layer() -> None:
    """角色链台账：层内成员全部继承本层，且层均在值对象体系根之下。"""
    offenders: ConcurrentStableList[str] = ConcurrentStableList()
    for layer, members in ROLE_CHAINS:
        assert issubclass(layer, BaseValueObject)
        for member in members:
            if not issubclass(member, layer):
                offenders.add(f"{member.__name__} 未挂 {layer.__name__}")
    assert not offenders, "角色链成员与层不一致：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2216)
def test_role_chain_common_fields_hold_on_all_members() -> None:
    """公共段完整性：每层声明的公共段（沿 MRO 累加）都是**全部**成员的 dataclass 字段。"""
    offenders: ConcurrentStableList[str] = ConcurrentStableList()
    for layer, members in ROLE_CHAINS:
        common: ConcurrentStableSet[str] = ConcurrentStableSet()
        for ancestor in layer.__mro__:
            declared: tuple[str, ...] = getattr(ancestor, "COMMON_FIELDS", ())
            common.update(declared)
        for member in members:
            missing = common - {field.name for field in dataclasses.fields(member)}
            if missing:
                offenders.add(f"{member.__name__} 缺 {layer.__name__} 公共段：{sorted(missing)}")
    assert not offenders, "层公共段在成员上不成立：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2216)
def test_snapshot_round_trip_chain_layer_contract() -> None:
    """快照往返链层：`to_snapshot` / `from_snapshot` 为抽象成对入口，成员均实现两者。"""
    assert getattr(BaseSnapshotRoundTripContract.to_snapshot, "__isabstractmethod__", False) is True
    assert getattr(BaseSnapshotRoundTripContract.from_snapshot, "__isabstractmethod__", False) is True
    for member in (EventContract, EventSubscription):
        assert issubclass(member, BaseSnapshotRoundTripContract)
        assert callable(member.to_snapshot)
        assert callable(member.from_snapshot)


@pytest.mark.kiwi_id(2216)
def test_ownership_chain_prefix_field_points_to_real_field() -> None:
    """所有权链层：`PREFIX_FIELD` 映射声明指向真实字段（历史不同名的前缀位可统一取用）。"""
    for member in (OwnershipViolation, OwnershipException):
        assert member.PREFIX_FIELD in {field.name for field in dataclasses.fields(member)}
    assert OwnershipViolation.PREFIX_FIELD == "prefix"
    assert OwnershipException.PREFIX_FIELD == "target_prefix"


@pytest.mark.kiwi_id(2216)
def test_ops_report_chain_layer_contract() -> None:
    """运维报告链层：公共段为抽象报告行入口 `describe()`，成员均实现该入口。"""
    assert getattr(BaseOpsReportContract.describe, "__isabstractmethod__", False) is True
    for member in (DatabaseTarget, DbCount, PoolBudgetRow):
        assert issubclass(member, BaseOpsReportContract)
        assert callable(member.describe)


@pytest.mark.kiwi_id(2216)
def test_tally_chain_counts_mapping() -> None:
    """计数汇总链层：`COUNT_FIELDS` 声明的计数位在全部成员上是**整数计数字段**，`counts` 可统一读取。"""
    assert any(layer is BaseTallyContract for layer, _members in ROLE_CHAINS)
    for member in (DispatchResult, OwnershipStats):
        declared: tuple[str, ...] = member.COUNT_FIELDS
        assert declared, f"{member.__name__} 未声明计数位"
        assert set(declared) <= {field.name for field in dataclasses.fields(member)}
    assert DispatchResult().counts == {"published": 0, "failed": 0, "dead": 0, "backlog": 0}
    assert OwnershipStats(statements=3).counts["statements"] == 3


@pytest.mark.kiwi_id(2216)
def test_registry_record_chain_layer_contract() -> None:
    """登记记录链层：公共段为成对构造钩子 `from_row`（抽象入口），成员均实现该钩子。"""
    assert getattr(BaseRegistryRecordContract.from_row, "__isabstractmethod__", False) is True
    for member in (ModuleRecord, TableRecord):
        assert issubclass(member, BaseRegistryRecordContract)
        assert getattr(member.from_row, "__func__", None) is not None


@pytest.mark.kiwi_id(2216)
def test_decision_chain_allows_unified_field_name() -> None:
    """判定链层：三处判定均以 `allowed` 表达结论（`EdgeTrustDecision.trusted` 已统一命名）。"""
    for member in (RateLimitDecision, ReplayDecision, EdgeTrustDecision):
        assert "allowed" in {field.name for field in dataclasses.fields(member)}
    assert EdgeTrustDecision(allowed=False, reason="x").allowed is False


@pytest.mark.kiwi_id(2216)
def test_tenant_view_code_is_common_field() -> None:
    """租户视图层：租户**自身**编码统一为 `code`（进公共段，`CODE_FIELD` 已退场）。"""
    assert "code" in BaseTenantViewContract.COMMON_FIELDS
    assert not hasattr(BaseTenantViewContract, "CODE_FIELD")
    for member in (TenantContext, TenantSnapshot):
        assert "code" in {field.name for field in dataclasses.fields(member)}
        assert "tenant_code" not in {field.name for field in dataclasses.fields(member)}
    assert TenantContext(code="demo", db_key="tenant_demo", name="演示租户").code == "demo"


@pytest.mark.kiwi_id(2216)
def test_secret_material_repr_masks_declared_fields() -> None:
    """敏感材料层：`SECRET_FIELDS` 声明的字段在 `repr` 中一律遮蔽（密钥 / 口令不入日志）。"""
    credentials = ClientCredentials(client_id="c1", client_secret="s3cr3t")
    assert "'s3cr3t'" not in repr(credentials)
    assert "client_secret='***'" in repr(credentials)
    assert ClientCredentials.SECRET_FIELDS == ("client_secret",)
    assert TokenKey.SECRET_FIELDS == ("private_key",)


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
    """基线递减：值对象体系条目已归零（条目数与余量口径由 09_05 台账用例维护）。"""
    entries = _baseline_entries()
    assert "value_object" not in {system for _rel, _name, system in entries}
    assert len(entries) <= 50, "基线只应递减（本批 110 处值对象归位后 ≤ 50）"


@pytest.mark.kiwi_id(2216)
def test_chat_stream_handle_migrated_to_framework_object() -> None:
    """复核迁出：`ChatStreamHandle`（运行时句柄）挂框架对象体系、非 dataclass、不属值对象体系。"""
    assert issubclass(ChatStreamHandle, BaseFrameworkObject)
    assert not issubclass(ChatStreamHandle, BaseValueObject)
    assert not dataclasses.is_dataclass(ChatStreamHandle)
    assert ChatStreamHandle.object_kind == "chat_stream_handle"
