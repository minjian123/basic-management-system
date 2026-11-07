"""审计能力域：ORM 字段级变更捕获基座契约（哈希链在阶段六回补）。

**扩展字段（07D `02_04`）**：标准字段（谁 / 何时 / 对什么 / 做了什么 / 结果 / 来源与链路）之外，
产品可补**有契约的扩展位**——记录级定位 `record_ref` 与自定义 `extensions`：

- `capture_extended()` 是**基类缺省方法**（非抽象）：先调既有 `capture()`，再把扩展位追加进载荷
  返回**新信封**——既有实现与调用点零改动；
- 扩展位只补充语义，**不改变哈希链构造与归档口径**（链算法不分支，新键自然参与规范化序列化）；
- 值域收敛：键 ≤16 个、值只允许标量且字符串 ≤255，且不得占用标准字段名（防洪泛与结构漂移）。
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseDataContract, BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.events.base import EventEnvelope

_RECORD_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$")
"""记录类型形态（两段点分小写，与资源类型标识同形）。"""

_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
"""记录主键形态（雪花 id / 业务主键；不含空白与通配符）。"""

_EXTENSION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""扩展位键形态（snake_case，≤32）。"""

__all__ = [
    "AUDIT_EXTENSION_RESERVED_KEYS",
    "MAX_AUDIT_EXTENSIONS",
    "MAX_AUDIT_EXTENSION_VALUE_LENGTH",
    "AuditCapturer",
    "FieldChange",
    "RecordRef",
    "validate_audit_extensions",
    "with_audit_extensions",
]

MAX_AUDIT_EXTENSIONS = 16
"""扩展位键的最大个数（防审计洪泛）。"""

MAX_AUDIT_EXTENSION_VALUE_LENGTH = 255
"""扩展位字符串值的最大长度。"""

AUDIT_EXTENSION_RESERVED_KEYS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "module",
        "action",
        "method",
        "path",
        "status",
        "tenant_id",
        "module_key",
        "resource_key",
        "user_id",
        "username",
        "query",
        "params",
        "ip",
        "user_agent",
        "cost_time",
        "error_msg",
        "record_ref",
        "extensions",
        "table",
        "model_id",
        "domain_key",
    )
)
"""扩展位不得占用的载荷键（标准字段名；冲突即拒，避免覆盖语义）。"""


@dataclass
class FieldChange(BaseDataContract):
    """字段级变更：字段名 + 旧值 / 新值。"""

    field: str
    old: object = None
    new: object = None


@dataclass(frozen=True)
class RecordRef(BaseValueObject):
    """记录级定位：从审计条目一次定位到记录（`type` + 主键）。"""

    type: str
    """记录类型：资源类型标识（`msg.topic`）或逻辑表名；形态 `[a-z][a-z0-9_]*` 可带一段点分。"""

    id: str
    """记录主键（雪花 id 十进制字符串；也接受业务主键字符串）。"""

    def __post_init__(self) -> None:
        """形态校验。

        Raises:
            ParamError: 类型形态非法 / 主键为空或含非法字符（10001）。
        """
        if not _RECORD_TYPE_RE.match(self.type) or len(self.type) > 64:
            raise ParamError(f"审计记录级定位的类型非法：{self.type!r}（须小写标识符，可带一段点分，≤64）")
        if not self.id or len(self.id) > 64 or not _RECORD_ID_RE.match(self.id):
            raise ParamError(f"审计记录级定位的主键非法：{self.id!r}（非空、≤64、仅字母数字与 `_:-`）")

    def to_payload(self) -> ConcurrentStableDict[str, object]:
        """转载荷形态。

        Returns:
            ConcurrentStableDict[str, object]: `{"type": ..., "id": ...}`。
        """
        return ConcurrentStableDict({"type": self.type, "id": self.id})


class AuditCapturer(BasePluggable, ABC):
    """审计捕获基座契约：关键表字段级变更 → 审计事件。"""

    key: str = "audit"
    plugin_key: str = "audit"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def is_audited(self, table: str) -> bool:
        """判断表是否纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: 纳入为 True。
        """

    @abstractmethod
    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """捕获字段级变更并生成审计事件。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更列表。
            actor: 操作者 ID。

        Returns:
            EventEnvelope: 审计事件信封（实现须在 `payload["domain_key"]` 标注业务域，取值经
            `collaboration/domain_scope.py::domain_of_table` 由表归属派生——07C `04_03`）。
        """

    def capture_extended(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
        record_ref: RecordRef | None = None,
        extensions: Mapping[str, object] | None = None,  # bare-collections:allow（只读映射入参）
    ) -> EventEnvelope:
        """捕获字段级变更并追加扩展位（记录级定位 + 产品自定义字段）。

        **缺省方法**（非抽象）：调既有 `capture()` 后追加扩展位，返回新信封——既有实现零改动；
        扩展位为空时不改动载荷（不写空对象 / null）。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更列表。
            actor: 操作者 ID。
            record_ref: 记录级定位（涉及具体记录的操作才给）。
            extensions: 产品自定义标量字段（键不得占用标准字段名）。

        Returns:
            EventEnvelope: 追加扩展位后的新信封（原信封不变）。

        Raises:
            ParamError: 扩展位键 / 值非法（10001）。
        """
        event = self.capture(table=table, model_id=model_id, changes=changes, actor=actor)
        return with_audit_extensions(event, record_ref=record_ref, extensions=extensions)


def validate_audit_extensions(  # bare-collections:allow（只读映射入参）
    extensions: Mapping[str, object],  # bare-collections:allow（只读映射入参）
) -> ConcurrentStableDict[str, object]:
    """校验并冻结扩展位（键形态 / 数量 / 值域 / 保留键）。

    Args:
        extensions: 原始扩展位映射。

    Returns:
        ConcurrentStableDict[str, object]: 校验通过的副本（保持插入序）。

    Raises:
        ParamError: 键形态非法、超过 `MAX_AUDIT_EXTENSIONS`、占用保留键或值非标量（10001）。
    """
    if len(extensions) > MAX_AUDIT_EXTENSIONS:
        raise ParamError(f"审计扩展位键过多：{len(extensions)}（上限 {MAX_AUDIT_EXTENSIONS}）")
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in extensions.items():
        if not _EXTENSION_KEY_RE.match(key) or len(key) > 32:
            raise ParamError(f"审计扩展位键非法：{key!r}（须小写标识符 snake_case，≤32）")
        if key in AUDIT_EXTENSION_RESERVED_KEYS:
            raise ParamError(f"审计扩展位键与标准字段冲突：{key!r}")
        if isinstance(value, str):
            if len(value) > MAX_AUDIT_EXTENSION_VALUE_LENGTH:
                raise ParamError(
                    f"审计扩展位值超长：{key}={len(value)} 字符（上限 {MAX_AUDIT_EXTENSION_VALUE_LENGTH}）"
                )
        elif value is not None and not isinstance(value, (bool, int, float)):
            raise ParamError(f"审计扩展位值须为标量（str/int/float/bool/None）：{key}={type(value).__name__}")
        result.set(key, value)
    return result


def with_audit_extensions(
    event: EventEnvelope,
    *,
    record_ref: RecordRef | None = None,
    extensions: Mapping[str, object] | None = None,  # bare-collections:allow（只读映射入参）
) -> EventEnvelope:
    """把扩展位追加进事件载荷，返回新信封（载荷只增不删）。

    Args:
        event: 原事件信封。
        record_ref: 记录级定位（`None` 不写该键）。
        extensions: 产品自定义字段（`None` / 空不写该键）。

    Returns:
        EventEnvelope: 新信封；两个扩展位都为空时原样返回同一对象。

    Raises:
        ParamError: 扩展位非法（10001）。
    """
    if record_ref is None and not extensions:
        return event
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(dict(event.payload.items()))
    if record_ref is not None:
        payload.set("record_ref", record_ref.to_payload())
    if extensions:
        payload.set("extensions", validate_audit_extensions(extensions))
    return replace(event, payload=payload)


def get_audit_capturer(request: Request) -> AuditCapturer:
    """依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

    Args:
        request: 应用请求（取装配 settings）。

    Returns:
        AuditCapturer: 应用装配的审计捕获实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "AuditCapturer",
        resolve_plugin(
            "audit",
            settings.audit.provider,
            expected_version=AuditCapturer.contract_version,
        ),
    )
