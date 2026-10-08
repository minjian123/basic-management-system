"""用户权限快照（域 `permission`）。

一次计算（主体链收敛 → 权限聚合 → 数据范围 / 字段权限收窄）落一份快照，供**四处消费**：

1. 两级校验点（`require_permission` 的业务级 / 动作级判定）；
2. 字段权限（读不返回 / 写拒绝）；
3. 数据范围（读注入 / 写校验）；
4. 权限概要（`/api/v1/menus/my` 供数）。

**对后代的接口承诺**：核心字段（`business_codes` / `action_codes` / `data_scopes` / `field_perms` / `tier` /
`profile`）语义**不得变更**；后代新增维度一律放 `extensions`（见《02_04 详细设计》§11.2 接缝 5）。

**`tier` 与 `profile` 的区别（易混）**：`tier` 是主体层级的**豁免标记**（超管 / 系统管理员 → 校验恒真）；
`profile` 是**引擎档位**（能力集合，见 `permission/profile.py`）。
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import PermissionError
from bms_core.core.objects import BaseDataContract
from bms_core.permission.field import FieldPermission
from bms_core.permission.profile import DEFAULT_PROFILE

TIER_STANDARD = "standard"
"""层级：普通主体（按权限码判定）。"""

TIER_SYSTEM_ADMIN = "system_admin"
"""层级：系统管理员（租户内豁免全权）。"""

TIER_PLATFORM_ADMIN = "platform_admin"
"""层级：平台超管（跨租户运营，豁免全权）。"""

EXEMPT_TIERS: tuple[str, ...] = (TIER_SYSTEM_ADMIN, TIER_PLATFORM_ADMIN)
"""豁免层级集合（`check` 恒真）。"""


@dataclass
class PermissionSnapshot(BaseDataContract):
    """用户权限快照（一次计算、四处消费；缓存载荷经 `to_payload` / `from_payload` 往返）。"""

    version: int = 0
    """生成时的租户权限版本（校验与排障用）。"""
    profile: str = DEFAULT_PROFILE
    """引擎档位（`smb` / `enterprise` / `enterprise_hr`）。"""
    tier: str = TIER_STANDARD
    """主体层级（`standard` / `system_admin` / `platform_admin`）。"""
    business_codes: ConcurrentStableSet[str] = field(default_factory=lambda: ConcurrentStableSet[str]())
    """业务码集合（表单 / 业务级校验与菜单入口可见性）。"""
    action_codes: ConcurrentStableSet[str] = field(default_factory=lambda: ConcurrentStableSet[str]())
    """动作码集合（`业务:动作`，按钮显隐与动作级校验）。"""
    data_scopes: ConcurrentStableList[ConcurrentStableDict[str, object]] = field(
        default_factory=lambda: ConcurrentStableList[ConcurrentStableDict[str, object]]()
    )
    """数据范围规则（`dict_type` / `policy_type` / `config`；读注入与写校验）。"""
    field_perms: ConcurrentStableList[FieldPermission] = field(
        default_factory=lambda: ConcurrentStableList[FieldPermission]()
    )
    """字段权限收窄项（读过滤与写拒绝；未列出的字段默认全开）。"""
    extensions: ConcurrentStableDict[str, object] = field(default_factory=lambda: ConcurrentStableDict[str, object]())
    """扩展位：后代档位自有数据（基础版为空），**新增维度只进此处**。"""

    def holds(self, code: str) -> bool:
        """是否持指定权限码（业务码或动作码命中即通过）。

        Args:
            code: 权限码（业务码或 `业务:动作`）。

        Returns:
            bool: 持有为 True。
        """
        return code in self.business_codes or code in self.action_codes

    @property
    def exempt(self) -> bool:
        """是否豁免主体（超管 / 系统管理员，校验恒真）。

        Returns:
            bool: 豁免为 True。
        """
        return self.tier in EXEMPT_TIERS

    def field_state(self, form_id: int, field_key: str) -> tuple[bool, bool] | None:
        """取字段收窄态（多角色从严：任一角色不可见即不可见、任一不可编辑即不可编辑）。

        Args:
            form_id: 表单 id。
            field_key: 字段键。

        Returns:
            tuple[bool, bool] | None: `(visible, editable)`；该字段无任何收窄项时返回 `None`（默认全开）。
        """
        visible = True
        editable = True
        matched = False
        for item in self.field_perms:
            if item.form_id != form_id or item.field_key != field_key:
                continue
            matched = True
            visible = visible and item.visible
            editable = editable and item.editable
        return (visible, editable) if matched else None

    def to_payload(self) -> ConcurrentStableDict[str, object]:
        """缓存序列化载荷（JSON 友好；字段顺序稳定）。

        Returns:
            ConcurrentStableDict[str, object]: 载荷。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        payload.set("version", self.version)
        payload.set("profile", self.profile)
        payload.set("tier", self.tier)
        payload.set("business_codes", list(self.business_codes))
        payload.set("action_codes", list(self.action_codes))
        payload.set("data_scopes", [dict(item) for item in self.data_scopes])
        payload.set(
            "field_perms",
            [
                {
                    "form_id": item.form_id,
                    "field_key": item.field_key,
                    "visible": item.visible,
                    "editable": item.editable,
                }
                for item in self.field_perms
            ],
        )
        payload.set("extensions", dict(self.extensions))
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> PermissionSnapshot:
        """缓存反序列化（缺字段 / 类型异常容错：回落默认，不抛错）。

        Args:
            payload: 缓存载荷（`to_payload` 产物或等价映射 / 任意缓存值）。

        Returns:
            PermissionSnapshot: 快照。
        """
        row = _as_stable(payload)
        business = ConcurrentStableSet[str]()
        business.update(item for item in _as_list(row.get("business_codes")) if isinstance(item, str))
        actions = ConcurrentStableSet[str]()
        actions.update(item for item in _as_list(row.get("action_codes")) if isinstance(item, str))
        scopes: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for item in _as_list(row.get("data_scopes")):
            scopes.add(_as_stable(item))
        fields: ConcurrentStableList[FieldPermission] = ConcurrentStableList()
        for item in _as_list(row.get("field_perms")):
            fields.add(_as_field_permission(item))
        raw_version = row.get("version")
        version = raw_version if isinstance(raw_version, int) and not isinstance(raw_version, bool) else 0
        raw_profile = row.get("profile")
        profile = raw_profile if isinstance(raw_profile, str) else DEFAULT_PROFILE
        raw_tier = row.get("tier")
        tier = raw_tier if isinstance(raw_tier, str) else TIER_STANDARD
        return cls(
            version=version,
            profile=profile,
            tier=tier,
            business_codes=business,
            action_codes=actions,
            data_scopes=scopes,
            field_perms=fields,
            extensions=_as_stable(row.get("extensions")),
        )


def _as_list(value: object) -> ConcurrentStableList[object]:
    """把载荷值规整为保序列表（非列表 / 元组返回空）。

    Args:
        value: 载荷值。

    Returns:
        ConcurrentStableList[object]: 保序列表。
    """
    result: ConcurrentStableList[object] = ConcurrentStableList()
    if isinstance(value, ConcurrentStableList):
        result.update(cast("Any", value))
    elif isinstance(value, list | tuple):
        result.update(cast("list[object] | tuple[object, ...]", value))
    return result


def _as_stable(value: object) -> ConcurrentStableDict[str, object]:
    """把载荷值规整为保序映射（键字符串化；非映射返回空）。

    Args:
        value: 载荷值（`dict` / `ConcurrentStableDict` / 其它）。

    Returns:
        ConcurrentStableDict[str, object]: 保序映射。
    """
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if isinstance(value, ConcurrentStableDict | dict):
        for key, item in cast("Any", value).items():
            result.set(str(key), item)
    return result


def _as_field_permission(value: object) -> FieldPermission:
    """把载荷值规整为字段权限收窄项（缺字段容错）。

    Args:
        value: 载荷值（字段权限映射）。

    Returns:
        FieldPermission: 收窄项。
    """
    row = _as_stable(value)
    raw_form_id = row.get("form_id")
    form_id = raw_form_id if isinstance(raw_form_id, int) and not isinstance(raw_form_id, bool) else 0
    raw_field_key = row.get("field_key")
    field_key = raw_field_key if isinstance(raw_field_key, str) else ""
    return FieldPermission(
        form_id=form_id,
        field_key=field_key,
        visible=bool(row.get("visible", True)),
        editable=bool(row.get("editable", True)),
    )


current_permission_snapshot: ContextVar[PermissionSnapshot | None] = ContextVar(
    "current_permission_snapshot", default=None
)
"""当前请求的用户权限快照（**引擎契约位**：真实校验器在请求级预加载时写入；请求间隔离）。

放基座而非某服务的校验器内：字段权限标记 / 数据范围注入 / 权限概要等**消费方**都要读它，
它们不该依赖某个具体 provider 服务的内部模块。
"""


def assert_fields_writable(*, form_id: int, values: ConcurrentStableDict[str, object]) -> None:
    """写时字段校验（**服务层写入口显式调用**的接缝）。

    口径（《02_04 详细设计》§4 / §5.5）：默认全开、只登记收窄项；含**不可编辑**字段即拒
    （`30001`）。豁免层级与未预加载（无快照）放行——写入口的登录态与权限码由认证链与
    `require_permission` 承担，本函数只管字段粒度。

    Args:
        form_id: 目标表单 id。
        values: 待写入字段值（字段键 → 值）。

    Raises:
        PermissionError: 含不可编辑字段（30001 / 403）。
    """
    snapshot = get_current_permission_snapshot()
    if snapshot is None or snapshot.exempt:
        return
    blocked: ConcurrentStableList[str] = ConcurrentStableList()
    for field_key in values:
        state = snapshot.field_state(form_id, field_key)
        if state is not None and not state[1]:
            blocked.add(field_key)
    if blocked:
        raise PermissionError(f"字段不可编辑：{', '.join(blocked)}")


def set_current_permission_snapshot(snapshot: PermissionSnapshot | None) -> None:
    """写入当前请求的用户权限快照。

    Args:
        snapshot: 权限快照；None 表示清空（无用户上下文 / 用例隔离）。
    """
    current_permission_snapshot.set(snapshot)


def get_current_permission_snapshot() -> PermissionSnapshot | None:
    """取当前请求的用户权限快照。

    Returns:
        PermissionSnapshot | None: 快照；未预加载为 None（消费方自行决定从严或放宽）。
    """
    return current_permission_snapshot.get()
