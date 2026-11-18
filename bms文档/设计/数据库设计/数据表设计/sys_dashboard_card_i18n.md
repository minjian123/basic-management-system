# sys_dashboard_card_i18n（工作台卡片名多语言附表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_dashboard_card_i18n

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `dashboard`） |
| 覆盖模块 | 36-首页工作台（卡片名多语言） |
| 上游依据 | 《[概要设计 · 首页工作台](../../概要设计/35_概要设计_首页工作台.md)》§4、《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》§5、《[国际化规范](../../../规范/国际化规范.md)》 |
| ORM 模型 | `bms_core/models/platform/dashboard.py::SysDashboardCardI18n`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 11_01 建表） |
| 相关节点 | [36-首页工作台](../36_数据库设计_首页工作台.md) 节点、[sys_dashboard_card](sys_dashboard_card.md)、[30-国际化管理](../30_数据库设计_国际化管理.md)（附表台账） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，语义见《[数据规范](../02_数据库设计_数据规范.md)》§2；多语言附表通用约定见同文档 §5。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `card_id` | DECIMAL(38,0) | 否 | 与 `locale` / `deleted_at` 复合唯一；建索引 | 卡片 ID（逻辑外键 → `sys_dashboard_card.id`，同库） |
| `locale` | VARCHAR(16) | 否 | 同上 | 语言标识（IETF 标准形态，如 `zh-CN` / `en-US`；比较大小写不敏感） |
| `name` | VARCHAR(128) | 否 | — | 卡片名的该语言文案（去空白后为空视为缺失，回退下一级） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_dashboard_card_i18n_card_locale_deleted_at` | 唯一 | `(card_id, locale, deleted_at)` | 同一卡片同一语言仅一条活行；软删除后可复用 |
| `idx_sys_dashboard_card_i18n_card_id` | 普通 | `card_id` | 按卡片批量取文案 |

- 无物理外键；`card_id` 同库逻辑外键。
- **同生命周期**：卡片软删除时附表行同事务连带软删（统一助手 `soft_delete_i18n`），不留孤儿行。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（随主表）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地，与主表同库同链。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-18 | v1 | 新建表结构（任务 11_01）：卡片名多语言附表；台账状态由「待落地」转「已落地」 | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套
