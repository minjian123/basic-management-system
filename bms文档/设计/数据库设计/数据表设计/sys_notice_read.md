# sys_notice_read（公告已读回执表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_notice_read

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（公告管理） |
| 覆盖模块 | 19-公告管理（已读回执与已读 / 未读统计） |
| 上游依据 | [需求 04-2](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-2)、《[概要设计 · 公告管理](../../概要设计/18_概要设计_公告管理.md)》§2 / §4、《[架构设计 · 通知公告](../../架构设计/22_架构设计_子系统_通知公告.md)》§3 |
| ORM 模型 | `bms_notification.domains.notification.models.notice.py::SysNoticeRead`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_02 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_notice](sys_notice.md)（公告主表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 回执标识 |
| `notice_id` | DECIMAL(38,0) | 否 | 逻辑外键 → `sys_notice.id`；与 `user_id`、`deleted_at` 复合唯一 | 公告标识 |
| `user_id` | DECIMAL(38,0) | 否 | 逻辑外键 → `sys_user.id`；普通索引 | 阅读用户（个人维度） |
| `read_at` | DATETIME | 否 | — | 阅读时间（UTC；重复阅读保留首次时间） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **一人一条**：`(notice_id, user_id, deleted_at)` 复合唯一；重复阅读幂等，不新增行；并发插入由唯一约束兜底。
- **软删除**：本期不提供回执删除入口；公告软删除时回执保留（审计追溯），统计接口对已删除公告返回 `70201`。
- **审计**：回执写入量大、非关键变更，**不纳入字段级审计**（与概要 §4 一致）。
- **应读人数不落表**：应读人数实时取平台启用用户数，避免快照漂移；本表只存已读事实。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_notice_read_notice_user_deleted_at` | 唯一 | `(notice_id, user_id, deleted_at)` | 同一公告同一用户一条活回执（软删后可重建） |
| `idx_sys_notice_read_user_id` | 普通 | `(user_id)` | 按用户批量取已读公告（列表已读状态） |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 唯一索引前两列 `(notice_id, user_id)` 同时支撑按公告统计已读人数（索引前缀）。
- 无物理外键；`user_id` 为跨服务逻辑外键（`sys_user` 归 platform 服务）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库）。
- **归档**：随租户规模增长，可纳入 14_01 归档策略（按 `read_at` / `created_at` 阈值流转）；本任务不建策略。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_02 公告管理）：雪花 ID 主键 + `(notice_id, user_id, deleted_at)` 复合唯一，回执幂等与已读统计 | minjian |
