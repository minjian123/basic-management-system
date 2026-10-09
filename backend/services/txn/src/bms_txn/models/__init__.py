"""跨服务事务管理器服务 models 层：SQLAlchemy ORM 模型（跨服务事务账本三表）。

职责：数据结构与映射定义。
禁止：写业务逻辑；查询与业务规则归 repositories / services。
继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。
"""

MODEL_MODULES: tuple[str, ...] = ("bms_txn.models.ledger",)
"""本服务模型模块清单（迁移链按服务解析模型用）。"""
