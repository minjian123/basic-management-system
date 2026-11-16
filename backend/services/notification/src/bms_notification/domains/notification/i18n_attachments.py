"""通知服务自有 i18n 附表登记（`sys_notice_i18n`）。

服务自有附表**不在基座常量**（基座不得引用他人服务库表名）：本模块在装载期把附表登记项
追加到 `bms_core.i18n.attachments` 的完整台账，供护栏与文档一致性校验使用。
"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.i18n.attachments import (
    ATTACHMENT_LANDED,
    I18nAttachment,
    register_i18n_attachments,
)

__all__ = ["NOTICE_I18N_ATTACHMENTS", "register_notice_i18n_attachments"]

NOTICE_I18N_ATTACHMENTS: ConcurrentStableList[I18nAttachment] = ConcurrentStableList(
    (
        I18nAttachment(
            table="sys_notice_i18n",
            owner_table="sys_notice",
            key_column="notice_id",
            text_columns=ConcurrentStableList(("title", "content")),
            status=ATTACHMENT_LANDED,
            owner_task="07_02 公告管理",
        ),
        I18nAttachment(
            table="sys_mail_template_i18n",
            owner_table="sys_mail_template",
            key_column="template_id",
            text_columns=ConcurrentStableList(("subject", "content")),
            status=ATTACHMENT_LANDED,
            owner_task="07_03 邮件与短信通知",
        ),
    )
)
"""公告 / 邮件模板多语言附表登记项。"""


def register_notice_i18n_attachments() -> None:
    """把公告 i18n 附表登记到完整台账（装载期幂等调用）。"""
    register_i18n_attachments(NOTICE_I18N_ATTACHMENTS)


register_notice_i18n_attachments()
