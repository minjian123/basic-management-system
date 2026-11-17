# sys_form_field_attr（表单字段属性）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_form_field_attr

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `form_design`） |
| 覆盖模块 | 37-表单定制（三级字段属性：必填 / 默认值 / 提示 / 校验规则 / 组件形态 / 选项集来源 / 只读 / 隐藏） |
| 上游依据 | 《[概要设计 · 表单定制](../../概要设计/36_概要设计_表单定制.md)》§2.1 / §4、《[架构设计 · 表单定制](../../架构设计/30_架构设计_子系统_表单定制.md)》§5、《[需求 08-2](../../../项目/08_通用能力/需求/08_需求_工作台与表单定制.md#r08-2)》 |
| ORM 模型 | `bms_core/models/platform/form_design.py::SysFormFieldAttr`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 10_01 建表；设计期决策 16 新增本表） |
| 相关节点 | [37-表单定制](../37_数据库设计_表单定制.md) 节点、[sys_form_layout](sys_form_layout.md)、[sys_field](sys_field.md)（平台库字段定义） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_code` | VARCHAR(64) | 否 | 与 `scope` / `role_id` / `field_key` / `deleted_at` 复合唯一；建索引 | 表单标识（业务码，逻辑外键 → 平台库 `sys_business.code`，跨库） |
| `scope` | VARCHAR(16) | 否 | 同上 | 层级：`platform` / `tenant` / `role` |
| `role_id` | DECIMAL(38,0) | 否 | 同上；默认 `0` | 角色 ID（逻辑外键 → `sys_role.id`，同库）；`0` 表示非角色层级 |
| `field_key` | VARCHAR(64) | 否 | 同上 | 字段键（引用 `sys_field.field_key` 或 `sys_field_ext.field_key`；不建物理列，允许引用暂不存在的键，渲染期跳过） |
| `attrs` | TEXT | 否 | — | 字段属性 JSON 文本（`required` / `placeholder` / `default_value` / `rules[]` / `option_set_key` / `widget` / `readonly` / `hidden` / 上传三件）；应用层解析，未知键读时丢弃、写时拒收 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_form_field_attr_form_scope_role_field_deleted_at` | 唯一 | `(form_code, scope, role_id, field_key, deleted_at)` | 同表单同层级同字段仅一条；软删除后可复用 |
| `idx_sys_form_field_attr_form_code` | 普通 | `form_code` | 按表单取三层属性 |

- 无物理外键；`form_code` 跨库逻辑外键（平台库 `sys_business.code`）。
- `field_key` **不作为外键**：属性可能在字段创建前先配置（草稿态），渲染期按「失效引用跳过」处置；保存期 `unknown-field` 只告警不阻断（与布局口径一致）。
- `role_id = 0` 占位与 `sys_form_layout` 同口径。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档。
- **建表**：随 **`platform:tenant` 链**幂等建表落地。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建表结构（任务 10_01，设计期决策 16）：承载平台字段与租户覆盖的字段属性，补概要 §4 表清单缺口；`attrs` 为 JSON 文本，未知键写时拒收 | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套
