# sys_dashboard_template（工作台模板）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_dashboard_template

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `dashboard`） |
| 覆盖模块 | 36-首页工作台（平台默认模板 + 角色模板） |
| 上游依据 | 《[概要设计 · 首页工作台](../../概要设计/35_概要设计_首页工作台.md)》§4 / §5、《[架构设计 · 首页工作台](../../架构设计/29_架构设计_子系统_首页工作台.md)》§4 / §6、《[需求 08-1](../../../项目/08_通用能力/需求/08_需求_工作台与表单定制.md#r08-1)》 |
| ORM 模型 | `bms_core/models/platform/dashboard.py::SysDashboardTemplate`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 11_01 建表） |
| 相关节点 | [36-首页工作台](../36_数据库设计_首页工作台.md) 节点、[sys_dashboard_card](sys_dashboard_card.md)、[07-角色管理](../07_数据库设计_角色管理.md)（`role_id` 逻辑外键） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `scope` | VARCHAR(16) | 否 | 与 `role_id` / `deleted_at` 复合唯一 | 层级：`platform`（平台默认，仅一份）/ `role`（角色模板，一角色至多一份） |
| `role_id` | DECIMAL(38,0) | 否 | 同上；默认 `0` | 角色 ID（逻辑外键 → `sys_role.id`，同库）；`0` 表示平台层级（规避唯一约束在 NULL 上的跨库语义差异） |
| `name` | VARCHAR(128) | 否 | — | 模板名称（管理面展示） |
| `layout_config` | TEXT | 否 | — | 布局配置 JSON 文本（`{cards:[{code,x,y,w,h,visible}]}`）；应用层归一与校验 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用即该级不参与回退） · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

**不设 `is_default` 列**：平台默认模板由 `scope = platform` 的唯一活行判定（复合唯一已保证只有一条），避免「`scope=role` 却 `is_default=true`」的自相矛盾状态（2026-11-18 决策 9）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_dashboard_template_scope_role_deleted_at` | 唯一 | `(scope, role_id, deleted_at)` | 平台层级仅一份（`role_id=0`）、一角色至多一份；软删除后可重建 |
| `idx_sys_dashboard_template_scope_role` | 普通 | `(scope, role_id)` | 解析期按层级 / 角色取模板 |

- 无物理外键；`role_id` 同库逻辑外键（`sys_role.id`）。
- **`role_id = 0` 而非 `NULL`**：保证复合唯一在四库同语义下成立（与 `sys_form_layout` 同范式）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（租户库配置表）。
- **归档**：不归档（配置元数据；变更留痕走字段级审计）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地。
- **种子**：平台默认模板由 `bms_core.tenant.seed.dashboard` 在缺失时写入（初值 = 当前启用内置卡的行流式布局）；租户已编辑的模板不被种子覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-18 | v1 | 新建表结构（任务 11_01）：平台默认模板与角色模板；**去掉概要中的 `is_default` 列**（以 `scope` 唯一行判定，决策 9） | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套
