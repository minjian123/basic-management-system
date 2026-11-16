# sys_sms_log（短信发送记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_sms_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（邮件与短信通知） |
| 覆盖模块 | 25-邮件通知（短信发送 / 渠道 / 场景 / 失败原因） |
| 上游依据 | [需求 04-3](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-3)、《[概要设计 · 邮件通知](../../概要设计/24_概要设计_邮件通知.md)》§2 / §4 / §5、《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》§3 / §6 |
| ORM 模型 | `bms_notification.domains.notification.models.sms.py::SysSmsLog`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_03 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_sms_template](sys_sms_template.md)（模板）、[sys_mail_log](sys_mail_log.md)（邮件记录） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 记录标识 |
| `recipient` | VARCHAR(32) | 是 | — | 收件手机号（缺失时为空） |
| `channel` | VARCHAR(16) | 否 | 默认 `aliyun` | 实际发送渠道（`aliyun` / `tencent`） |
| `template_code` | VARCHAR(64) | 是 | — | 模板 code（raw 发送为空） |
| `scene` | VARCHAR(16) | 是 | — | 场景（选项集 `bms.sms.scene`） |
| `content` | TEXT | 是 | — | **脱敏后的正文**（连续 4 位及以上数字替换为 `****`） |
| `status` | VARCHAR(16) | 否 | 默认 `pending` | 状态：`pending` / `success` / `failed` / `skipped` |
| `error_msg` | VARCHAR(512) | 是 | — | 失败原因摘要（厂商返回码 / 渠道未配置等） |
| `attempts` | INT | 否 | 默认 0 | 已尝试次数 |
| `user_id` | DECIMAL(38,0) | 是 | — | 收件用户 ID（逻辑外键 → `sys_user.id`；可空） |
| `idempotency_key` | VARCHAR(128) | 是 | 与 `deleted_at` 复合唯一 | 幂等键（可空） |
| `job_id` | DECIMAL(38,0) | 是 | — | 发送作业 ID（逻辑外键 → 作业表，可空） |
| `sent_at` | DATETIME | 是 | — | 发送成功时间（UTC） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **正文脱敏**：验证码 / 令牌等连续数字在入日志前替换为 `****`；完整正文只在作业负载中（随作业保留期清理）。
- **状态口径**：同 [sys_mail_log](sys_mail_log.md)；`skipped` 当前只用于免打扰。
- **幂等**：写路径先按 `(idempotency_key, deleted_at IS NULL)` 查询；唯一约束只作并发兜底。
- **审计**：发送记录不纳入字段级审计。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_sms_log_idempotency_key_deleted_at` | 唯一 | `(idempotency_key, deleted_at)` | 幂等键唯一（可空） |
| `idx_sys_sms_log_status_created_at` | 普通 | `(status, created_at)` | 按状态 / 时间检索与清理 |
| `idx_sys_sms_log_template_code` | 普通 | `(template_code)` | 按模板检索 |
| `idx_sys_sms_log_user_id` | 普通 | `(user_id)` | 按收件用户检索 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 3 个 + 唯一 1 个 + 公共 1 个 = 5 个（≤5）。
- 无物理外键；`user_id` 跨服务（platform），不建库约束。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；发送记录量级可控）。
- **归档**：随 14_01 既有归档策略按 `created_at` 配置，本任务不建策略。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_03 邮件与短信通知）：短信发送记录，正文脱敏 | minjian |
