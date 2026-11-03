# sys_i18n_locale（语言清单）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_i18n_locale

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 覆盖模块 | 30-国际化管理 |
| 上游依据 | [需求 06-1](../../../项目/08_通用能力/需求/06_需求_国际化.md#r06-1)、《[概要设计 · 国际化管理](../../概要设计/29_概要设计_国际化管理.md)》§4、《[架构设计 · 国际化](../../架构设计/24_架构设计_子系统_国际化.md)》§4、《[数据规范](../02_数据库设计_数据规范.md)》§5 |
| ORM 模型 | `bms_core/models/platform/i18n.py::SysI18nLocale`（继承 `BaseModel`；登记于 `models/platform/__init__.py::MODEL_MODULES`） |
| 状态 | 待落库（08 `05_01` 随 `platform:tenant` 链建表） |
| 相关节点 | [30-国际化管理](../30_数据库设计_国际化管理.md)、[数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」 |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一，默认 `i18n_locale` | 表单标识（多表联合判别列；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(16) | 否 | `(code, deleted_at)` 复合唯一（应用层大小写不敏感判重） | 语言标识（IETF 语言标签，标准形态如 `zh-CN` / `en-US` / `ar-SA`；比较一律大小写不敏感） · **系统字段**：代码 |
| `name` | VARCHAR(64) | 否 | — | 语言名称（本地名，如 `简体中文` / `English` / `العربية`） · **系统字段**：名称 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） · **系统字段**：状态 |
| `rtl` | BOOLEAN | 否 | 默认 `false` | 是否从右到左（驱动前端布局方向切换） |
| `is_default` | BOOLEAN | 否 | 默认 `false`；**全表恰一条**（应用层保证） | 默认语言标记（派生主表默认文案 + 缺省回退目标；不承担必填语义） |
| `sort` | INT | 否 | 默认 0，升序 | 排序（语言下拉与列表） · **系统字段**：排序 / 行序 |
| `is_overridden` | BOOLEAN | 否 | 默认 `false` | 是否被租户改过（`false` = 平台默认行；种子刷新与保护判据） · **系统字段**：状态（覆盖标记） |
| `parent_id` | DECIMAL(38,0) | 是 | — | 上级字典 ID（自引用同表 `id`；本表无层级，按系统字段口径保留） · **系统字段**：上级字典 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_i18n_locale_code_deleted_at` | 唯一 | `(code, deleted_at)` | 语言标识唯一（软删除后可复用） |
| `uq_sys_i18n_locale_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |
| `idx_sys_i18n_locale_sort` | 普通 | `sort` | 排序字段（进排序白名单，须建索引） |

- 无物理外键。
- **默认语言唯一性不走 DB 约束**：软删 + 布尔标记无法用跨方言一致的唯一索引表达，由写路径「先清其它行 `is_default` 再置本条」+ 读路径断言（缺 / 重即 `44006`）保证。
- **约束实际效力**：`(code, deleted_at)` / `(form_key, deleted_at)` 在 `deleted_at IS NULL` 时**不产生唯一约束效果**（NULL 互不相等，SQLite / MySQL / PostgreSQL 同，02_02 已实测），故 `code` 唯一性由**应用层判重**（写前 `SELECT`，大小写不敏感）保证；该问题为全平台软删表共性，阶段收口统一评估。
- 公共软删除索引 `idx_sys_i18n_locale_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在此重复。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（语言清单为小型热配置数据）。
- **归档**：不归档（在用配置数据）；变更经 ORM 事件落字段级审计（06_02 消费）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。
- **平台默认与租户覆盖**：平台默认语言行由幂等种子下发到各租户库（`is_overridden=false`），租户改值 / 新增语言置 `true`；平台默认升级只刷新 `false` 行。读取只走本表（不跨库合并）。
- **缓存**：`bms:{tenant}:i18n:locales`（载荷 `{v, locales}`）、版本键 `bms:{tenant}:i18n:version`；变更后**先提交事务 → DEL 清单键 + DEL 全部语言包键 → INCR 版本 → 刷新进程内快照**。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-03 | v1 | 新建表结构（platform 服务租户库；08 `05_01` 落 `platform:tenant` 链）：语言清单含 `rtl` / `is_default` / `sort` / `is_overridden`；默认语言唯一由应用层保证 | minjian |
