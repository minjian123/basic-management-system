"""组织主数据服务 models 层：SQLAlchemy ORM 模型。

继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。

本服务当前**无自有模型表**：用户（系统账号，`sys_user` / `sys_account_lock`）随需求 07-10
归口 platform 服务租户库（原阶段六历史落点已迁出）；组织主数据表（`org_dept` / `org_post` /
`org_user_post`）归 mdm 产品仓库维护。故 `MODEL_MODULES` 声明空元组（链元数据子集仅含基础设施表）。
"""

MODEL_MODULES: tuple[str, ...] = ()
"""本服务模型模块清单（迁移链按服务解析模型用；无自有模型声明空元组）。"""
