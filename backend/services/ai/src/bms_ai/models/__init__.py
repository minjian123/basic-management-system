"""AI服务 models 层：SQLAlchemy ORM 模型。

继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。
"""

MODEL_MODULES: tuple[str, ...] = ()
"""本服务模型模块清单（迁移链按服务解析模型用；本服务暂未定义模型）。"""
