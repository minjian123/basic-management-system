# sys_mail_template（邮件模板主表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_mail_template

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（邮件与短信通知） |
| 覆盖模块 | 25-邮件通知（邮件模板维护 / 多语言 / 沙箱渲染 / 发送） |
| 上游依据 | [需求 04-3](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-3)、《[概要设计 · 邮件通知](../../概要设计/24_概要设计_邮件通知.md)》§2 / §4 / §5、《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》§5 |
| ORM 模型 | `bms_notification.domains.notification.models.mail.py::SysMailTemplate`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_03 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_mail_template_i18n](sys_mail_template_i18n.md)（多语言附表）、[sys_mail_log](sys_mail_log.md)（发送记录） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 模板标识 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一；创建后不可改 | 模板 code（租户内唯一；同 code 覆盖内置默认） |
| `name` | VARCHAR(128) | 否 | — | 模板名称 |
| `subject` | VARCHAR(256) | 否 | — | 主题（系统默认语言派生快照） |
| `content` | TEXT | 否 | 默认空串 | 正文 Jinja2 / HTML（系统默认语言派生快照） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` 启用 / `disabled` 停用（停用不回落内置默认） |
| `remark` | VARCHAR(255) | 是 | — | 备注 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **平台默认模板在代码内置**：本表只存租户模板；读取先本表、无同 `code` 回落代码内置清单，删除覆盖行后自动回落。
- **多语言**：主题 / 正文逐语言文案存 [sys_mail_template_i18n](sys_mail_template_i18n.md)；本表两列为系统默认语言派生快照，由服务端按「系统默认语言 → 请求语言 → 首个有值语言」写入。
- **软删除**：删除写 `deleted_at`；附表同事务连带软删；发送解析过滤软删除行。
- **审计**：属关键表，字段级变更由 notification 服务装载期注册审计白名单后自动记录。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_mail_template_code_deleted_at` | 唯一 | `(code, deleted_at)` | 同一租户同一 code 一条活模板（软删后可重建） |
| `idx_sys_mail_template_status` | 普通 | `(status)` | 状态筛选 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 1 个 + 唯一 1 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`created_by` / `updated_by` 为逻辑外键 → `sys_user.id`（跨服务，不建约束）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；模板量级小）。
- **归档**：随 14_01 既有归档策略配置，本任务不建策略。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_03 邮件与短信通知）：邮件模板主表，支撑 Jinja2 沙箱校验、多语言与异步发送 | minjian |
