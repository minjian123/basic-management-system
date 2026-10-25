"""自定义图标模型：`sys_icon` / `sys_icon_i18n`（`permission_meta` 业务域）。

- 归属：业务域 `permission_meta`（承载服务 `platform`，库类别租户库）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 图标键（`code`）为业务标识，前端 icon key 由基座派生为 `custom:{图标键}`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_icon.md`）。
"""

from sqlalchemy import BigInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysIcon(BaseModel):
    """租户自定义图标（`sys_icon`）：图标键唯一、租户各自维护（03_03 真实落库）。

    图标为**租户库**表（平台官方与业务自绘图标随代码发布、不落表）；图标键（`code`）为业务标识，
    前端 icon key 由基座派生为 `custom:{图标键}`。`svg` 存内联 SVG 内容，类型 / 大小与危险内容
    基础拒绝由图标服务校验，深度清洗归文件管理阶段。表结构以《数据库设计》数据表文件为唯一事实源。
    """

    __tablename__ = "sys_icon"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_icon_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_icon_form_key_deleted_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="icon", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="图标键（kebab-case，租户内唯一；icon key = custom:{code}）")
    name: Mapped[str] = mapped_column(String(128), comment="图标名称（默认文案）")
    category: Mapped[str] = mapped_column(String(64), index=True, comment="图标分组（分类）")
    tags: Mapped[str] = mapped_column(String(256), default="", comment="标签（逗号分隔，搜索用；跨方言安全）")
    svg: Mapped[str] = mapped_column(Text, comment="SVG 内容（上传前清洗归文件管理阶段）")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="状态（active/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysIconI18n(BaseModel):
    """自定义图标名称多语言附表（`sys_icon_i18n`）：`(icon_id, locale, deleted_at)` 唯一。"""

    __tablename__ = "sys_icon_i18n"
    __table_args__ = (
        UniqueConstraint("icon_id", "locale", "deleted_at", name="uq_sys_icon_i18n_icon_locale_deleted_at"),
    )

    icon_id: Mapped[int] = mapped_column(BigInteger, comment="图标 ID（逻辑外键 → sys_icon.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="图标名称文案")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )
