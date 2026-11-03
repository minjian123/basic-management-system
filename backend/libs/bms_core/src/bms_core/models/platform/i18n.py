"""国际化（`sys_i18n_locale` / `sys_i18n_message`）ORM 模型（platform 服务租户库）。

- 语言清单：`code` 唯一（与 `deleted_at` 复合）、`rtl` 驱动前端布局方向、`is_default` 为默认语言标记
  （全清单恰一条、不可停用 / 不可删除，由应用层保证）。
- 固定文案语言包：`(msg_key, locale)` 联合唯一，`value` 去空白后为空即缺失（读取侧回退默认语言）。
- 平台默认经幂等种子写入各租户库（`bms_core.i18n.seed`），租户覆盖改同一行并置 `is_overridden=true`。
- 字段 / 索引口径见《数据库设计 · 数据表设计 · sys_i18n_locale》《sys_i18n_message》表文件（字段唯一事实源）。
"""

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId

__all__ = ["SysI18nLocale", "SysI18nMessage"]


class SysI18nLocale(BaseModel):
    """语言清单（`sys_i18n_locale`）。"""

    __tablename__ = "sys_i18n_locale"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_i18n_locale_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_i18n_locale_form_key_deleted_at"),
        Index("idx_sys_i18n_locale_sort", "sort"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="i18n_locale", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(16), comment="语言标识（IETF 标准形态，如 zh-CN / en-US / ar-SA）")
    name: Mapped[str] = mapped_column(String(64), default="", comment="语言名称（本地名，如 简体中文 / English）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    rtl: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否从右到左（驱动前端布局方向）")
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="默认语言标记（全清单恰一条；派生默认文案与缺省回退目标）"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序（升序）")
    is_overridden: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否被租户改过（false=平台默认行；种子刷新与保护判据）"
    )
    parent_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysI18nMessage(BaseModel):
    """固定文案语言包（`sys_i18n_message`）。"""

    __tablename__ = "sys_i18n_message"
    __table_args__ = (
        UniqueConstraint("code", "locale", "deleted_at", name="uq_sys_i18n_message_code_locale_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_i18n_message_form_key_deleted_at"),
        Index("idx_sys_i18n_message_locale", "locale"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="i18n_message", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    msg_key: Mapped[str] = mapped_column(
        "code", String(128), comment="文案 key（模块.页面.字段，如 common.confirm；DB 列名为 code）"
    )
    name: Mapped[str] = mapped_column(String(128), default="", comment="展示名（维护列表用，缺省取 key）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（与 sys_i18n_locale.code 同形态）")
    value: Mapped[str] = mapped_column(Text, default="", comment="该语言文案（去空白为空即缺失）")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注（维护页说明 / 插值提示）")
    is_overridden: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否被租户改过（false=平台默认行；种子刷新与删除保护判据）"
    )
    parent_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="上级明细 ID（自引用同表 id；本表无层级）"
    )
