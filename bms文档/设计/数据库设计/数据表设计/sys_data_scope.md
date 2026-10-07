# sys_data_scope（角色数据权限）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_data_scope

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 07-角色管理（数据权限配置） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》「核心表」节、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「数据权限」节、《[组件设计 · 权限配置](../../组件设计/08_交互类/07_组件设计_权限配置/07_组件设计_权限配置.md)》「数据权限」节、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_platform/models/role.py::SysDataScope`（继承 `BaseModel`；待落地） |
| 状态 | 待落库（表文件就绪；模型 / 迁移随本任务落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_role](sys_role.md)、[sys_dict_type](sys_dict_type.md)、[sys_dict_attr](sys_dict_attr.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `role_id` | BIGINT | 否 | 建索引 | 角色 ID（逻辑外键 → `sys_role.id`，同库） |
| `dict_type_id` | BIGINT | 否 | — | 字典类型 ID（platform 服务租户库实体，**跨库逻辑外键** → `sys_dict_type.id`） |
| `policy_type` | VARCHAR(16) | 否 | — | 策略类型（`select` / `region` / `match` / `extension`） |
| `config` | JSON | 否 | 默认 `[]` | 结构化策略配置（**只选不编**，按 `policy_type` 分结构，写入时后端 schema 强校验） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_data_scope_role_dict_policy_deleted_at` | 唯一 | `(role_id, dict_type_id, policy_type, deleted_at)` | 一角色对一字典一策略一条 |
| `idx_sys_data_scope_role_id` | 普通 | `role_id` | 按角色取数据权限 |

- 无物理外键；`role_id` 同库逻辑引用，`dict_type_id` **跨库逻辑引用** platform 服务租户库字典类型。
- **`config` 结构（按 `policy_type`，只选不编）**：
  - `select`：`[{"item_code": "enabled"}, ...]` —— 直接勾选该字典的数据（分页勾选，选中即授权）
  - `region`：`[{"start": "a", "end": "m"}, ...]` —— 开始值 / 结束值（用动态字典组件选择字典数据）
  - `match`：`[{"field": "code", "pattern": "user_*"}, ...]` —— 字段 + 通配符值；`field` 须属该字典类型白名单（内置 `code` / `name` / `remark` + 已启用 `attr_key`），`pattern` 仅允许 `*` `?` 与中英文 / 数字 / 下划线（越界拒绝，错误码 `30047`）
  - `extension`：`[{"key": "dept_subtree", "params": {...}}, ...]` —— 扩展权限（预设 / 二次开发注册的后端筛选器）+ 参数 JSON，由该扩展功能自行解析；`key` 须在扩展权限注册表内
- **四类并集兜底**：各策略结果合并使用；**全部为空 = 无数据权限**（默认无）。
- **读写双向**：读时按授权范围过滤（数据访问层）、写时校验（写入口）；**强制叠加租户过滤**，任何策略不得跨租户（由权限计算引擎 `02_04` 实施）。
- **写入方式**：全量覆盖提交（先删后插、单事务）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻）。
- **归档**：不归档（在用授权数据）。
- **迁移**：随 **`platform:tenant` 链**迁移落地（`alembic/versions/platform/tenant/0007_role_tables.py`，本任务新增）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；按字典类型结构化、`config` JSON、只选不编） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
