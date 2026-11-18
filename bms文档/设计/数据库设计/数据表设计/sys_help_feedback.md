# sys_help_feedback（帮助阅读反馈）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_feedback

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（阅读反馈：有帮助 / 无帮助 + 评论） |
| 上游依据 | [需求 09-4](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-4)、《[概要设计 · 帮助中心](../../概要设计/17_概要设计_帮助中心.md)》§2.1 / §4 / §5、《[架构设计 · 帮助中心](../../架构设计/28_架构设计_子系统_帮助中心.md)》§5 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpFeedback`（继承 `BaseModel`） |
| 状态 | 已设计（随 12_01 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_article](sys_help_article.md)（主表 / 反馈计数）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 反馈行标识 |
| `article_id` | DECIMAL(38,0) | 否 | — | 文章 ID（逻辑外键 → `sys_help_article.id`） |
| `user_id` | DECIMAL(38,0) | 否 | — | 反馈人 ID（逻辑外键 → `sys_user.id`） |
| `feedback` | VARCHAR(16) | 否 | — | 反馈类型：`helpful` 有帮助 / `unhelpful` 无帮助（业务闭集，代码常量） |
| `comment` | VARCHAR(500) | 是 | — | 反馈评论（可空；超长由接口拒绝） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **联合唯一**：`(article_id, user_id, deleted_at)` 防重复；同一用户对同一文章再次提交即**改投**（覆盖 `feedback` / `comment`），
  不产生第二行。
- **计数派生**：`sys_help_article.helpful_count` / `unhelpful_count` 是本表的派生计数，由维护接口在同一事务内按差值增减；
  统计与列表读计数列，不聚合本表。
- **计数写入口径**：计数经单条 `UPDATE ... c = c + n` 自增，不走 ORM 行更新——避免高频反馈把字段级审计链刷满
  （审计只覆盖内容变更，计数属派生数据）。
- **软删除**：保留 `deleted_at` 供 13_01 回收站 / 合规清理使用；当前无删除入口。
- **匿名反馈**：不设计匿名行——读者面要求登录，反馈一律绑定当前用户；`user_id` 不可为空。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_help_feedback_article_user_deleted_at` | 唯一 | `(article_id, user_id, deleted_at)` | 同用户同文章仅一条（软删除后释放） |
| `idx_sys_help_feedback_article_type` | 普通 | `(article_id, feedback)` | 统计按文章 / 反馈类型聚合与明细定位 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`article_id` / `user_id` 均为逻辑外键（`user_id` 指向主数据用户表，同服务租户库口径由 04 系列承接）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；反馈量级小）。
- **归档**：随主表按 `updated_at` 与 14_01 既有归档机制按需配置，本任务不建策略。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-18 | v1 | 新建（12_01 帮助内容维护）：阅读反馈表，联合唯一防重复、可改投；计数落文章主表 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
