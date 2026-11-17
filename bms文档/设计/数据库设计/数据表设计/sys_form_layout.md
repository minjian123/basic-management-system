# sys_form_layout（表单三级布局）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_form_layout

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `form_design`） |
| 覆盖模块 | 37-表单定制（三级布局：平台默认 / 租户覆盖 / 角色视图） |
| 上游依据 | 《[概要设计 · 表单定制](../../概要设计/36_概要设计_表单定制.md)》§4、《[架构设计 · 表单定制](../../架构设计/30_架构设计_子系统_表单定制.md)》§3 / §7、《[需求 08-2](../../../项目/08_通用能力/需求/08_需求_工作台与表单定制.md#r08-2)》 |
| ORM 模型 | `bms_core/models/platform/form_design.py::SysFormLayout`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 10_01 建表） |
| 相关节点 | [37-表单定制](../37_数据库设计_表单定制.md) 节点、[sys_form_field_attr](sys_form_field_attr.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_code` | VARCHAR(64) | 否 | 与 `scope` / `role_id` / `deleted_at` 复合唯一；建索引 | 表单标识（业务码，逻辑外键 → 平台库 `sys_business.code`，跨库）；保存后不变 |
| `scope` | VARCHAR(16) | 否 | 同上 | 层级：`platform`（平台默认）/ `tenant`（租户覆盖）/ `role`（角色视图） |
| `role_id` | DECIMAL(38,0) | 否 | 同上；默认 `0` | 角色 ID（逻辑外键 → `sys_role.id`，同库）；`0` 表示非角色层级 |
| `layout_config` | TEXT | 否 | — | 布局配置 JSON 文本（`main` + `query` + `detail` + `dictAdvanced`）；应用层解析，理由见《数据规范》§3「多值字段例外」 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_form_layout_form_scope_role_deleted_at` | 唯一 | `(form_code, scope, role_id, deleted_at)` | 同表单同层级（同角色）仅一条；软删除后可复用 |
| `idx_sys_form_layout_form_code` | 普通 | `form_code` | 按表单取三层布局 |

- 无物理外键；`form_code` 为跨库逻辑外键（平台库 `sys_business.code`），`role_id` 同库逻辑外键（`sys_role.id`）。
- **`role_id = 0` 而非 `NULL`**：`(form_code, scope, role_id, deleted_at)` 复合唯一在 `NULL` 上不生效（NULL 互不相等，三库同语义）；用 `0` 占位保证「同表单同层级仅一条」成立（与 `sys_role_permission.source_menu_id` 同范式）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（租户库配置表）。
- **归档**：不归档（配置元数据；变更留痕走字段级审计）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期自动建表、运维 / CI 经 `ops.init_schema`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建表结构（任务 10_01）：三级布局 `layout_config`；定位列取 `form_code`（决策 17，不存 `form_id`）；`role_id = 0` 占位规避唯一约束 NULL 语义 | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套
