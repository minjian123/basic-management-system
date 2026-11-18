"""i18n 附表登记台账（`{主表}_i18n` 的唯一代码侧事实源）。

任务 05_02 的「附表逐项登记、不全表附挂」落点：机器可读的台账在此，人类可读视图是
《数据库设计 · 国际化管理》「i18n 附表登记」节；护栏脚本 `check_i18n_attachments.py`
断言**模型层每张 `*_i18n` 表都在完整台账内**，且「已落库」行的文案列与模型一致。

口径：

- 只有「面向用户的文本列」挂附表；技术列（`code` / `path` / `key`）不挂。
- `status="landed"`：表已落库，文案列即当前模型列名；`status="pending"`：主表尚未建立，
  文案列是与该任务约定的**预期列**，建表时回填并改状态。
- **归属 platform 的表**登记在 `I18N_ATTACHMENTS`；**服务自有附表**由服务在装载期经
  `register_i18n_attachments()` 注册（基座不引用他人服务库表名），完整视图取 `all_attachments()`。
- 字典 label **不在台账**：字典无独立 i18n 附表（02_09 已拆除），多语言由通用数据源
  `DictI18nSpec` 按需挂载（见 `bms_core/dict/table.py`）。
"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.roots import BaseValueObject

__all__ = [
    "ATTACHMENT_LANDED",
    "ATTACHMENT_PENDING",
    "I18N_ATTACHMENTS",
    "I18nAttachment",
    "all_attachments",
    "landed_attachments",
    "pending_attachments",
    "register_i18n_attachments",
    "reset_i18n_attachments",
]

ATTACHMENT_LANDED = "landed"
"""附表已落库（模型存在，文案列以模型为准）。"""

ATTACHMENT_PENDING = "pending"
"""附表待落地（主表尚未建立，文案列为约定）。"""


@dataclass(frozen=True)
class I18nAttachment(BaseValueObject):
    """一条 i18n 附表登记项。

    Attributes:
        table: 附表名（`{主表}_i18n`）。
        owner_table: 主表名。
        key_column: 指向主表 `id` 的列名。
        text_columns: 文案列名（多列如邮件模板 `subject` / `content`）。
        status: `landed` / `pending`。
        owner_task: 归属任务（待落地时为归口任务）。
    """

    table: str
    owner_table: str
    key_column: str
    text_columns: ConcurrentStableList[str] = field(hash=False)
    status: str = ATTACHMENT_LANDED
    owner_task: str = ""


I18N_ATTACHMENTS: ConcurrentStableDict[str, I18nAttachment] = ConcurrentStableDict(
    {
        item.table: item
        for item in (
            I18nAttachment(
                table="sys_menu_i18n",
                owner_table="sys_menu",
                key_column="menu_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="08 菜单管理",
            ),
            I18nAttachment(
                table="sys_field_i18n",
                owner_table="sys_field",
                key_column="field_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="08 菜单管理",
            ),
            I18nAttachment(
                table="sys_business_i18n",
                owner_table="sys_business",
                key_column="business_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="08 菜单管理",
            ),
            I18nAttachment(
                table="sys_action_i18n",
                owner_table="sys_action",
                key_column="action_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="08 菜单管理",
            ),
            I18nAttachment(
                table="sys_module_i18n",
                owner_table="sys_module",
                key_column="module_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="03 模块注册",
            ),
            I18nAttachment(
                table="sys_icon_i18n",
                owner_table="sys_icon",
                key_column="icon_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="03_03 自定义图标",
            ),
            I18nAttachment(
                table="sys_help_article_i18n",
                owner_table="sys_help_article",
                key_column="article_id",
                text_columns=ConcurrentStableList(["title", "content"]),
                owner_task="08_03 产品帮助包装载注册",
            ),
            I18nAttachment(
                table="sys_dashboard_card_i18n",
                owner_table="sys_dashboard_card",
                key_column="card_id",
                text_columns=ConcurrentStableList(["name"]),
                status=ATTACHMENT_LANDED,
                owner_task="11_01 首页工作台",
            ),
            I18nAttachment(
                table="sys_field_ext_i18n",
                owner_table="sys_field_ext",
                key_column="field_id",
                text_columns=ConcurrentStableList(["name"]),
                owner_task="10_01 表单定制",
            ),
        )
    }
)
"""平台侧 i18n 附表登记台账（表名 → 登记项）。

**服务自有附表**（如 `sys_notice_i18n`）由服务在装载期经 `register_i18n_attachments()` 追加，
本常量只登记归属 platform 的表——基座不得直接引用其他服务库表名。
"""

_REGISTERED: ConcurrentStableDict[str, I18nAttachment] = ConcurrentStableDict()
"""服务装载期注册的附表（表名 → 登记项）。"""


def register_i18n_attachments(items: ConcurrentStableList[I18nAttachment]) -> None:
    """登记服务自有 i18n 附表（装载期调用；同表重复登记无操作）。

    Args:
        items: 附表登记项（插入序）。
    """
    for item in items:
        _REGISTERED.set(item.table, item)


def reset_i18n_attachments() -> None:
    """清空服务注册表（测试隔离用；不影响平台常量）。"""
    _REGISTERED.clear()


def all_attachments() -> ConcurrentStableDict[str, I18nAttachment]:
    """取完整台账（平台常量 + 服务注册）。

    Returns:
        ConcurrentStableDict[str, I18nAttachment]: 表名 → 登记项（插入序；服务项追加在后）。
    """
    merged: ConcurrentStableDict[str, I18nAttachment] = ConcurrentStableDict(I18N_ATTACHMENTS)
    for table, item in _REGISTERED.items():
        merged.set(table, item)
    return merged


def landed_attachments() -> ConcurrentStableList[I18nAttachment]:
    """取已落库的登记项。

    Returns:
        ConcurrentStableList[I18nAttachment]: 已落库条目。
    """
    return ConcurrentStableList(item for item in all_attachments().values() if item.status == ATTACHMENT_LANDED)


def pending_attachments() -> ConcurrentStableList[I18nAttachment]:
    """取待落地的登记项。

    Returns:
        ConcurrentStableList[I18nAttachment]: 待落地条目。
    """
    return ConcurrentStableList(item for item in all_attachments().values() if item.status == ATTACHMENT_PENDING)
