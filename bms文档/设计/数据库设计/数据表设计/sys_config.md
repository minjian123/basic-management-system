# sys_config（系统参数）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_config

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 覆盖模块 | 11-系统参数 |
| 上游依据 | [需求 03-8](../../../项目/06_认证与安全/需求/03_需求_验证码与账号治理.md#r03-8)、《[概要设计 · 系统参数](../../概要设计/10_概要设计_系统参数.md)》「核心表」节、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》§4.1 |
| ORM 模型 | `bms_core/config/models.py::SysConfig`（继承 `BaseModel`；登记于 `db/migration.py::COMMON_MODEL_MODULES`） |
| 状态 | 已落库（`platform:tenant` 链迁移 `0004_sys_config`，2026-09-27） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 10-系统参数](../../概要设计/10_概要设计_系统参数.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(128) | 否 | 与 `deleted_at` 复合唯一 | 参数键（点分小写，如 `captcha.scene.login.required`）。**DB 列名 `code`，ORM 属性与契约字段名仍为 `config_key`** · **系统字段**：代码 |
| `name` | VARCHAR(128) | 否 | 应用侧缺省取 `code` | 参数名称（展示） · **系统字段**：名称 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） · **系统字段**：状态 |
| `value` | TEXT | 否 | —（应用侧缺省空串；DB 不设默认值） | 参数值（标量 / 布尔 / JSON 字符串统一按文本承载，由消费方按类型解析；仅应用侧读写、无库内 JSON 检索需求，取 `TEXT` 最大跨方言安全；**TEXT 在 MySQL 不允许默认值**，空值由应用侧承载） |
| `remark` | VARCHAR(255) | 是 | — | 备注（参数用途说明） |
| `parent_id` | BIGINT | 是 | — | 上级字典 ID（自引用同表 `id`；顶层 NULL；本表无层级，按系统字段口径保留） · **系统字段**：上级字典 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_config_code_deleted_at` | 唯一 | `(code, deleted_at)` | 参数键唯一（软删除后可复用；原 `uq_sys_config_config_key_deleted_at`） |
| `uq_sys_config_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |

- 无物理外键；`code`（DB 列名，ORM 属性 / 契约字段名 `config_key`）为平台统一命名空间键（消费方自定义前缀，如 `captcha.` / `password.` / `session.`）。
- 无独立业务索引（查询按 `code` 唯一键命中或 `IN` 子集）；公共软删除索引 `idx_sys_config_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在本表重复列出。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（参数为小型热配置数据）。
- **归档**：不归档（在用配置数据）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。
- **缓存**：`bms:{tenant}:config:{config_key}`（短 TTL + 随机偏移；版本键 `bms:{tenant}:config:version`），变更后删 key 并递增版本号（先写库后删缓存）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（platform 服务租户库；随 `03_08` 落 `platform:tenant` 链迁移 `0004_sys_config`） | minjian |
| 2026-10-11 | v2 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `name` + `status` + `parent_id`；既有标识列 `config_key` **DB 列名改 `code`**（ORM 属性 / 契约字段名保持 `config_key`），唯一约束改 `uq_sys_config_code_deleted_at`；随 `platform:tenant` 链 `0015_system_fields_form_key` | minjian |
