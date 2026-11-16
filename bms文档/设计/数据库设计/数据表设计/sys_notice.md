# sys_notice（公告主表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_notice

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | notification 服务租户库 `bms_notification_{code}`（归属部署单元 `notification`） |
| 归属业务域 | `notification`（公告管理） |
| 覆盖模块 | 19-公告管理（全员公告发布 / 置顶 / 过期下线 / 已读回执） |
| 上游依据 | [需求 04-2](../../../项目/08_通用能力/需求/04_需求_通知与公告.md#r04-2)、《[概要设计 · 公告管理](../../概要设计/18_概要设计_公告管理.md)》§2 / §4 / §5、《[架构设计 · 通知公告](../../架构设计/22_架构设计_子系统_通知公告.md)》§3 |
| ORM 模型 | `bms_notification.domains.notification.models.notice.py::SysNotice`（继承 `BaseModel`） |
| 状态 | 已设计（随 07_02 进 notification 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_notice_read](sys_notice_read.md)（已读回执）、[sys_notice_i18n](sys_notice_i18n.md)（多语言附表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 公告标识 |
| `title` | VARCHAR(256) | 否 | — | 标题（系统默认语言派生快照，恒非空） |
| `content` | TEXT | 否 | 默认空串 | 正文 HTML（已净化；默认语言派生快照；草稿可为空） |
| `type` | VARCHAR(32) | 否 | 默认 `system` | 公告类型（选项集 `bms.notice.type` 的值） |
| `priority` | VARCHAR(16) | 否 | 默认 `normal` | 优先级（选项集 `bms.notice.priority` 的值） |
| `is_top` | BOOLEAN | 否 | 默认 false | 是否置顶 |
| `publish_at` | DATETIME | 否 | — | 发布时间（UTC；未到该时间不展示） |
| `expire_at` | DATETIME | 是 | — | 过期时间（UTC；NULL = 永不过期；到达后不展示） |
| `status` | VARCHAR(16) | 否 | 默认 `draft` | 状态：`draft` 草稿 / `published` 发布中 / `offline` 已下线 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **多语言**：标题 / 正文的逐语言文案存 [sys_notice_i18n](sys_notice_i18n.md)；本表两列为**系统默认语言派生快照**，由服务端按「系统默认语言 → 请求语言 → 首个有值语言」写入，调用方不单独提交。
- **正文格式**：统一存 HTML，后端按白名单清洗后入库；长度按清洗后 UTF-8 字节 ≤ 60000 校验（MySQL `TEXT` 上限）。
- **软删除**：删除写 `deleted_at`；列表 / 详情 / 统计全部过滤；回执与附表保留供审计追溯，附表同事务连带软删。
- **状态迁移**：`draft → published`（发布）、`published → published`（编辑重发）、`published → offline`（到期扫描）；`offline → published`、`published → draft`、`draft → offline` 一律拒绝。
- **审计**：属关键表，字段级变更经 ORM 事件自动记录（`sys_notice` 由 notification 服务装载期注册审计白名单）；已读回执与 i18n 附表不单独审计。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_notice_status_top_publish` | 普通 | `(status, is_top, publish_at)` | 发布中列表过滤与置顶 / 发布时间排序 |
| `idx_sys_notice_status_expire` | 普通 | `(status, expire_at)` | 过期扫描（发布中且到期） |
| `idx_sys_notice_type` | 普通 | `(type)` | 管理列表类型筛选 |

- 公共 `deleted_at` 索引由元数据命名约定生成（`idx_sys_notice_deleted_at`），不在本表重复列；业务索引 3 个 + 公共 1 个 = 4 个（≤5）。
- 无物理外键；`created_by` / `updated_by` 为逻辑外键 → `sys_user.id`（跨服务，不建约束）。
- 置顶排序使用 `CASE WHEN is_top THEN updated_at ELSE publish_at END`，组合索引不覆盖 CASE 排序；公告量级小，先正确性优先。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；公告量级小）。
- **归档**：可归档；按 `created_at` / `expire_at` 由 14_01 既有归档策略配置，本任务不建策略。
- **建表**：进入 notification 服务**租户链**，由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（07_02 公告管理）：公告主表，三态 + 置顶 + 发布时间 / 过期时间，支撑全员公告与过期下线 | minjian |
