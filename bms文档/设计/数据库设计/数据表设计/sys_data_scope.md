# sys_data_scope（角色数据权限）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_data_scope

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 07-角色管理（数据权限配置） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》「核心表」节、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「数据权限」节、《[组件设计 · 权限配置](../../组件设计/08_交互类/07_组件设计_权限配置/07_组件设计_权限配置.md)》「数据权限」节、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_platform/models/role.py::SysDataScope`（继承 `BaseModel`） |
| 状态 | 已落库（`platform:tenant` 链 `0007_role_tables` 建表；`config` 列为 JSON 语义，ORM 侧经 `StableJson` 写入规整 / 读回转插入序集合类） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_role](sys_role.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `role_id` | BIGINT | 否 | 建索引 | 角色 ID（逻辑外键 → `sys_role.id`，同库） |
| `data_source_key` | VARCHAR(64) | 否 | — | **数据源标识**（业务码字符串，如 `role` / `org_dept` / `wms_bin`；登记于**统一数据源登记**；2026-10-11 由 `dict_type_id` 改 `dict_key`（02_09）、再由 `dict_key` 改 `data_source_key`（02_10）） |
| `policy_type` | VARCHAR(16) | 否 | — | 策略类型（`select` / `region` / `match` / `extension`） |
| `config` | JSON | 否 | 默认 `[]` | 结构化策略配置（**只选不编**，按 `policy_type` 分结构，写入时后端 schema 强校验） |
| `parent_id` | BIGINT | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） · **系统字段**：上级明细 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_data_scope_role_data_source_policy_deleted_at` | 唯一 | `(role_id, data_source_key, policy_type, deleted_at)` | 一角色对一数据源一策略一条 |
| `idx_sys_data_scope_role_id` | 普通 | `role_id` | 按角色取数据权限 |

- 无物理外键；`role_id` 同库逻辑引用，`data_source_key` 为**数据源标识**（登记于统一数据源登记，不落实体表）。
- **`config` 结构（按 `policy_type`，只选不编）**：
  - `select`：`[{"item_code": "enabled"}, ...]` —— 直接勾选该字典的数据（分页勾选，选中即授权）；`item_code` 承载**字典项 `value`**（条目标识，业务列实际存的值；读入兼容前端历史键 `itemCode`）
  - `region`：`[{"start": "a", "end": "m"}, ...]` —— 开始值 / 结束值（用动态字典组件选择字典数据）
  - `match`：`[{"field": "code", "pattern": "user_*"}, ...]` —— 字段 + 通配符值；`field` 须属该字典**登记项字段白名单**（`allowlist` + 内置 `code` / `name` / `remark`），`pattern` 仅允许 `*` `?` 与中英文 / 数字 / 下划线（越界拒绝，错误码 `30047`）
  - `extension`：`[{"key": "dept_subtree", "params": {...}}, ...]` —— 扩展权限（预设 / 二次开发注册的后端筛选器）+ 参数 JSON，由该扩展功能自行解析；`key` 须在扩展权限注册表内
- **求值口径（`04-4` 收口，2026-10-20）**：`config` 按**数据源维度**产出条件——`select` → `in`（值集合）、`region` → `between`（起止区间），二者**不含字段名**；`match` → `like`（带白名单字段）；`extension` → 扩展求值器直接返回的条件集合。数据源维度条件由消费方按「数据源 → 实体列」声明翻译（未声明即不产生放行），集合值按目标列类型归一；`select` 勾选数超 `[data_scope].options.max_in_values` 时配置期拒绝写入（`30047`，引导改用区域 / 匹配 / 扩展），运行期兜底为永假。口径细节见《[`04-4` 详细设计](../../../项目/07_RBAC基础模块/任务/02_用户与角色/02_用户与角色_04_主体链权限计算引擎/02_用户与角色_04_主体链权限计算引擎_04_四策略口径修正/设计/01_详细设计_04_四策略口径修正.md)》§5。
- **四类并集兜底**：各策略结果合并使用；**全部为空 = 无数据权限**（默认无）。
- **读写双向**：读时按授权范围过滤（数据访问层）、写时校验（写入口）；**强制叠加租户过滤**，任何策略不得跨租户（由权限计算引擎 `02_04` 实施）。
- **写入方式**：全量覆盖提交（先删后插、单事务）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（租户库常驻）。
- **归档**：不归档（在用授权数据）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；按字典类型结构化、`config` JSON、只选不编） | minjian |
| 2026-10-07 | v2 | 归属改 **platform 服务租户库**（`platform:tenant` 链 `0007_role_tables` 建表，随 02_03 落点改定）；`config` 列 JSON 语义不变，ORM 侧改 `StableJson`（写前集合类规整 / 读回转插入序集合类）——集合类直接落裸 `JSON` 会报「非 JSON 序列化」 | minjian |
| 2026-10-11 | v3 | 02_09 口径返工：归属列 `dict_type_id`（BIGINT → 字典类型主键）改 **`dict_key` VARCHAR(64)**（字典标识业务码字符串）；唯一约束列同步、**存量清空不回填**（迁移 `0012_data_scope_dict_key`）；校验改由**字典数据源登记**提供存在性与字段白名单（不再查 `sys_dict_type` / `sys_dict_attr`） | minjian |
| 2026-10-11 | v4 | 系统字段对齐（02_11）：增 `parent_id`（上级明细 ID）；随 `platform:tenant` 链 `0015_system_fields_form_key` | minjian |
| 2026-10-11 | v5 | 02_10 泛化：归属列 `dict_key` → **`data_source_key`**（数据源标识；迁移 `0016_data_source_key`，纯改名）；唯一约束更名 `uq_sys_data_scope_role_data_source_policy_deleted_at` | minjian |
| 2026-10-20 | v6 | `04-4` 口径收口（**无列变更**）：§3 补四策略求值口径（`select` / `region` 按数据源维度产出条件、不含字段名；`match` 带白名单字段；`extension` 直接返回条件集合）、`item_code` 取值语义（字典项 `value`，读入兼容 `itemCode`）与配置期勾选超阈引导（`30047`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
