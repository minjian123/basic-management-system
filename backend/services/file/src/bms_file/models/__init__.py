from bms_core.core.concurrent import ConcurrentStableList

"""文件服务 models 层：SQLAlchemy ORM 模型。

继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。
模型落域子包 `domains/file/models/file.py`（03_01）；本清单是迁移链解析模型的唯一登记点。
"""

MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(("bms_file.domains.file.models.file",))
"""本服务模型模块清单（迁移链按服务解析模型用）。"""
