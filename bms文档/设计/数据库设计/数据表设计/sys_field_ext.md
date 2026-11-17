# sys_field_ext（租户自建字段）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_field_ext

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `form_design`） |
| 覆盖模块 | 37-表单定制（租户自建字段元数据与 `ext_*` 物理列生命周期） |
| 上游依据 | 《[概要设计 · 表单定制](../../概要设计/36_概要设计_表单定制.md)》§2.2 / §4、《[架构设计 · 表单定制](../../架构设计/30_架构设计_子系统_表单定制.md)》§4、《[需求 08-2](../../../项目/08_通用能力/需求/08_需求_工作台与表单定制.md#r08-2)》 |
| ORM 模型 | `bms_core/models/platform/form_design.py::SysFieldExt`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 10_01 建表） |
| 相关节点 | [37-表单定制](../37_数据库设计_表单定制.md) 节点、[sys_field_ext_i18n](sys_field_ext_i18n.md)、[sys_field](sys_field.md)（平台库字段定义） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_code` | VARCHAR(64) | 否 | 与 `field_key` / `deleted_at` 复合唯一；建索引 | 表单标识（业务码，逻辑外键 → 平台库 `sys_business.code`，跨库） |
| `field_key` | VARCHAR(64) | 否 | 同上 | 字段键（表单内唯一；小写字母开头，仅小写字母 / 数字 / 下划线，≤ 60） |
| `name` | VARCHAR(128) | 否 | — | 字段名（**按优先级兜底派生的快照**：系统默认语言 → 必填语言 → 首个有值语言；多语言见 `sys_field_ext_i18n`） |
| `type` | VARCHAR(32) | 否 | — | 字段类型（白名单：`text` / `longtext` / `number` / `datetime` / `option` / `option_multi` / `switch` / `file`；**富文本不放开**） |
| `option_set_key` | VARCHAR(128) | 是 | — | 选项集标识引用（仅 `option` / `option_multi`；点分小写带命名空间，如 `bms.user.status`）；**不存选项条目数组** |
| `column_name` | VARCHAR(64) | 否 | 与 `form_code` 复合唯一 | 物理列名（`ext_` + `field_key` 蛇形，≤ 64；由服务端派生，不接受调用方指定） |
| `table_name` | VARCHAR(64) | 否 | — | 目标物理表名（登记期冗余：由 `form_code` 经表单清单解析得出，**仅供巡检对账，不作判定依据**） |
| `ddl_status` | VARCHAR(16) | 否 | 默认 `pending` | 建列生命周期：`pending`（待建列）/ `active`（已生效）/ `failed`（建列失败，可重试） |
| `sort` | INT | 否 | 默认 `0` | 同表单内排序（升序） · **系统字段**：行序（明细排序） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用不删列） · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_field_ext_form_key_deleted_at` | 唯一 | `(form_code, field_key, deleted_at)` | 同表单内字段键唯一；软删除后可复用（重建复用列） |
| `uq_sys_field_ext_form_column_deleted_at` | 唯一 | `(form_code, column_name, deleted_at)` | 同表单内物理列名唯一 |
| `idx_sys_field_ext_form_code` | 普通 | `form_code` | 按表单列示自建字段 |

- 无物理外键；`form_code` 跨库逻辑外键（平台库 `sys_business.code`）。
- **`ext_*` 物理列**：不在建表链，由 DDL 执行器在目标租户库业务表上加列；类型按《[数据规范](../02_数据库设计_数据规范.md)》§3 与 `bms_core/fieldtype/mapping.py` 四库映射：
  - `text` → `VARCHAR(255)`、`longtext` → `TEXT`（四库同为 TEXT）、`number` → `DECIMAL(18,4)`、`datetime` → `DATETIME`/`TIMESTAMP`、`option` → `VARCHAR(64)`、`option_multi` → `TEXT`（逗号分隔）、`switch` → `SMALLINT`、`file` → `VARCHAR(255)`（存文件 ID）。
- **停用不删列**：`status=disabled` 不生成 `DROP COLUMN`；合规销毁走归档链路（14_01）。
- **重建复用列**：同 `form_code` 下同 `column_name` 的停用字段可恢复为 `enabled`（元数据复用，不重复加列）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片；**分片表与平台库表禁止自建字段**（申请即 `40401`）。
- **归档**：不归档（配置元数据）。停用字段的行保留（数据列亦保留）。
- **建表**：本表随 **`platform:tenant` 链**幂等建表落地；`ext_*` 物理列由运行期 DDL 加列，**不在任何链**。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建表结构（任务 10_01）：自建字段元数据 + `ext_*` 物理列生命周期；`options` 语义收窄为 `option_set_key` 标识引用（不存条目数组，与概要 §4 2026-10-21 口径一致）；`table_name` 为巡检冗余列 | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套
