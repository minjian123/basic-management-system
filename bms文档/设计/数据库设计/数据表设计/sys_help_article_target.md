# sys_help_article_target（帮助文章锚点关联）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_article_target

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（文章 × 页面内帮助锚点，一对多） |
| 上游依据 | [需求 09-2](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-2)、《[架构设计 · 帮助中心](../../架构设计/28_架构设计_子系统_帮助中心.md)》§4.2、《[帮助包规范](../../../规范/帮助包规范.md)》§5 / §6 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpArticleTarget`（继承 `BaseModel`） |
| 状态 | 已设计（随 08_03 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_article](sys_help_article.md)（主表）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 关联行标识 |
| `article_id` | DECIMAL(38,0) | 否 | — | 文章 ID（逻辑外键 → `sys_help_article.id`） |
| `target_type` | VARCHAR(16) | 否 | — | 目标类型：`global` / `module` / `form` / `field` / `action` |
| `target_key` | VARCHAR(255) | 否 | 默认空串 | 目标锚点：`global` 为空串，其余为五段式 `help_key` 原值 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **一对多**：一篇文章可挂多个锚点（如同时挂表单与按钮）；解析时按候选层级对应的 `target_type` + `target_key` 精确命中。
- **`global` 约定**：`target_type=global` 时 `target_key` 为空串（不用 `NULL`，避免达梦复合唯一中的 NULL 语义差异）；其余类型的 `target_key` 必须逐字等于元数据上的 `help_key`。
- **写入口径**：包装载整体替换（旧行软删、按新集合插行）；12_01 维护入口同口径。
- **引用不创建**：本表只引用元数据锚点，不反向创建 / 修改菜单、表单、字段、按钮、动作码（《帮助包规范》§9 只读边界）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_help_article_target_article_type_key_deleted_at` | 唯一 | `(article_id, target_type, target_key, deleted_at)` | 同一文章同一目标只挂一次（软删除后释放） |
| `idx_sys_help_article_target_type_key` | 普通 | `(target_type, target_key)` | 解析按目标反查已发布文章 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`article_id` 为逻辑外键（同库）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：随主表归档；不单独建策略。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建（08_03 产品帮助包装载注册）：文章多锚点关联，支撑五级解析与「同锚点多篇」优先级 | minjian |
