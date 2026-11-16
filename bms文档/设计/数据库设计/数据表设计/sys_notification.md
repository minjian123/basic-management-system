# sys_notification（站内信表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_notification

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（通知中心） |
| 覆盖模块 | 18-通知中心（个人站内信 / 待办提醒） |
| 上游依据 | [需求 04-1](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-1)、《[概要设计 · 通知中心](../../概要设计/16_概要设计_通知中心.md)》§2 / §4 / §5、《[架构设计 · 通知公告](../../架构设计/22_架构设计_子系统_通知公告.md)》§2 |
| ORM 模型 | `bms_notification/domains/notification/models/notification.py::SysNotification`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_01 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | 18-通知中心（节点待建）；sys_notice（公告，07_02 建表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 通知标识 |
| `user_id` | DECIMAL(38,0) | 否 | 逻辑外键 → `sys_user.id` | 收件用户（个人维度；一条记录一个用户） |
| `title` | VARCHAR(256) | 否 | — | 标题（消费侧限长 256） |
| `content` | TEXT | 否 | 默认空串 | 正文（生产方已按收件人语言渲染；不走 i18n 附表） |
| `type` | VARCHAR(32) | 否 | 默认 `system` | 通知类型：`system`（系统提示）/ `approval`（审批待办）/ `alert`（告警）/ `import`（导入导出任务结果） |
| `biz_type` | VARCHAR(64) | 是 | — | 业务类型（如 `approval` / `export`），供跳转与业务识别 |
| `biz_id` | VARCHAR(64) | 是 | — | 业务标识（如作业主键 / 单据主键），供跳转 |
| `is_read` | BOOLEAN | 否 | 默认 false | 已读标记（false 未读 / true 已读） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **软删除**：用户主动删除即写 `deleted_at`；列表、详情、未读数、删除全部按 `deleted_at IS NULL` 过滤，数据保留至归档。
- **内容语言**：正文由生产方按收件人 locale 渲染后写入；本表不承载多语言附表（运行时内容，非可维护文案）。
- **去重**：消费幂等由 `sys_event_consumed` 负责；`biz_type` / `biz_id` 不建唯一约束（同一业务允许多条提醒）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_notification_user_id_created_at` | 普通 | `(user_id, created_at)` | 列表按时间倒序（含分页） |
| `idx_sys_notification_user_id_is_read` | 普通 | `(user_id, is_read)` | 未读数统计与已读筛选 |
| `idx_sys_notification_user_id_type` | 普通 | `(user_id, type)` | 类型筛选 |

- 公共 `deleted_at` 索引由元数据命名约定生成（`idx_sys_notification_deleted_at`），不在本表重复列；业务索引 3 个 + 公共 1 个 = 4 个（≤5）。
- 无物理外键；`user_id` 为逻辑外键（跨服务，`sys_user` 归 platform 服务）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（MVP 按租户库隔离；通知量随归档策略承接长尾）。
- **归档**：可归档；按 `created_at` 由归档策略处理（随 14_01 既有策略机制配置，本任务不建策略）。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_01 通知中心）：个人站内信落库，三组组合索引支撑列表 / 未读 / 类型筛选 | minjian |
