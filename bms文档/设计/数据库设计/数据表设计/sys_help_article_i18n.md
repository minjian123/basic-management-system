# sys_help_article_i18n（帮助文章多语言附表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_article_i18n

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（文章标题 / 正文多语言） |
| 上游依据 | [需求 09-4](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-4)、《[概要设计 · 帮助中心](../../概要设计/17_概要设计_帮助中心.md)》§4、《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》§5 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpArticleI18n`（继承 `BaseModel`） |
| 状态 | 已设计（随 08_03 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_article](sys_help_article.md)（主表）、[30-国际化管理](../30_数据库设计_国际化管理.md)（附表台账）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 附表行标识 |
| `article_id` | DECIMAL(38,0) | 否 | — | 主表 ID（逻辑外键 → `sys_help_article.id`） |
| `locale` | VARCHAR(16) | 否 | — | 语言标识（IETF 标准形态，如 `zh-CN` / `en-US`） |
| `title` | VARCHAR(256) | 否 | — | 该语言标题 |
| `content` | TEXT | 否 | 默认空串 | 该语言正文 HTML（已净化） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **回退口径**：读取侧按「请求语言 → 租户默认语言 → 主表 `title` / `content` 快照」三级回退；`locale` 比较大小写不敏感。
- **整体替换**：装载 / 维护保存时按主表行整体替换（旧行软删、按语言插新行），保证 `(article_id, locale, deleted_at)` 不冲突。
- **同生命周期**：主表软删除时附表同事务连带软删（`bms_core.repositories.i18n.soft_delete_i18n`），不留孤儿行。
- **台账**：本表登记于 `bms_core/i18n/attachments.py`，文案列为 `title` / `content`；状态由「待落地」改为「已落库」。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_help_article_i18n_article_locale_deleted_at` | 唯一 | `(article_id, locale, deleted_at)` | 一篇文章一种语言一行（软删除后释放） |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务唯一索引 1 个 + 公共 1 个 = 2 个（≤5）。
- 无物理外键；`article_id` 为逻辑外键（同库），唯一索引前缀已覆盖按主表 ID 的读取。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：随主表归档；不单独建策略。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建（08_03 产品帮助包装载注册）：文章标题 / 正文多语言附表，随包装载整体替换 | minjian |
