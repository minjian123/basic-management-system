"""作用域资源归属能力域（07D `01_01`）：三级作用域值对象 + 资源类型注册只读视图。

**与数据范围正交**：本域回答「这条资源属于谁」（`tenant_id` / `module_key` / `resource_key`）；
`bms_core/scope/`（数据范围）回答「当前用户能看哪些行」。两者不互相替代（架构 41 §4.2-1），
故本域**独立成目录**，不并入 `scope/`。

口径：

- **值对象只承载值**：`ResourceScopeKey` 构造期只做形态校验（非法即 `ParamError`），
  「是否已登记 / 是否启用」属运行期判定，归作用域解析校验任务（`01_02`）；
- **注册记录只读**：记录由产品声明装载（第十类 `[[resource_types]]` → 注册通道 → 落库 → 投影），
  运行期只读；请求期一律查视图，**不回源库、不自建状态缓存**；
- **投影口径差异**：本域视图保留 `disabled`（要区分「未注册」与「已停用」，两类错误码不同），
  只排除 `retired`；其余九类声明投影只收 `enabled`；
- **声明态与运营态分离**：`status` 由声明写，`admin_status` 只由运营期停用写——声明重放不覆盖运营态。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import CatalogError, ParamError
from bms_core.core.objects import BaseRegistryRecordContract, BaseValueObject

__all__ = [
    "DEFAULT_RESOURCE_KEY_MAX_LENGTH",
    "MAX_RESOURCE_KEY_LENGTH",
    "MODULE_KEY_RE",
    "REMOVAL_POLICIES",
    "REMOVAL_POLICY_ARCHIVE",
    "REMOVAL_POLICY_PURGE",
    "RESOURCE_KEY_PATTERN_DEFAULT",
    "RESOURCE_KEY_RE",
    "RESOURCE_TYPE_KEY_RE",
    "SCOPE_RESOURCE_ADMIN_STATUSES",
    "SCOPE_RESOURCE_DISABLED",
    "SCOPE_RESOURCE_ENABLED",
    "SCOPE_RESOURCE_RETIRED",
    "SCOPE_RESOURCE_STATUSES",
    "ResourceScopeKey",
    "ScopeResourceTypeRecord",
    "find_scope_resource_type",
    "register_scope_resource_types",
    "reset_scope_resource_types",
    "scope_resource_type_issues",
    "scope_resource_type_key",
    "scope_resource_type_view",
    "scope_resource_types_of",
]

MODULE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""模块键形态（登记型标识 snake_case，与 `sys_module.module_key` 同口径）。"""

RESOURCE_TYPE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
"""类型标识形态：`{module_key}.{kind}`（两段点分小写；`module_key` 即命名空间）。"""

RESOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""`resource_key` 形态（登记型标识 snake_case；长度另由类型记录的 `max_length` 约束）。"""

RESOURCE_KEY_PATTERN_DEFAULT = r"^[a-z][a-z0-9_]{0,63}$"
"""缺省命名规则（64 位内 snake_case，与 `RESOURCE_KEY_RE` + 缺省 `max_length` 一致）。"""

DEFAULT_RESOURCE_KEY_MAX_LENGTH = 64
"""`resource_key` 缺省最大长度。"""

MAX_RESOURCE_KEY_LENGTH = 255
"""`resource_key` 允许的最大长度上限（类型记录不得声明更长的限制）。"""

MAX_NAME_PATTERN_LENGTH = 128
"""命名规则正则的最大长度（超长即拒，防「正则当程序」。）"""

MAX_PATTERN_QUANTIFIERS = 16
"""命名规则中量词符号的最大个数（`*` / `+` / `{n,m}`；防回溯爆炸）。"""

SCOPE_RESOURCE_ENABLED = "enabled"
"""声明态 / 运营态：启用。"""

SCOPE_RESOURCE_DISABLED = "disabled"
"""声明态 / 运营态：停用。"""

SCOPE_RESOURCE_RETIRED = "retired"
"""声明态：已退役（本次全量声明未出现；不删行、不物理回收）。"""

SCOPE_RESOURCE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (SCOPE_RESOURCE_ENABLED, SCOPE_RESOURCE_DISABLED, SCOPE_RESOURCE_RETIRED)
)
"""声明态取值清单。"""

SCOPE_RESOURCE_ADMIN_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (SCOPE_RESOURCE_ENABLED, SCOPE_RESOURCE_DISABLED)
)
"""运营态取值清单（运营期停用只有两态，退役不走运营态）。"""

REMOVAL_POLICY_ARCHIVE = "archive"
"""保留期到期处置：归档留存。"""

REMOVAL_POLICY_PURGE = "purge"
"""保留期到期处置：物理删除。"""

REMOVAL_POLICIES: ConcurrentStableList[str] = ConcurrentStableList((REMOVAL_POLICY_ARCHIVE, REMOVAL_POLICY_PURGE))
"""保留期到期处置取值清单。"""

_GROUP_QUANTIFIED = re.compile(r"\(([^()]*)\)(\*|\+|\{\d+,\d*\})")
"""「分组 + 紧随量词」形态（嵌套量词检测用）。"""

_UNBOUNDED_BODY = re.compile(r"[*+]|\{\d+,\}")
"""分组体内是否含无界量词。"""

_QUANTIFIER = re.compile(r"[*+]|\{\d+(,\d*)?\}")
"""量词计数用（`{n}` 与 `{n,m}` 各计一个）。"""


def scope_resource_type_key(module_key: str, resource_kind: str) -> str:
    """拼类型标识（`{module_key}.{kind}`）。

    Args:
        module_key: 模块键。
        resource_kind: 类型短名。

    Returns:
        str: 类型标识。
    """
    return f"{module_key}.{resource_kind}"


@dataclass(frozen=True)
class ResourceScopeKey(BaseValueObject):
    """三级作用域值对象：`tenant_id / module_key / resource_key`（不可变）。

    构造期只做**形态**校验；「已登记 / 已启用」判定归作用域解析与校验（`01_02`），
    登记记录查询用 `find_scope_resource_type()`。

    Attributes:
        tenant_id: 租户雪花主键（**不可变**；不得用租户编码参与标识）。
        module_key: 模块键（已登记且启用的模块键，值本身不在此校验登记态）。
        resource_key: 资源标识（产品定义、必须已注册类型；模块级作用域为 None）。
    """

    tenant_id: int
    module_key: str
    resource_key: str | None = None

    def __post_init__(self) -> None:
        """形态校验（非法即 `ParamError`，10001）。

        Raises:
            ParamError: 租户主键非正、模块键或资源标识形态非法。
        """
        if self.tenant_id <= 0:
            raise ParamError(f"作用域租户主键非法（须为雪花 id 且大于 0）：{self.tenant_id}")
        if not MODULE_KEY_RE.fullmatch(self.module_key):
            raise ParamError(f"作用域模块键形态非法（snake_case）：{self.module_key}")
        if self.resource_key is not None and not RESOURCE_KEY_RE.fullmatch(self.resource_key):
            raise ParamError(f"作用域资源标识形态非法（snake_case）：{self.resource_key}")

    def with_resource(self, resource_key: str) -> ResourceScopeKey:
        """派生带资源标识的新作用域（原实例不变）。

        Args:
            resource_key: 资源标识。

        Returns:
            ResourceScopeKey: 新作用域实例。
        """
        return ResourceScopeKey(
            tenant_id=self.tenant_id,
            module_key=self.module_key,
            resource_key=resource_key,
        )

    def as_text(self) -> str:
        """作用域文本形态（缓存键 / 审计定位用；空资源位留空段）。

        Returns:
            str: `{tenant_id}/{module_key}/{resource_key}`。
        """
        return f"{self.tenant_id}/{self.module_key}/{self.resource_key or ''}"


@dataclass(frozen=True)
class ScopeResourceTypeRecord(BaseRegistryRecordContract):
    """作用域资源类型注册记录（字段与 `sys_scope_resource_type` 对齐）。

    Attributes:
        resource_type_key: 类型标识 `{module_key}.{kind}`（全局唯一，业务键）。
        name: 显示名。
        name_pattern: `resource_key` 取值正则。
        max_length: `resource_key` 最大长度。
        retention_days: 保留期（天；0 = 永久保留）。
        removal_policy: 保留期到期处置（archive / purge）。
        product_key: 声明方产品键。
        status: 声明态（enabled / disabled / retired）。
        admin_status: 运营态（enabled / disabled；非声明要素，声明重放不写）。
        declaration_version: 声明版本（内容变更 +1；非声明要素）。
    """

    resource_type_key: str
    name: str
    name_pattern: str = RESOURCE_KEY_PATTERN_DEFAULT
    max_length: int = DEFAULT_RESOURCE_KEY_MAX_LENGTH
    retention_days: int = 0
    removal_policy: str = REMOVAL_POLICY_ARCHIVE
    product_key: str = ""
    status: str = SCOPE_RESOURCE_ENABLED
    admin_status: str = SCOPE_RESOURCE_ENABLED
    declaration_version: int = 1

    @property
    def module_key(self) -> str:
        """所属模块键（由类型标识前缀派生，不另落列）。

        Returns:
            str: 模块键（标识不含点时回落整串）。
        """
        return self.resource_type_key.split(".", 1)[0]

    @property
    def resource_kind(self) -> str:
        """类型短名（由类型标识派生）。

        Returns:
            str: 类型短名（标识不含点时为整串）。
        """
        parts = self.resource_type_key.split(".", 1)
        return parts[1] if len(parts) > 1 else parts[0]

    def is_active(self) -> bool:
        """是否有效启用（声明态与运营态同时 enabled）。

        Returns:
            bool: 有效启用为 True。
        """
        return self.status == SCOPE_RESOURCE_ENABLED and self.admin_status == SCOPE_RESOURCE_ENABLED

    def accepts(self, resource_key: str) -> bool:
        """`resource_key` 是否满足本类型的命名规则与长度约束。

        Args:
            resource_key: 待判定的资源标识。

        Returns:
            bool: 命中为 True（正则已登记、可安全编译）。
        """
        if len(resource_key) > self.max_length:
            return False
        return _compile_pattern(self.name_pattern).fullmatch(resource_key) is not None

    @classmethod
    def from_row(cls, row: object) -> ScopeResourceTypeRecord:
        """按登记字段从 ORM 行（或任意同构对象）构造记录。

        Args:
            row: 具备登记字段的对象（如 `SysScopeResourceType` 行）。

        Returns:
            ScopeResourceTypeRecord: 注册记录。
        """
        data = cast("Any", row)
        return cls(
            resource_type_key=str(data.resource_type_key),
            name=str(data.name),
            name_pattern=str(data.name_pattern),
            max_length=int(data.max_length),
            retention_days=int(data.retention_days),
            removal_policy=str(data.removal_policy),
            product_key=str(data.product_key),
            status=str(data.status),
            admin_status=str(getattr(data, "admin_status", SCOPE_RESOURCE_ENABLED)),
            declaration_version=int(getattr(data, "declaration_version", 1)),
        )


_RESOURCE_TYPES: ConcurrentStableDict[str, ScopeResourceTypeRecord] = ConcurrentStableDict()
"""运行期只读视图：`{resource_type_key: 记录}`（由注册表投影整表重建）。"""


def register_scope_resource_types(records: Iterable[ScopeResourceTypeRecord]) -> None:
    """装载注册记录（同键同值合并、同键异值即拒）。

    Args:
        records: 注册记录（插入序）。

    Raises:
        CatalogError: 同一类型标识被装载为两份不同内容（视图层安全口径，不为投影放宽）。
    """
    for record in records:
        existing = _RESOURCE_TYPES.get(record.resource_type_key)
        if existing is not None and existing != record:
            raise CatalogError(f"作用域资源类型装载冲突：{record.resource_type_key}（同键异值）")
        _RESOURCE_TYPES.set(record.resource_type_key, record)


def reset_scope_resource_types() -> None:
    """复位视图（投影整表重建与用例隔离用）。"""
    _RESOURCE_TYPES.clear()


def scope_resource_type_view() -> ConcurrentStableDict[str, ScopeResourceTypeRecord]:
    """取注册类型视图（只读副本；调用方不得写回）。

    Returns:
        ConcurrentStableDict[str, ScopeResourceTypeRecord]: `{类型标识: 记录}`。
    """
    return ConcurrentStableDict(_RESOURCE_TYPES.items())


def find_scope_resource_type(module_key: str, resource_kind: str) -> ScopeResourceTypeRecord | None:
    """按模块键 + 类型短名取记录（**请求期唯一查询入口，不查库**）。

    Args:
        module_key: 模块键。
        resource_kind: 类型短名。

    Returns:
        ScopeResourceTypeRecord | None: 记录；未登记为 None（调用方据此 fail-closed）。
    """
    return _RESOURCE_TYPES.get(scope_resource_type_key(module_key, resource_kind))


def scope_resource_types_of(module_key: str) -> ConcurrentStableList[ScopeResourceTypeRecord]:
    """取某模块下的全部类型（插入序；运营视图分组用）。

    Args:
        module_key: 模块键。

    Returns:
        ConcurrentStableList[ScopeResourceTypeRecord]: 该模块的类型记录（未登记为空列表）。
    """
    return ConcurrentStableList(record for record in _RESOURCE_TYPES.values() if record.module_key == module_key)


def scope_resource_type_issues(
    record: ScopeResourceTypeRecord, *, module_keys: ConcurrentStableSet[str]
) -> ConcurrentStableList[str]:
    """注册记录的装载期形态校验（V1 / V2 / V5 / V6 / V7）。

    唯一实现：装配期（`inspect_product_manifests`）与注册期（注册通道）复用同一函数；
    跨产品唯一性（V4）与「模块键已登记且启用」（V3）需注册表现状，由调用方判定。

    Args:
        record: 待校验的注册记录。
        module_keys: 本产品**有权声明**的模块键集合（清单服务行 ∪ 注册表已登记本产品模块键）。

    Returns:
        ConcurrentStableList[str]: 问题明细（空 = 通过）。
    """
    issues: ConcurrentStableList[str] = ConcurrentStableList()
    key = record.resource_type_key
    if not RESOURCE_TYPE_KEY_RE.fullmatch(key) or len(key) > 128:
        issues.add(f"类型标识形态非法（须为 {{module_key}}.{{kind}}，snake_case 点分）：{key}")
        return issues
    if record.module_key not in module_keys:
        issues.add(f"类型标识 {key} 的模块键 {record.module_key} 不属于本产品（须先声明服务行）")
    if not record.name or len(record.name) > 64:
        issues.add(f"类型 {key} 的显示名为空或超长（≤64）：{record.name!r}")
    if not 1 <= record.max_length <= MAX_RESOURCE_KEY_LENGTH:
        issues.add(f"类型 {key} 的 max_length 越界（1~{MAX_RESOURCE_KEY_LENGTH}）：{record.max_length}")
    if record.retention_days < 0:
        issues.add(f"类型 {key} 的保留期非法（≥0）：{record.retention_days}")
    if record.removal_policy not in REMOVAL_POLICIES:
        issues.add(f"类型 {key} 的到期处置非法（archive / purge）：{record.removal_policy}")
    if record.status not in (SCOPE_RESOURCE_ENABLED, SCOPE_RESOURCE_DISABLED):
        issues.add(f"类型 {key} 的声明态非法（enabled / disabled；退役由未声明表达）：{record.status}")
    issues.update(_pattern_issues(key, record.name_pattern, record.max_length))
    return issues


def _pattern_issues(key: str, pattern: str, max_length: int) -> ConcurrentStableList[str]:
    """命名规则校验（可编译 / 长度 / 量词 / 与长度自洽）。

    Args:
        key: 类型标识（错误信息用）。
        pattern: 命名规则正则。
        max_length: 声明最大长度。

    Returns:
        ConcurrentStableList[str]: 问题明细。
    """
    issues: ConcurrentStableList[str] = ConcurrentStableList()
    if not pattern or len(pattern) > MAX_NAME_PATTERN_LENGTH:
        issues.add(f"类型 {key} 的命名规则为空或超长（≤{MAX_NAME_PATTERN_LENGTH}）：{pattern!r}")
        return issues
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        issues.add(f"类型 {key} 的命名规则无法编译：{exc}")
        return issues
    if len(_QUANTIFIER.findall(pattern)) > MAX_PATTERN_QUANTIFIERS:
        issues.add(f"类型 {key} 的命名规则量词过多（≤{MAX_PATTERN_QUANTIFIERS}）")
    if _has_nested_unbounded(pattern):
        issues.add(f"类型 {key} 的命名规则含嵌套无界量词（回溯风险）：{pattern!r}")
    if compiled.fullmatch("") is not None:
        issues.add(f"类型 {key} 的命名规则接受空串（形同虚设）：{pattern!r}")
    if compiled.fullmatch("a" * (max_length + 1)) is not None:
        issues.add(f"类型 {key} 的命名规则未约束长度（应拒绝 {max_length + 1} 位取值）：{pattern!r}")
    return issues


def _has_nested_unbounded(pattern: str) -> bool:
    """是否存在「无界量词作用于含无界量词的分组」。

    Args:
        pattern: 命名规则正则。

    Returns:
        bool: 存在嵌套无界量词为 True。
    """
    for match in _GROUP_QUANTIFIED.finditer(pattern):
        body, quantifier = match.group(1), match.group(2)
        unbounded_quantifier = quantifier in ("*", "+") or re.fullmatch(r"\{\d+,\}", quantifier) is not None
        if unbounded_quantifier and _UNBOUNDED_BODY.search(body):
            return True
    return False


@lru_cache(maxsize=128)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """编译命名规则（按 pattern 缓存；装载期已校验可编译）。

    Args:
        pattern: 命名规则正则。

    Returns:
        re.Pattern[str]: 编译结果。
    """
    return re.compile(pattern)
