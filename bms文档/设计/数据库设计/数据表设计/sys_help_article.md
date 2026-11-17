# sys_help_article（帮助文章）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_article

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（文章主体 / 状态机 / 来源与本地覆盖 / 阅读反馈计数） |
| 上游依据 | [需求 09-4](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-4)、《[概要设计 · 帮助中心](../../概要设计/17_概要设计_帮助中心.md)》§2 / §4、《[帮助包规范](../../../规范/帮助包规范.md)》§5 / §7 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpArticle`（继承 `BaseModel`） |
| 状态 | 已设计（随 08_03 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_category](sys_help_category.md)（分类）、[sys_help_article_i18n](sys_help_article_i18n.md)（多语言）、[sys_help_article_target](sys_help_article_target.md)（多锚点）、[sys_help_package](sys_help_package.md)（来源包）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 文章标识 |
| `category_id` | DECIMAL(38,0) | 否 | — | 所属分类 ID（逻辑外键 → `sys_help_category.id`） |
| `title` | VARCHAR(256) | 否 | — | 标题（系统默认语言派生快照，恒非空） |
| `content` | TEXT | 否 | 默认空串 | 正文 HTML（已净化；系统默认语言派生快照） |
| `status` | VARCHAR(16) | 否 | 默认 `draft` | 状态：`draft` 草稿 / `published` 已发布 / `offline` 已下架 |
| `is_top` | BOOLEAN | 否 | 默认 false | 是否置顶 |
| `source` | VARCHAR(16) | 否 | 默认 `tenant` | 来源：`builtin` 平台内建 / `product` 产品包 / `tenant` 租户自建 |
| `package_id` | DECIMAL(38,0) | 是 | — | 来源包版本（逻辑外键 → `sys_help_package.id`；租户自建为 NULL） |
| `source_key` | VARCHAR(128) | 是 | — | 包内稳定键（升级比对主键；租户自建为 NULL） |
| `local_override` | BOOLEAN | 否 | 默认 false | 租户本地编辑标记（升级不覆盖内容） |
| `generated_by` | VARCHAR(16) | 否 | 默认 `manual` | 生成方式：`manual` 人工 / `ai` AI 草稿 |
| `ai_model` | VARCHAR(64) | 是 | — | AI 生成模型（`generated_by=ai` 时填写） |
| `reviewed_by` | VARCHAR(128) | 是 | — | 人工审核人标识（`generated_by=ai` 时必填） |
| `author_id` | DECIMAL(38,0) | 是 | — | 人工作者（逻辑外键 → `sys_user.id`；包装载为空） |
| `publish_at` | DATETIME | 是 | — | 发布时间（UTC；首次发布时写入） |
| `view_count` | BIGINT | 否 | 默认 0 | 阅读计数（12_01 维护） |
| `helpful_count` | BIGINT | 否 | 默认 0 | 「有帮助」计数（12_01 维护） |
| `unhelpful_count` | BIGINT | 否 | 默认 0 | 「无帮助」计数（12_01 维护） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **多语言**：标题 / 正文的逐语言文案存 [sys_help_article_i18n](sys_help_article_i18n.md)；本表两列为**系统默认语言派生快照**，由装载器或维护入口按租户默认语言写入。
- **多锚点**：文章与页面 / 模块 / 表单 / 字段 / 动作的关联落 [sys_help_article_target](sys_help_article_target.md)，**本表不存 `target_type` / `target_key`**（一篇可挂多个锚点）。
- **来源优先级**：解析按 `builtin > product > tenant`；`local_override` 只改内容、不改 `source`，本地编辑过的产品文章仍按 `product` 参与优先级。
- **包来源身份**：`source_key` 在「同一产品」内唯一（代码与装载器校验，不建 DB 唯一——租户自建为 NULL，达梦会把 NULL 视同相等）；`source_key` 一经发布不得修改。
- **状态迁移**：`draft → published`（发布）、`published → offline`（下架 / 包内移除）、`offline → published`（重新发布 / 包内重新出现）；草稿不进入解析。
- **删除**：复用软删除（`deleted_at`），`deleted_at` 非空不参与解析与列表；包内移除只置 `offline`，不软删。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_help_article_category_status` | 普通 | `(category_id, status)` | 分类下文章列表 / 前台可见过滤 |
| `idx_sys_help_article_status_top_publish` | 普通 | `(status, is_top, publish_at)` | 已发布列表与置顶 / 发布时间排序 |
| `idx_sys_help_article_source_source_key` | 普通 | `(source, source_key)` | 包来源文章按产品与稳定键定位 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 3 个 + 公共 1 个 = 4 个（≤5）。
- 无物理外键；`category_id` / `package_id` / `author_id` 均为逻辑外键（`category_id` 同库、`package_id` 同库、`author_id` 同服务租户库）。
- **不加 `(source_key, deleted_at)` 唯一**：租户自建文章的 `source_key` 为 `NULL`，达梦把复合唯一中的 NULL 视同相等，会让多条自建文章互撞；唯一性由应用校验承担。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；文章量级小）。
- **归档**：可归档；随 14_01 归档策略按 `updated_at` 配置，本任务不建策略。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建（08_03 产品帮助包装载注册）：文章主体，三态 + 来源 / 包版本 / 本地覆盖 + 阅读反馈计数；多锚点拆附表 | minjian |
