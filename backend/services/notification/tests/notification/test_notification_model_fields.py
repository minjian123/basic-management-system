"""站内信表模型声明用例（`bms_notification/models/notification.py`）。

本阶段只声明结构、不建表：断言表名与关键列齐备，确保模型元数据与《数据库设计》口径一致。
"""

from __future__ import annotations

from bms_notification.models.notification import SysNotification


def test_sys_notification_model_declaration() -> None:
    """表名与关键列（收件人 / 标题 / 正文 / 类型 / 业务标识 / 已读）齐备。"""
    assert SysNotification.__tablename__ == "sys_notification"
    columns = set(SysNotification.__table__.columns.keys())
    assert {"user_id", "title", "content", "type", "biz_type", "biz_id", "is_read"} <= columns
    assert SysNotification.__table__.columns["is_read"].default.arg is False
