"""帮助中心内容面模型：分类 / 文章 / 多语言 / 锚点 / 包登记（08_03）。

- 归属：业务域 `help`（承载服务 `platform`，库类别 `tenant`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`17_数据库设计_帮助中心.md` 与五张表文件）；
- 来源与优先级 / 包状态 / 目标类型的静态值域见 `bms_core.help.values`；
- `sys_help_feedback` 归 12_01 帮助内容维护，本模块不声明。

挂接链：分类 1:N 文章；文章 1:N 多语言附表与锚点关联；包 1:N 来源文章。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_DRAFT,
    GENERATED_BY_MANUAL,
    PACKAGE_SCHEMA_VERSION,
    PACKAGE_STATUS_LOADED,
)
from bms_core.models.base import BaseModel, SnowflakeId

__all__ = [
    "SysHelpArticle",
    "SysHelpArticleI18n",
    "SysHelpArticleTarget",
    "SysHelpCategory",
    "SysHelpPackage",
]


class SysHelpCategory(BaseModel):
    """帮助分类树（`sys_help_category`）：`parent_id = 0` 表示根。"""

    __tablename__ = "sys_help_category"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", "deleted_at", name="uq_sys_help_category_parent_name_deleted_at"),
        Index("idx_sys_help_category_parent_sort", "parent_id", "sort"),
    )

    parent_id: Mapped[int] = mapped_column(SnowflakeId, default=0, comment="上级分类 ID（逻辑外键 → 本表 id；0 = 根）")
    name: Mapped[str] = mapped_column(String(128), comment="分类名（默认语言；分类不设多语言附表）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序（升序）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysHelpArticle(BaseModel):
    """帮助文章主体（`sys_help_article`）：标题 / 正文为默认语言派生快照。"""

    __tablename__ = "sys_help_article"
    __table_args__ = (
        Index("idx_sys_help_article_category_status", "category_id", "status"),
        Index("idx_sys_help_article_status_top_publish", "status", "is_top", "publish_at"),
        Index("idx_sys_help_article_source_source_key", "source", "source_key"),
    )

    category_id: Mapped[int] = mapped_column(SnowflakeId, comment="所属分类 ID（逻辑外键 → sys_help_category.id）")
    title: Mapped[str] = mapped_column(String(256), comment="标题（系统默认语言派生快照）")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文 HTML（已净化；系统默认语言派生快照）")
    status: Mapped[str] = mapped_column(
        String(16), default=ARTICLE_STATUS_DRAFT, comment="状态（draft/published/offline）"
    )
    is_top: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否置顶")
    source: Mapped[str] = mapped_column(
        String(16), default=ARTICLE_SOURCE_TENANT, comment="来源（builtin/product/tenant）"
    )
    package_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="来源包版本（逻辑外键 → sys_help_package.id；租户自建为 NULL）"
    )
    source_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="包内稳定键（升级比对主键；租户自建为 NULL）"
    )
    local_override: Mapped[bool] = mapped_column(Boolean, default=False, comment="租户本地编辑标记（升级不覆盖内容）")
    generated_by: Mapped[str] = mapped_column(String(16), default=GENERATED_BY_MANUAL, comment="生成方式（manual/ai）")
    ai_model: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="AI 生成模型（generated_by=ai 时填写）"
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="人工审核人标识（generated_by=ai 时必填）"
    )
    author_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="人工作者（逻辑外键 → sys_user.id；包装载为空）"
    )
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="发布时间（UTC；首次发布时写入）"
    )
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, comment="阅读计数（12_01 维护）")
    helpful_count: Mapped[int] = mapped_column(BigInteger, default=0, comment="有帮助计数（12_01 维护）")
    unhelpful_count: Mapped[int] = mapped_column(BigInteger, default=0, comment="无帮助计数（12_01 维护）")


class SysHelpArticleI18n(BaseModel):
    """文章标题 / 正文多语言附表（`sys_help_article_i18n`）。"""

    __tablename__ = "sys_help_article_i18n"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "locale",
            "deleted_at",
            name="uq_sys_help_article_i18n_article_locale_deleted_at",
        ),
    )

    article_id: Mapped[int] = mapped_column(SnowflakeId, comment="文章 ID（逻辑外键 → sys_help_article.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（IETF 标准形态，如 zh-CN / en-US）")
    title: Mapped[str] = mapped_column(String(256), comment="该语言标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="该语言正文 HTML（已净化）")


class SysHelpArticleTarget(BaseModel):
    """文章 × 页面内帮助锚点（`sys_help_article_target`）：一篇可挂多个目标。"""

    __tablename__ = "sys_help_article_target"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "target_type",
            "target_key",
            "deleted_at",
            name="uq_sys_help_article_target_article_type_key_deleted_at",
        ),
        Index("idx_sys_help_article_target_type_key", "target_type", "target_key"),
    )

    article_id: Mapped[int] = mapped_column(SnowflakeId, comment="文章 ID（逻辑外键 → sys_help_article.id）")
    target_type: Mapped[str] = mapped_column(String(16), comment="目标类型（global/module/form/field/action）")
    target_key: Mapped[str] = mapped_column(
        String(255), default="", comment="目标锚点（global 为空串；其余为五段式 help_key 原值）"
    )


class SysHelpPackage(BaseModel):
    """产品帮助包装载登记（`sys_help_package`）：一行一个「产品 × 版本」。"""

    __tablename__ = "sys_help_package"
    __table_args__ = (
        UniqueConstraint(
            "product_key",
            "package_version",
            "deleted_at",
            name="uq_sys_help_package_product_version_deleted_at",
        ),
        Index("idx_sys_help_package_product_status", "product_key", "status"),
    )

    product_key: Mapped[str] = mapped_column(String(64), comment="产品键（platform / 各产品仓产品键）")
    package_version: Mapped[str] = mapped_column(String(32), comment="语义化版本（X.Y.Z）")
    schema_version: Mapped[int] = mapped_column(Integer, default=PACKAGE_SCHEMA_VERSION, comment="包格式版本")
    checksum: Mapped[str] = mapped_column(String(80), comment="装载时校验通过的 sha256:<64 位十六进制>")
    article_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="该版本清单文章总数（含 offline 与宽松模式跳过的篇）"
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="清单 generated_at（UTC；仅登记）"
    )
    loaded_at: Mapped[datetime] = mapped_column(DateTime, comment="本次装载时间（UTC）")
    status: Mapped[str] = mapped_column(
        String(16), default=PACKAGE_STATUS_LOADED, comment="状态（loaded/outdated/unloaded）"
    )
