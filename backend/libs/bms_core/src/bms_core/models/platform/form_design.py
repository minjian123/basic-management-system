"""表单定制域模型：布局 / 字段属性 / 租户自建字段（含多语言附表）。

- 归属：业务域 `form_design`（承载服务 `platform`，库类别 `tenant`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_form_layout.md` 等四份表文件，
  节点 [37-表单定制](../../../../../bms文档/设计/数据库设计/37_数据库设计_表单定制.md)）；
- **定位列统一 `form_code`**（业务码字符串，逻辑引用平台库 `sys_business.code`）：不存雪花
  `form_id`，避免渲染热路径跨库、以及删库重建后 ID 漂移（任务 10_01 决策 17）；
- **`role_id = 0`** 表示非角色层级：`(form_code, scope, role_id, deleted_at)` 复合唯一在
  `NULL` 上不生效（NULL 互不相等，四库同语义），用 `0` 占位保证「同表单同层级仅一条」成立
  （与 `sys_role_permission.source_menu_id` 同范式）；
- **`ext_*` 物理列不在任何建表链**：由表单定制域的 DDL 执行器在运行期对业务表加列，元数据在本表；
  列类型按 `bms_core/fieldtype/mapping.py` 四库映射，由 SQLAlchemy 按方言编译（不拼字符串）。
"""

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import BaseModel, SnowflakeId

SCOPE_PLATFORM = "platform"
"""布局 / 属性层级：平台默认（租户开通种子复制到各租户库）。"""

SCOPE_TENANT = "tenant"
"""布局 / 属性层级：租户覆盖。"""

SCOPE_ROLE = "role"
"""布局 / 属性层级：角色视图。"""

LAYOUT_SCOPES: ConcurrentStableList[str] = ConcurrentStableList((SCOPE_PLATFORM, SCOPE_TENANT, SCOPE_ROLE))
"""层级取值（与前端 `DesignerLevel` 一致）。"""

NO_ROLE_ID = 0
"""非角色层级的占位角色 ID（规避唯一约束在 NULL 上的跨库语义差异）。"""

DDL_STATUS_PENDING = "pending"
"""建列生命周期：待建列。"""

DDL_STATUS_ACTIVE = "active"
"""建列生命周期：已生效。"""

DDL_STATUS_FAILED = "failed"
"""建列生命周期：建列失败（可重试）。"""

DDL_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (DDL_STATUS_PENDING, DDL_STATUS_ACTIVE, DDL_STATUS_FAILED)
)
"""建列生命周期取值。"""

EXT_FIELD_TYPES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "text",
        "longtext",
        "number",
        "datetime",
        "option",
        "option_multi",
        "switch",
        "file",
    )
)
"""自建字段类型白名单（对齐《概要设计 · 表单定制》「组件类型与自建字段边界」节；富文本不放开）。"""

EXT_OPTION_TYPES: ConcurrentStableList[str] = ConcurrentStableList(("option", "option_multi"))
"""需要选项集的自建字段类型。"""

EXT_COLUMN_PREFIX = "ext_"
"""自建字段物理列名前缀。"""


class SysFormLayout(BaseModel):
    """表单三级布局（`sys_form_layout`）：同表单下各层级各一份，可缺失（缺失即回退下一级）。"""

    __tablename__ = "sys_form_layout"
    __table_args__ = (
        UniqueConstraint(
            "form_code",
            "scope",
            "role_id",
            "deleted_at",
            name="uq_sys_form_layout_form_scope_role_deleted_at",
        ),
    )

    form_code: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="表单标识（业务码，逻辑外键 → 平台库 sys_business.code，跨库；保存后不变）",
    )
    scope: Mapped[str] = mapped_column(String(16), comment="层级（platform/tenant/role）")
    role_id: Mapped[int] = mapped_column(
        SnowflakeId, default=NO_ROLE_ID, comment="角色 ID（逻辑外键 → sys_role.id，同库；0 = 非角色层级）"
    )
    layout_config: Mapped[str] = mapped_column(
        Text, comment="布局配置 JSON 文本（main + query + detail + dictAdvanced）；应用层解析"
    )
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysFormFieldAttr(BaseModel):
    """表单三级字段属性（`sys_form_field_attr`）：与布局同层同源，承载平台字段与租户覆盖的属性。"""

    __tablename__ = "sys_form_field_attr"
    __table_args__ = (
        UniqueConstraint(
            "form_code",
            "scope",
            "role_id",
            "field_key",
            "deleted_at",
            name="uq_sys_form_field_attr_form_scope_role_field_deleted_at",
        ),
    )

    form_code: Mapped[str] = mapped_column(
        String(64), index=True, comment="表单标识（业务码，逻辑外键 → 平台库 sys_business.code，跨库）"
    )
    scope: Mapped[str] = mapped_column(String(16), comment="层级（platform/tenant/role）")
    role_id: Mapped[int] = mapped_column(
        SnowflakeId, default=NO_ROLE_ID, comment="角色 ID（逻辑外键 → sys_role.id，同库；0 = 非角色层级）"
    )
    field_key: Mapped[str] = mapped_column(
        String(64), comment="字段键（引用 sys_field.field_key 或 sys_field_ext.field_key；允许先于字段定义配置）"
    )
    attrs: Mapped[str] = mapped_column(
        Text,
        comment="字段属性 JSON 文本（required / placeholder / defaultValue / rules / optionSetKey 等）",
    )


class SysFieldExt(BaseModel):
    """租户自建字段（`sys_field_ext`）：元数据 + `ext_*` 物理列生命周期。"""

    __tablename__ = "sys_field_ext"
    __table_args__ = (
        UniqueConstraint("form_code", "field_key", "deleted_at", name="uq_sys_field_ext_form_key_deleted_at"),
        UniqueConstraint("form_code", "column_name", "deleted_at", name="uq_sys_field_ext_form_column_deleted_at"),
    )

    form_code: Mapped[str] = mapped_column(
        String(64), index=True, comment="表单标识（业务码，逻辑外键 → 平台库 sys_business.code，跨库）"
    )
    field_key: Mapped[str] = mapped_column(
        String(64), comment="字段键（表单内唯一；小写字母开头，仅小写字母/数字/下划线，≤60）"
    )
    name: Mapped[str] = mapped_column(
        String(128), comment="字段名（按优先级兜底派生的快照；多语言见 sys_field_ext_i18n）"
    )
    type: Mapped[str] = mapped_column(
        String(32), comment="字段类型（text/longtext/number/datetime/option/option_multi/switch/file）"
    )
    option_set_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="选项集标识引用（仅 option/option_multi；不存选项条目数组）"
    )
    column_name: Mapped[str] = mapped_column(
        String(64), comment="物理列名（ext_ + 蛇形 field_key，≤64；服务端派生，不接受调用方指定）"
    )
    table_name: Mapped[str] = mapped_column(
        String(64), comment="目标物理表名（由 form_code 经表单清单解析得出；仅供巡检对账，不作判定依据）"
    )
    ddl_status: Mapped[str] = mapped_column(
        String(16), default=DDL_STATUS_PENDING, comment="建列生命周期（pending/active/failed）"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同表单内排序（升序）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled；停用不删列）")


class SysFieldExtI18n(BaseModel):
    """租户自建字段名多语言附表（`sys_field_ext_i18n`）。"""

    __tablename__ = "sys_field_ext_i18n"
    __table_args__ = (
        UniqueConstraint("field_id", "locale", "deleted_at", name="uq_sys_field_ext_i18n_field_locale_deleted_at"),
    )

    field_id: Mapped[int] = mapped_column(SnowflakeId, comment="自建字段 ID（逻辑外键 → sys_field_ext.id，同库）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（IETF 标准形态，如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="字段名的该语言文案")
    parent_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="上级明细 ID（自引用同表 id；本表无层级，按附表统一口径保留）"
    )
