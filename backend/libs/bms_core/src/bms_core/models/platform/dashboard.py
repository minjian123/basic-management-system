"""首页工作台域模型：卡片注册表 / 卡片名多语言附表 / 模板（11_01）。

- 归属：业务域 `dashboard`（承载服务 `platform`，库类别 `tenant`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_dashboard_card.md` 等三份，
  节点 [36-首页工作台](../../../../../bms文档/设计/数据库设计/36_数据库设计_首页工作台.md)）；
- **定位键 `code`**：布局与模板只引用卡片 `code`（业务键），不存雪花 ID——卡片删后重建不影响既有模板；
- **`role_id = 0`** 表示平台层级：`(scope, role_id, deleted_at)` 复合唯一在 `NULL` 上不生效
  （NULL 互不相等，四库同语义），用 `0` 占位保证「平台仅一份、一角色至多一份」成立；
- **不设 `is_default` 列**：平台默认模板由 `scope = platform` 的唯一活行判定（2026-11-18 决策 9）；
- 内置卡定义由平台种子登记、租户只可改 `status`，语义由服务层强制（表结构不区分）。
"""

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import BaseModel, SnowflakeId

CARD_TYPE_BUILTIN = "builtin"
"""卡片类型：内置功能卡（平台种子登记，租户只可停用）。"""

CARD_TYPE_DATASET = "dataset"
"""卡片类型：数据集图表卡（租户自建，引用报表中心数据集）。"""

CARD_TYPES: ConcurrentStableList[str] = ConcurrentStableList((CARD_TYPE_BUILTIN, CARD_TYPE_DATASET))
"""卡片类型取值（双轨制）。"""

SCOPE_PLATFORM = "platform"
"""模板层级：平台默认（仅一份）。"""

SCOPE_ROLE = "role"
"""模板层级：角色模板（一角色至多一份）。"""

TEMPLATE_SCOPES: ConcurrentStableList[str] = ConcurrentStableList((SCOPE_PLATFORM, SCOPE_ROLE))
"""模板层级取值。"""

NO_ROLE_ID = 0
"""非角色层级的占位角色 ID（规避唯一约束在 NULL 上的跨库语义差异）。"""

STATUS_ENABLED = "enabled"
"""启用状态。"""

STATUS_DISABLED = "disabled"
"""停用状态（卡片停用即从所有布局剔除；模板停用即该级不参与回退）。"""

STATUSES: ConcurrentStableList[str] = ConcurrentStableList((STATUS_ENABLED, STATUS_DISABLED))
"""状态取值。"""


class SysDashboardCard(BaseModel):
    """工作台卡片注册表（`sys_dashboard_card`）：内置功能卡与租户数据集图表卡统一登记。"""

    __tablename__ = "sys_dashboard_card"
    __table_args__ = (UniqueConstraint("code", "deleted_at", name="uq_sys_dashboard_card_code_deleted_at"),)

    code: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="卡片标识（业务键，^[a-z][a-z0-9_]{1,63}$；布局与模板只引用本列）",
    )
    name: Mapped[str] = mapped_column(
        String(128), comment="卡片名默认文案（派生快照：系统默认语言 → 首个有值语言；多语言见附表）"
    )
    card_type: Mapped[str] = mapped_column(
        String(16), default=CARD_TYPE_BUILTIN, comment="卡片类型（builtin / dataset）"
    )
    render_key: Mapped[str] = mapped_column(
        String(64), default="", comment="前端渲染器标识（builtin 卡必填；dataset 卡为空）"
    )
    dataset_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="数据集标识（逻辑外键 → 报表中心数据集，跨服务；仅 dataset 卡）"
    )
    chart_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="图表类型（CHART_TYPES 白名单；仅 dataset 卡）"
    )
    chart_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="可选图表样式覆盖 JSON 文本（图例 / 坐标轴 / 色板序号等）"
    )
    data_endpoint: Mapped[str] = mapped_column(
        String(256), default="", comment="卡片数据接口地址（空表示前端按渲染器自身逻辑取数或占位）"
    )
    default_width: Mapped[int] = mapped_column(Integer, default=4, comment="默认网格宽（列，2~12）")
    default_height: Mapped[int] = mapped_column(Integer, default=2, comment="默认网格高（行，2~6）")
    mobile_supported: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否参与移动端单列布局")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="可选卡片清单与最小布局排序（升序）")
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_ENABLED, comment="状态（enabled / disabled；停用后解析期从所有布局剔除）"
    )


class SysDashboardCardI18n(BaseModel):
    """卡片名多语言附表（`sys_dashboard_card_i18n`）：`(card_id, locale, deleted_at)` 唯一。"""

    __tablename__ = "sys_dashboard_card_i18n"
    __table_args__ = (
        UniqueConstraint(
            "card_id",
            "locale",
            "deleted_at",
            name="uq_sys_dashboard_card_i18n_card_locale_deleted_at",
        ),
    )

    card_id: Mapped[int] = mapped_column(SnowflakeId, comment="卡片 ID（逻辑外键 → sys_dashboard_card.id，同库）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（IETF 标准形态，如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="卡片名的该语言文案")


class SysDashboardTemplate(BaseModel):
    """工作台模板（`sys_dashboard_template`）：平台默认模板与角色模板，同层各一份。"""

    __tablename__ = "sys_dashboard_template"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "role_id",
            "deleted_at",
            name="uq_sys_dashboard_template_scope_role_deleted_at",
        ),
    )

    scope: Mapped[str] = mapped_column(String(16), comment="层级（platform / role）")
    role_id: Mapped[int] = mapped_column(
        SnowflakeId, default=NO_ROLE_ID, comment="角色 ID（逻辑外键 → sys_role.id，同库；0 = 平台层级）"
    )
    name: Mapped[str] = mapped_column(String(128), comment="模板名称（管理面展示）")
    layout_config: Mapped[str] = mapped_column(
        Text, comment="布局配置 JSON 文本（{cards:[{code,x,y,w,h,visible}]}）；应用层归一与校验"
    )
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_ENABLED, comment="状态（enabled / disabled；停用即该级不参与回退）"
    )
