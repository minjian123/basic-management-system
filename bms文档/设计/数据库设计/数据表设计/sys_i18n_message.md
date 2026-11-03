# sys_i18n_message（固定文案语言包）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_i18n_message

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 覆盖模块 | 30-国际化管理 |
| 上游依据 | [需求 06-1](../../../项目/08_通用能力/需求/06_需求_国际化.md#r06-1)、《[概要设计 · 国际化管理](../../概要设计/29_概要设计_国际化管理.md)》§4、《[架构设计 · 国际化](../../架构设计/24_架构设计_子系统_国际化.md)》§2、《[国际化规范](../../../规范/国际化规范.md)》§2 / §5 |
| ORM 模型 | `bms_core/models/platform/i18n.py::SysI18nMessage`（继承 `BaseModel`；登记于 `models/platform/__init__.py::MODEL_MODULES`） |
| 状态 | 已落库（08 `05_01` 随 `platform:tenant` 链建表） |
| 相关节点 | [30-国际化管理](../30_数据库设计_国际化管理.md)、[sys_i18n_locale](sys_i18n_locale.md)、[数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」 |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一，默认 `i18n_message` | 表单标识（多表联合判别列；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(128) | 否 | `(code, locale, deleted_at)` 复合唯一 | 文案 key（`模块.页面.字段`，如 `user.form.username`、`error.44001`）。**DB 列名 `code`，ORM 属性与契约字段名为 `msg_key`** |
| `name` | VARCHAR(128) | 否 | 默认空串（应用侧缺省取 `code`） | 展示名（维护列表用，非文案本身） · **系统字段**：名称 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`）。当前实现恒 `enabled`，不承载「废弃 key 停用」语义 · **系统字段**：状态 |
| `locale` | VARCHAR(16) | 否 | 同上复合唯一 | 语言标识（与 [sys_i18n_locale](sys_i18n_locale.md) `code` 同形态、标准形态比较不敏感） |
| `value` | TEXT | 否 | 默认空串（应用侧；TEXT 在 MySQL 不允许默认值） | 该语言文案；**去空白后为空即「缺失」**（缺失回退默认语言文案，不渲染空白） |
| `remark` | VARCHAR(255) | 是 | — | 备注（维护页说明 / 插值变量提示） |
| `is_overridden` | BOOLEAN | 否 | 默认 `false` | 是否被租户改过（`false` = 平台默认行；种子刷新与删除保护判据） · **系统字段**：状态（覆盖标记） |
| `parent_id` | DECIMAL(38,0) | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） · **系统字段**：上级明细 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_i18n_message_code_locale_deleted_at` | 唯一 | `(code, locale, deleted_at)` | 同 key 同语言唯一（软删除后可复用） |
| `uq_sys_i18n_message_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |
| `idx_sys_i18n_message_locale` | 普通 | `locale` | 语言包按语言全量加载（复合唯一以 `code` 打头，无法覆盖本查询） |

- 无物理外键（`locale` 为对 `sys_i18n_locale.code` 的软引用：语言停用后允许存量文案保留）。
- **约束实际效力**：`(code, locale, deleted_at)` 在 `deleted_at IS NULL` 时**不产生唯一约束效果**（NULL 互不相等，三库同语义，02_02 已实测），唯一性由**应用层判重**（写前按 `(code, locale)` + `locale` 归一后 `SELECT`）保证；表清单一并登记该共性问题的收口评估。
- 公共软删除索引 `idx_sys_i18n_message_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在此重复。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（语言包数据量小、变更低频）。
- **归档**：不归档；语言包变更经 ORM 事件落字段级审计（`sys_data_audit_log`，06_02 消费）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。
- **平台默认与租户覆盖**：平台默认文案（`common.*` / `error.*` / `i18n.*`）由幂等种子下发到各租户库（`is_overridden=false`），租户改值置 `true`；平台默认升级只刷新 `false` 行；`is_overridden=false` 的行不可删除（仅可改值）。
- **缓存**：`bms:{tenant}:i18n:messages:{locale}`（载荷 `{v, messages}`）、版本键 `bms:{tenant}:i18n:version`；变更后**先提交事务 → DEL 受影响语言键 → INCR 版本**，读路径按版本比对（版本不一致即回源）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-03 | v1 | 新建表结构（platform 服务租户库；08 `05_01` 落 `platform:tenant` 链）：`(code, locale, deleted_at)` 复合唯一 + `locale` 索引 + `remark` / `is_overridden`；DB 列名 `code`、ORM 属性 `msg_key` | minjian |
