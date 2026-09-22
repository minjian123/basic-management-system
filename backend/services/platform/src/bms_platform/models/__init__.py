"""平台服务 models 层：SQLAlchemy ORM 模型（平台业务与骨架表）。

职责：数据结构与映射定义。
禁止：写业务逻辑；查询与业务规则归 repositories / services。
继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。
"""
