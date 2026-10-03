# sys_user_extension（用户扩展信息）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user_extension

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`，与 `sys_config` / `sys_user_preference` 同库） |
| 覆盖模块 | 05-前端插件化（域 06 具名插槽：样例插件的后端契约资源；归属 `sys` 模块 —— 平台共享前缀 `sys_`，与平台服务同库同链） |
| 上游依据 | [需求 05-10](../../../项目/05_前端插件化/需求/06_需求_具名插槽与插件挂接.md#r05-10)、《[架构设计 · 扩展点与插件化](../../架构设计/10_架构设计_子系统_扩展点与插件化.md)》§9.2（数据归属方提供插件）、《[详细设计 · 具名插槽基座功能与前后端配套插件](../../../项目/05_前端插件化/任务/06_具名插槽与插件挂接/06_具名插槽与插件挂接_01_具名插槽基座功能与前后端配套插件/设计/01_详细设计_06_具名插槽与插件挂接_01_具名插槽基座功能与前后端配套插件.md)》§3.7 |
| ORM 模型 | `bms_platform/models/system.py::SysUserExtension`（继承 `BaseModel`；随 `bms_platform/models/__init__.py::MODEL_MODULES` 导入） |
| 表归属登记 | `bms_core/services/table_registry.py::TABLE_OWNERSHIP`（`owner=platform`、`datasource=tenant`、`status=enabled`） |
| 状态 | 已落库（`platform:tenant` 链迁移 `0006_sys_user_extension`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、「已设计数据表登记」 |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `user_id` | BIGINT | 否 | — | 用户主键（逻辑外键 `sys_user.id`；跨服务只持值、不建物理外键） |
| `label` | VARCHAR(64) | 否 | — | 扩展标签（用户维度内唯一） |
| `remark` | VARCHAR(255) | 是 | — | 备注 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_extension_user_label_deleted_at` | 唯一 | `(user_id, label, deleted_at)` | 同用户同标签唯一（软删除后可重建）；冲突经服务层抛 10003 |
| `idx_sys_user_extension_user_id` | 普通 | `(user_id)` | 按用户列扩展信息（样例插件读路径） |

- 无物理外键；`user_id` 为逻辑外键指向 `sys_user.id`。
- 公共软删除索引 `idx_sys_user_extension_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在本表重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；按用户扩展条目线性增长，量级小）。
- **归档**：随用户主数据生命周期处理（用户注销 / 清理时一并清除），不单独归档。
- **迁移**：随 **`platform:tenant` 链** Alembic 迁移落地（建表 `0006_sys_user_extension`）；命令 `alembic upgrade head`（缺省链即 `platform:tenant`）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-03 | v1 | 新建表结构（platform 服务租户库；随具名插槽样例插件后端契约落 `platform:tenant` 链迁移 `0006_sys_user_extension`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
