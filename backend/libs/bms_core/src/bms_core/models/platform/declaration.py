"""产品声明注册表模型（07B `02_06`）：跨产品协同八类声明的**权威落点**。

六张表（一表一类），与既有 `sys_module`（服务行）/ `sys_product`（产品档案）共同构成注册表：

| 表 | 承载 |
| --- | --- |
| `sys_product_route` | 产品级路由（前端命名空间 / 网关路由） |
| `sys_data_source` | 数据源声明（字典 / 参考数据） |
| `sys_collaboration` | 能力声明（第五类记录） |
| `sys_collaboration_usage` | 消费方使用声明（第八类记录） |
| `sys_seed` | 数据种子声明（第六类记录） |
| `sys_errcode` | 错误码声明（第七类记录） |
| `sys_domain` | 业务域声明（第九类记录；07B `04_02` 重开） |

口径：

- 归属：六表归 `platform` 服务、库类别 `platform`（链 `platform:platform`，库 `bms_platform`），
  由 `bms_core/services/table_registry.py::TABLE_OWNERSHIP` 单一来源登记；
- 写入口**唯一**：产品注册通道（`PUT /api/v1/internal/declarations`）与平台自身清单注册；
- 退役不删行：本次全量注册未出现的记录置 `status = retired`，历史保留；
- `content_hash` 用于「内容未变不写」与变更检测；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_*.md`）。
"""

from sqlalchemy import CHAR, BigInteger, Boolean, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = [
    "SysCollaboration",
    "SysCollaborationUsage",
    "SysDataSource",
    "SysDomain",
    "SysErrcode",
    "SysProductRoute",
    "SysSeed",
]


class SysProductRoute(BaseModel):
    """产品级路由声明（`sys_product_route`）：产品键 → 域段 → 承载服务键。"""

    __tablename__ = "sys_product_route"
    __table_args__ = (
        UniqueConstraint("product_key", "domain", "deleted_at", name="uq_sys_product_route_product_domain_deleted_at"),
        UniqueConstraint("domain", "deleted_at", name="uq_sys_product_route_domain_deleted_at"),
        UniqueConstraint("service_key", "deleted_at", name="uq_sys_product_route_service_deleted_at"),
    )

    product_key: Mapped[str] = mapped_column(String(32), comment="产品键（声明方）")
    domain: Mapped[str] = mapped_column(String(64), comment="域段（前端命名空间段，如 mdm）")
    service_key: Mapped[str] = mapped_column(String(64), comment="承载服务键")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="说明")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/retired）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysDataSource(BaseModel):
    """数据源声明（`sys_data_source`）：字典 / 参考数据的取数登记。"""

    __tablename__ = "sys_data_source"
    __table_args__ = (UniqueConstraint("data_source_key", "deleted_at", name="uq_sys_data_source_key_deleted_at"),)

    data_source_key: Mapped[str] = mapped_column(String(64), comment="数据源键（前端与后端共用标识）")
    product_key: Mapped[str] = mapped_column(String(32), comment="声明方产品键")
    name: Mapped[str] = mapped_column(String(64), comment="显示名")
    kind: Mapped[str] = mapped_column(String(16), default="dict", comment="数据源类型（dict/tree/remote）")
    data_source: Mapped[str] = mapped_column(String(128), comment="取数实现标识（如 mdm.mdm.dept）")
    origin: Mapped[str] = mapped_column(String(16), default="product", comment="来源（platform/product）")
    path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="提供方访问面路径")
    allowlist: Mapped[str | None] = mapped_column(Text, nullable=True, comment="允许下发字段（JSON 数组）")
    cascade: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否级联取数")
    strategies: Mapped[str | None] = mapped_column(Text, nullable=True, comment="取数策略（JSON 数组）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/retired）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysCollaboration(BaseModel):
    """能力声明（`sys_collaboration`）：第五类记录，能力视图与取址的唯一来源。"""

    __tablename__ = "sys_collaboration"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_sys_collaboration_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(128), comment="能力名（{产品}.{业务域}.{能力}，全局唯一）")
    product_key: Mapped[str] = mapped_column(String(32), comment="声明方产品键（提供方）")
    domain: Mapped[str] = mapped_column(String(64), comment="提供方业务域（须在域布局登记）")
    kind: Mapped[str] = mapped_column(String(16), comment="访问面类别（read/write/txn-branch/dataset/codes）")
    contract_version: Mapped[str] = mapped_column(String(16), comment="随提供方服务契约版本")
    path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="访问面路径模板（codes 为空）")
    branch_id: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="事务分支标识（txn-branch）")
    branch_op: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="事务分支动作名（txn-branch）")
    data_source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="关联数据源键（dataset）")
    permission_codes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="业务码/权限码集合（JSON 数组）")
    frontend_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="前端命名空间域段")
    default_consumers: Mapped[str | None] = mapped_column(Text, nullable=True, comment="默认分配消费方（JSON 数组）")
    replacement: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="替代能力名（deprecated 必填）")
    status: Mapped[str] = mapped_column(
        String(16), default="enabled", comment="状态（enabled/disabled/deprecated/retired）"
    )
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysDomain(BaseModel):
    """业务域声明（`sys_domain`）：第九类记录，域布局的权威落点（07B `04_02` 重开）。

    域布局从「独立 `deploy/boundaries/domain_layout.json` 文件」改为「产品自持声明」后，
    域信息随注册通道到达平台；`domain_layout.json` 降为**本仓清单渲染的生成物**。
    """

    __tablename__ = "sys_domain"
    __table_args__ = (
        UniqueConstraint("product_key", "domain_key", "deleted_at", name="uq_sys_domain_owner_key_deleted_at"),
        UniqueConstraint("domain_key", "deleted_at", name="uq_sys_domain_key_deleted_at"),
    )

    product_key: Mapped[str] = mapped_column(String(32), comment="声明方产品键")
    domain_key: Mapped[str] = mapped_column(String(64), comment="业务域标识（全局唯一）")
    service_key: Mapped[str] = mapped_column(String(64), comment="承载服务键（恒不变）")
    status: Mapped[str] = mapped_column(
        String(16), default="placement", comment="布局状态（placement/legacy/planned/retired）"
    )
    paths: Mapped[str | None] = mapped_column(Text, nullable=True, comment="域代码路径（JSON 数组，相对仓库根）")
    public_api: Mapped[str | None] = mapped_column(Text, nullable=True, comment="域公共出口模块名（JSON 数组，≤1）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysCollaborationUsage(BaseModel):
    """消费方使用声明（`sys_collaboration_usage`）：第八类记录，声明方即消费方。"""

    __tablename__ = "sys_collaboration_usage"
    __table_args__ = (
        UniqueConstraint(
            "product_key",
            "capability_name",
            "deleted_at",
            name="uq_sys_collaboration_usage_owner_name_deleted_at",
        ),
    )

    product_key: Mapped[str] = mapped_column(String(32), comment="声明方（＝消费方）产品键")
    capability_name: Mapped[str] = mapped_column(String(128), comment="被消费能力名")
    degrade: Mapped[str] = mapped_column(String(16), default="none", comment="降级模式（none/empty/stale）")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="降级理由")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/retired）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysSeed(BaseModel):
    """数据种子声明（`sys_seed`）：第六类记录，执行归平台统一编排。"""

    __tablename__ = "sys_seed"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_sys_seed_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(64), comment="种子名（与平台自身种子共用命名空间）")
    product_key: Mapped[str] = mapped_column(String(32), comment="声明方产品键")
    service: Mapped[str] = mapped_column(String(64), comment="执行服务键（XA 分支参与方）")
    db_key: Mapped[str] = mapped_column(String(64), comment="目标库键（支持 {tenant} 占位）")
    module: Mapped[str] = mapped_column(String(255), comment="入口模块点分路径")
    entry: Mapped[str] = mapped_column(String(64), comment="入口函数名")
    op: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="分支操作名（缺省同 name）")
    after: Mapped[str | None] = mapped_column(Text, nullable=True, comment="依赖种子名（JSON 数组）")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="说明")
    tables: Mapped[str | None] = mapped_column(Text, nullable=True, comment="目标表 → 自然键（JSON 对象）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/retired）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysErrcode(BaseModel):
    """错误码声明（`sys_errcode`）：第七类记录，渲染与手册导出的来源。"""

    __tablename__ = "sys_errcode"
    __table_args__ = (UniqueConstraint("code", "deleted_at", name="uq_sys_errcode_code_deleted_at"),)

    code: Mapped[int] = mapped_column(Integer, comment="错误码（6 位 = 2 位段 + 4 位序号）")
    product_key: Mapped[str] = mapped_column(String(32), comment="声明方产品键")
    segment: Mapped[str] = mapped_column(String(2), comment="段位（取自服务行 errcode_segment）")
    domain: Mapped[str] = mapped_column(String(64), comment="所属业务域")
    http_status: Mapped[int] = mapped_column(SmallInteger, comment="渲染用 HTTP 状态码")
    message_key: Mapped[str] = mapped_column(String(128), comment="文案键（<product>.error.<snake>）")
    severity: Mapped[str] = mapped_column(String(16), comment="严重级（info/warning/error）")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="中文描述（回退与审计读用）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/retired）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )
