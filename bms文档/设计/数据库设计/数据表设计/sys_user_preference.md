# sys_user_preference（用户偏好表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user_preference

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `user`（用户偏好 / 用户喜好） |
| 覆盖模块 | 05-用户喜好（主题 / 列表个性化 / 通知偏好 / 工作台自定义） |
| 上游依据 | [需求 04-1](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-1)（通知偏好）、《[概要设计 · 用户喜好](../../概要设计/04_概要设计_用户喜好.md)》§2 / §4、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》「用户偏好」节 |
| ORM 模型 | `bms_core/models/platform/user.py::SysUserPreference`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_01 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | 05-用户喜好（节点待建）、[sys_user](sys_user.md)（语言 / 时区偏好列） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 偏好行标识 |
| `user_id` | DECIMAL(38,0) | 否 | 逻辑外键 → `sys_user.id`；普通索引 | 用户标识 |
| `pref_key` | VARCHAR(128) | 否 | 与 `user_id`、`deleted_at` 复合唯一 | 偏好键（`{域}.{键}`，如 `notify.channels` / `list.user_form`） |
| `pref_value` | TEXT | 否 | — | 偏好值（JSON 字符串；跨方言安全，见《数据规范》§3 多值字段例外） |
| `parent_id` | DECIMAL(38,0) | 是 | — | 上级明细 ID（自引用同表 `id`；顶层为 NULL） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **值格式**：`pref_value` 统一存 JSON 字符串（对象 / 数组 / 标量），读侧解析失败回退默认值并告警；写入前按 `[pref]` 上限校验（单键 64KB）。
- **允许键**：首段 `ui` / `list` / `notify` / `dashboard` / `wizard`；`list.{form_key}` 第二段随表单标识动态。
- **通知偏好结构**：`notify.channels` 为 `{inbox,email,sms}` 布尔对象；`notify.dnd` 为 `{enabled,start,end}`，时间为 `HH:MM`，按 `sys_user.timezone` 解释。
- **软删除**：重置偏好即软删该行；软删后同键可重建（唯一约束含 `deleted_at`）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_preference_user_key_deleted_at` | 唯一 | `(user_id, pref_key, deleted_at)` | 同用户同键唯一（软删后可重建） |
| `idx_sys_user_preference_user_id` | 普通 | `(user_id)` | 按用户取全部偏好 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`user_id` 为逻辑外键（同库 `sys_user`）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（单用户偏好键数上限 200，行数量级小）。
- **归档**：不归档（当前状态数据，随用户删除清理）。
- **建表**：进入 platform 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_01 通知中心）：偏好真实存储落地，支撑通知渠道开关与免打扰时段 | minjian |
