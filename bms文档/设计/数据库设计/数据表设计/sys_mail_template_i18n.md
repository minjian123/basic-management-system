# sys_mail_template_i18n（邮件模板多语言附表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_mail_template_i18n

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（邮件与短信通知） |
| 覆盖模块 | 25-邮件通知（邮件主题 / 正文多语言） |
| 上游依据 | [需求 04-3](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-3)、《[概要设计 · 邮件通知](../../概要设计/24_概要设计_邮件通知.md)》§4、《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》§5、《[数据库设计 · 国际化管理](../30_数据库设计_国际化管理.md)》§2.1 |
| ORM 模型 | `bms_notification.domains.notification.models.mail.py::SysMailTemplateI18n`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_03 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_mail_template](sys_mail_template.md)（主表）；i18n 附表台账状态由「待落地」改「已落库」 |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 附表行标识 |
| `template_id` | DECIMAL(38,0) | 否 | 逻辑外键 → `sys_mail_template.id`；与 `locale`、`deleted_at` 复合唯一 | 模板标识 |
| `locale` | VARCHAR(16) | 否 | — | 语言标识（IETF 形态，如 `zh-CN` / `en-US`；比较大小写不敏感） |
| `subject` | VARCHAR(256) | 否 | — | 该语言主题 |
| `content` | TEXT | 否 | 默认空串 | 该语言正文（Jinja2 / HTML） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **承载全部语言**：主表默认文案列是派生快照；附表可容纳任意启用语言，新增语言不改表结构与接口契约。
- **读写助手**：统一经 `bms_core/repositories/i18n.py` 的 `load_i18n_texts` / `replace_i18n_texts` / `soft_delete_i18n`（多文案列 `subject` + `content`，各列独立回退）。
- **同生命周期**：主表软删除时附表同事务连带软删，不留孤儿行。
- **审计**：文案变更跟随主表业务留痕，附表不单独纳入字段级审计。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_mail_template_i18n_template_locale_deleted_at` | 唯一 | `(template_id, locale, deleted_at)` | 同一模板同一语言一条活文案（软删后可重建） |

- 公共 `deleted_at` 索引由元数据命名约定生成；唯一索引 1 个 + 公共 1 个 = 2 个（≤5）。
- 无物理外键；`template_id` 为同库逻辑外键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（随主表）。
- **归档**：随主表归档策略处理，本任务不建策略。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_03 邮件与短信通知）：邮件主题 / 正文多语言附表，关闭 05_02 台账「待落地」 | minjian |
