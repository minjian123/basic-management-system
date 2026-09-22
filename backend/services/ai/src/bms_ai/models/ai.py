"""AI 域表模型骨架：交互审计（`ai_chat_log`，按月分片；真实建表以《数据库设计》为准）。

AI 交互全量落 `ai_chat_log`；会话列表与历史以本表审计数据为**派生视图**（按用户 / `session_id` 聚合），
不另建独立会话事实源。逻辑表名 `ai_chat_log`、物理表名带 `yyyyMM`（按月分片，新分片由 Celery 预创建），
本任务只声明结构、不建表、不迁移。表结构以《数据库设计》数据表文件为唯一事实源。
"""

from sqlalchemy import BigInteger, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class AiChatLog(BaseModel):
    """AI 交互审计（`ai_chat_log`，按月分片）。"""

    __tablename__ = "ai_chat_log"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="用户 ID（逻辑外键 → sys_user.id）")
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="租户 ID")
    session_id: Mapped[str] = mapped_column(String(64), index=True, comment="会话标识（派生视图分组键）")
    module: Mapped[str] = mapped_column(String(32), comment="模式（ask / report / approval / doc_qa）")
    role: Mapped[str] = mapped_column(String(16), comment="消息角色（user / assistant / system）")
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True, comment="提示词（落库前经掩码）")
    response: Mapped[str | None] = mapped_column(Text, nullable=True, comment="响应文本")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="实际使用的模型")
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Provider 标识")
    tokens: Mapped[int] = mapped_column(Integer, default=0, comment="token 消耗")
    cost: Mapped[float] = mapped_column(Numeric(20, 4), default=0, comment="成本（金额）")
    status: Mapped[str] = mapped_column(
        String(16), default="done", comment="状态（streaming / done / error / stopped）"
    )
