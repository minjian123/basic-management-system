# 11 详细设计 · 系统字段 `form_key` 落表（表文件 / 模型 / 迁移）

> 项目骨架 · 02 后端基座 · 子任务 11 · 详细设计 01

[文档首页](../../../../../../文档首页.md) › [02 后端基座](../../02_后端基座.md) › [11 系统字段 form_key 落表](../02_后端基座_11_系统字段form_key落表.md) › 设计　|　[← 任务文档](../02_后端基座_11_系统字段form_key落表.md)

## 1. 目的与口径 <a id="purpose"></a>

按《数据库开发规范》「系统字段（基础 / 表单 / 字典统一口径）」节（§3.1）与需求 [02-57](../../../../需求/02_需求_后端基座.md#r02-57)，把 **`form_key`（表单标识）** 落到全仓数据表：表文件、ORM 模型、Alembic 迁移三处**零漂移**；同时按「缺失即补」把判为**字典表 / 表单表**的表补齐各自系统字段、把**明细表**补齐明细系统字段。`data_source_key` **不落实体表**（归数据源注册表，属任务 `02_10`）。

- **唯一事实源**：表结构（字段 / 类型 / 约束 / 索引）**只在各表文件维护**（`bms文档/设计/数据库设计/数据表设计/{表名}.md`），本设计只写**变更增量**、不复刻字段清单；通用约定见《数据库设计 · 数据规范》。
- **变更传导（强制）**：**先改表文件（追加「变更记录」）→ 改 ORM 模型 → 生成 Alembic 迁移（分链）→ 回写两处状态**。
- **系统字段口径**（§3.1，本节按规范原文执行，不做设计裁剪）：
  - **基础系统字段**（所有表继承）：主表 `id` / `version` / 审计四字段 / `deleted_at`；明细 `id` / `{主表}_id` / `parent_id` / `version`（多列明细加 `sort`）。
  - **表单**（业务表单数据）＝ 基础 ＋ `form_key`（表单标识）/ `code`（表单编号）/ `bill_date`（单据日期）/ `status`（状态）。
  - **字典**（基础数据 / 参考数据）＝ 基础 ＋ `form_key`（表单标识）/ `code`（字典项代码）/ `name`（展示名称）/ `status`（状态）/ `parent_id`（上级字典 ID）。
  - `form_key`：`VARCHAR(64)`、**全局唯一**（`(form_key, deleted_at)`）、**保存后不变**；供通用页面路由 / 查询方案（`field_key = form_key`）/ 用户偏好（`list.{form_key}`）引用；**核心用途＝多表联合（union）取数时的表判别列**——同一 `form_key` 聚集一张表（一个表单 / 字典）的行，联合结果按 `form_key` 区分数据来源。

## 2. 决策确认汇总 <a id="decisions"></a>

| # | 事项 | 结论 | 取舍说明（长期收益 / 迁移成本） |
| --- | --- | --- | --- |
| 1 | `form_key` 落表范围 | **仅「业务实体表」**（字典表 + 表单表两类，有维护界面 / 列表页的业务实体主表）；明细表、多对多关联表、账本 / 日志 / 会话 / 锁 / 发件箱 / 表归属 / 节点映射等基础设施表**不落** | 与「`form_key` 供通用页面路由」语义一致，迁移面最小 |
| 2 | 取值口径 | **独立业务码**（`sys_role`→`role`、`sys_user`→`user`、`sys_tenant`→`tenant`…），全局唯一、保存后不变 | 改表名不影响 `form_key`（守住「保存后不变」）；可支撑通用路由；成本＝多一份清单 |
| 3 | 全局唯一承载 | **每表 `(form_key, deleted_at)` 复合唯一 ＋ 新增 `form_key` 构建期清单**（跨表唯一校验 + 路由依据） | 唯一性可机检、路由有据；成本＝多一份清单与校验 |
| 4 | 既有系统字段对齐 | **缺失即补**（判为字典 / 表单的表缺 `code` / `name` / `status` / `parent_id` / `bill_date` 的一并新增） | 一次对齐到底，口径齐整 |
| 5 | 业务实体表边界 | **严格**：基础数据 / 参考数据语义清晰的独立实体表；元数据表（菜单 / 表单 / 按钮 / 字段）、组合 / 关联 / 授权表、基础设施表、全部 `_i18n` 附表**不落 `form_key`** | 与「字典 / 表单＝业务数据」语义一致 |
| 6 | `parent_id` 覆盖 | **字典表与明细表都要**（非层级字典亦加 `parent_id`；一切带 `{主表}_id` 的明细表含 `_i18n` 均加 `parent_id`） | 通用功能更通用，按需冗余 |
| 7 | 未落库（`planned`）表 | **表文件 + 模型一并补**；迁移不进（`planned` 本就不入链，随其入链时随建表迁移补） | 模型 / 表文件一次对齐 |
| 8 | 产品仓（mdm / biz / cw） | **本次仅 bms 仓**；产品仓随各自独立任务（兼 `02_10` 协同）另行提交 | 跨仓解耦、各仓独立提交 |
| 9 | 迁移组织 | **按链各新增一条**（一条内批改本链全部目标表：加列 + 复合唯一 + 索引） | 与「按服务 × 数据源分链」口径一致、易回滚 |
| 10 | 交付边界 | **含基座校验断言**（`form_key` 存在性 + 清单一致 + 跨表全局唯一），纳入 `preflight --fast` 与 CI | 口径可持续守卫、防回退 |
| 11 | 明细补列范围 | 明细**只补 `parent_id`**（多列明细另补 `sort`），不补 `code` / `name` / `status`（对齐 §3.1.1 明细形态） | 明细与字典口径各归其位 |
| 12 | 既有标识列与 `code` | **只改 DB 列名**为 `code`（表文件 + 迁移改列名）；ORM 用 `mapped_column("code", …)` 映射，**属性名与既有代码 / 契约字段名不动**；列名 ↔ 属性 / 契约字段名映射登记表文件 | 与「字典表格式即 `code` + `name`」一致（DB 口径齐、无双码）；代码零波及、无误伤协议同名参数风险；成本＝6 个属性名 ≠ 列名（表文件登记映射） |

## 3. 影响面与全表判定 <a id="impact"></a>

判定分三类：**① 字典表**（落 `form_key`，补 `code` / `name` / `status` / `parent_id`）；**② 明细表**（不落 `form_key`，仅补 `parent_id`，多列另补 `sort`）；**③ 不处置**（元数据表、组合 / 关联 / 授权表、账本 / 日志 / 会话 / 锁 / 发件箱 / 表归属 / 节点映射等基础设施表）。

### 3.1 bms 后端全表判定 <a id="impact-tables"></a>

> 下表只给**变更增量**；完整字段以各表文件为准。「链」为归属迁移链；`planned` = 未入链（仅补表文件 + 模型，不生成迁移）。

| 表 | 链 | 类别 | `form_key` | 新增列 | 既有列改名 |
| --- | --- | --- | --- | --- | --- |
| `sys_module` | platform:platform | 字典 | `module` | `parent_id` | `module_key` → `code` |
| `sys_product` | platform:platform | 字典 | `product` | `parent_id` | `product_key` → `code` |
| `sys_business` | platform:platform | 字典 | `business` | `parent_id` | — |
| `sys_action` | platform:platform | 字典 | `action` | `parent_id` | — |
| `sys_module_i18n` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_business_i18n` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_action_i18n` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_menu_i18n` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_field` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_button` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_field_i18n` | platform:platform | 明细 | — | `parent_id` | — |
| `sys_menu` | platform:platform | 不处置（元数据树） | — | — | — |
| `sys_form` | platform:platform | 不处置（元数据） | — | — | — |
| `sys_menu_form` | platform:platform | 不处置（关联） | — | — | — |
| `sys_permission` | platform:platform | 不处置（组合） | — | — | — |
| `sys_table_ownership` | platform:platform | 不处置（基础设施） | — | — | — |
| `sys_outbox` / `sys_event_consumed` / `sys_event_dead_letter` | 各链（`*`） | 不处置（账本） | — | — | — |
| `sys_user` | platform:tenant | 字典 | `user` | `parent_id` | `username` → `code` |
| `sys_role` | platform:tenant | 字典 | `role` | `parent_id` | — |
| `sys_config` | platform:tenant | 字典 | `config` | `name`、`status`、`parent_id` | `config_key` → `code` |
| `sys_account_lock` | platform:tenant | 明细 | — | `parent_id` | — |
| `sys_role_permission` | platform:tenant | 明细（授权） | — | `parent_id` | — |
| `sys_role_field` | platform:tenant | 明细（授权） | — | `parent_id` | — |
| `sys_data_scope` | platform:tenant | 明细（授权） | — | `parent_id` | — |
| `sys_user_extension` | platform:tenant | 明细 | — | `parent_id` | — |
| `sys_task_log` | platform:tenant（planned） | 明细 | — | `parent_id` | — |
| `sys_user_preference` | platform:tenant（planned） | 明细 | — | `parent_id` | — |
| `sys_icon_i18n` | platform:tenant（planned） | 明细 | — | `parent_id` | — |
| `sys_task` | platform:tenant（planned） | 字典 | `task` | `code`、`status`、`parent_id` | — |
| `sys_icon` | platform:tenant（planned） | 字典 | `icon` | `parent_id` | — |
| `sys_user_role` | platform:tenant | 不处置（关联） | — | — | — |
| `sys_query_scheme` | platform:tenant | 不处置（配置） | — | — | — |
| `demo` | platform:tenant（planned） | 不处置（示例） | — | — | — |
| `sys_tenant` | tenant:platform | 字典 | `tenant` | `parent_id` | — |
| `sys_tenant_database` | tenant:platform | 明细 | — | `parent_id` | — |
| `sys_user_tenant` | tenant:platform | 不处置（关联） | — | — | — |
| `sys_identity_provider` | identity:tenant | 字典 | `identity_provider` | `parent_id` | `idp_key` → `code` |
| `sys_client` | identity:tenant | 字典 | `client` | `parent_id` | `client_id` → `code` |
| `sys_session` | identity:tenant | 不处置（基础设施） | — | — | — |
| `sys_user_identity` | identity:platform | 不处置（节点映射） | — | — | — |
| `txn_global_branch` | txn:platform | 明细 | — | `parent_id` | — |
| `txn_global_recovery` | txn:platform | 明细 | — | `parent_id` | — |
| `txn_global` | txn:platform | 不处置（账本） | — | — | — |

**无模型、无表文件的登记表**（`sys_tenant_quota` / `sys_tenant_module` / `sys_form_layout` / `sys_field_ext` / `sys_admin` / `sys_ai_provider`）本任务**不处置**（无表文件与模型可改；随各自阶段建表时按本口径落 `form_key`）。

**判定说明（边界项）**：

- `sys_config`（系统参数）：规范 §3.1.3 明确「字典＝基础数据 / 参考数据」，参数属可维护的基础配置数据，按字典表处置（补 `name` / `status` / `parent_id`）。
- `sys_task`（定时任务定义）：任务清单属参考数据、有维护界面，按字典表处置。
- `sys_notification`（站内信，`planned`）：属**业务数据**（非基础 / 参考数据），**不判为字典表**，本任务不处置。
- `sys_user_identity`（SSO 身份映射）：属节点映射，不落 `form_key`；非「带 `{主表}_id` 的明细表」（无归属主表语义），本任务不补 `parent_id`。

### 3.2 表单表 <a id="impact-form"></a>

bms 后端**无「业务表单数据」表**（业务表单在产品仓：biz `pur_` / `pay_` / `sale_` / `wh_`、mdm 等），故 §3.1.2 **表单 4 项**（`form_key` / `code` / `bill_date` / `status`）在 bms 仓**本次无落地对象**；口径随产品仓任务（本任务范围外）执行。本任务在 bms 仓实际落地的是 **§3.1.3 字典 5 项** 与 **§3.1.1 明细补 `parent_id`**。

## 4. `form_key` 构建期清单 <a id="catalog"></a>

- **新增模块** `bms/backend/libs/bms_core/src/bms_core/registry/`（`__init__.py` + `forms.py`）：
  - `FormRecord`（不可变值对象）：`form_key`（业务码，`^[a-z][a-z0-9_]*$`）、`table`（物理表名）、`kind`（`dict` / `form`）、`name`（名称）、`status`（`enabled` / `disabled`）、`data_source_key`（可空；供 `02_10` 数据源注册归并，暂留空）。
  - `FORM_CATALOG`：**bms 侧构建期清单**（本节 §3.1 全部字典表，及其后 bms 表单表的登记位）。
  - `FormCatalog`（运行期只读）+ `merge_form_records()`（产品在构建期注入自身登记项，口径同服务目录 `ModuleRegistry` / 字典登记 `DictRegistry`）。
  - `FormCatalog.validate()`：`form_key` 格式与**跨表全局唯一**；`table` / `name` / `kind` 合法；`table` 在 `TABLE_OWNERSHIP` 内。
- **与既有登记的关系**：`form_key` 清单是**界面标识 → 表**的登记；`02_10` 的 `DataSourceRegistry` 是**数据源 → 数据出口**的登记；`form_key → data_source_key`（多对一）由二者在构建期合并解析（`02_13` 消费）。本任务只落 `form_key` 清单骨架，`data_source_key` 字段留空待 `02_10` 填。
- **`form_key` 取值口径**：**业务码字符串**（表名单词化，去前缀），如 `sys_role`→`role`、`sys_user`→`user`、`sys_tenant`→`tenant`、`sys_module`→`module`、`sys_identity_provider`→`identity_provider`；跨表 / 跨仓唯一由清单校验保证。

## 5. 表文件变更口径 <a id="table-files"></a>

每张受影响表文件改三处：

1. **`## 2. 字段` 节**：按 §3.1.2（字典 5 项）/ §3.1.1（明细）在合适位置补列行，说明列标注系统字段（`· **系统字段**：表单标识 / 上级字典 ID / …`），既有列改名者同步改列名与说明（并注明「列名 ↔ 契约字段名映射」）。
2. **`## 3. 索引与约束` 节**：补 `uq_{表}_form_key_deleted_at`（字典表）；`parent_id` 索引按「层级必备、非层级不建」落列（见 §7.3）。
3. **`## 5. 变更记录` 节**：追加一行（日期 / 版本 / 变更 / 作者），与迁移编号一一对应。

**表文件 ↔ 模型 ↔ 迁移零漂移**：由基座校验断言（§8）。

## 6. ORM 模型变更口径 <a id="models"></a>

- **字典表**：类内增 `form_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="表单标识（全局唯一；保存后不变）")`；`__table_args__` 加 `UniqueConstraint("form_key", "deleted_at", name="uq_{表}_form_key_deleted_at")`；按 §3.1 补齐既有列（缺 `name` / `status` 者新增）。**既有标识列改名只改 DB 列名**——`mapped_column("code", String(...), …)` 映射（**属性名与既有代码 / 契约字段名保持不动**），唯一约束名同步改为 `uq_{表}_code_deleted_at`，列名 ↔ 属性名映射登记表文件。
- **明细表**：类内增 `parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="上级 ID（自引用同表 id；顶层 NULL）")`；多列明细另补 `sort`。
- **`form_key` 取值落地**：因 `form_key` 为**每表常量**（同一表所有行同值），模型侧以 `default="<form_key>"`（或 `server_default`）声明；**写入路径不改业务代码**（列值恒定，由模型缺省提供）。
- **不落 `BaseModel` 基类**：`form_key` 仅在字典 / 表单具体模型声明（§3.1.1 基础字段不含 `form_key`），**不动** `bms_core/models/base.py`。

## 7. 迁移设计 <a id="migration"></a>

### 7.1 迁移链与编号 <a id="migration-chains"></a>

**按链各新增一条**，一条内批改本链全部目标表：

| 链 | 新迁移编号 / 文件 | 目标表 |
| --- | --- | --- |
| `platform:platform` | `0010_system_fields_form_key` | `sys_module` / `sys_product` / `sys_business` / `sys_action`（字典）+ 各自 `_i18n`、`sys_menu_i18n`、`sys_field`、`sys_button`、`sys_field_i18n`（明细） |
| `platform:tenant` | `0015_system_fields_form_key` | `sys_user` / `sys_role` / `sys_config`（字典）+ `sys_account_lock` / `sys_role_permission` / `sys_role_field` / `sys_data_scope` / `sys_user_extension`（明细） |
| `tenant:platform` | `0007_system_fields_form_key` | `sys_tenant`（字典）+ `sys_tenant_database`（明细） |
| `identity:tenant` | `0006_system_fields_form_key` | `sys_identity_provider` / `sys_client`（字典） |
| `identity:platform` | `0004_system_fields_form_key` | （本任务无目标表 → **不新增**；`sys_user_identity` 不处置） |
| `txn:platform` | `0003_system_fields_form_key` | `txn_global_branch` / `txn_global_recovery`（明细） |

> `planned` 表（`sys_task` / `sys_task_log` / `sys_user_preference` / `sys_icon` / `sys_icon_i18n`）**不入链**，本次只补表文件与模型；其迁移随各自入链时随建表迁移补。

### 7.2 加列与改名写法（三库兼容） <a id="migration-ddl"></a>

- **加列**：`op.add_column(...)` + `server_default`（`form_key` 常量缺省；`parent_id` 可空无缺省），存量行按缺省回填；随后 `batch_alter_table` 移除 `server_default`（保持模型与库一致）。
- **改名**：`batch_alter_table(...).alter_column("module_key", new_column_name="code", ...)`（三库兼容；唯一约束随列重建，名称同步为 `uq_{表}_code_deleted_at`）。**先数据后改型**口径不涉及（本次改名不改类型）。
- **复合唯一**：`batch_alter_table(...)` 内 `create_unique_constraint("uq_{表}_form_key_deleted_at", ["form_key", "deleted_at"])`；SQLite 经 `batch_alter_table` 重建表兼容。
- **索引**：`op.create_index("idx_{表}_parent_id", ...)`（层级字典 / 层级明细）。
- **`downgrade`**：逐项反向（删列 / 改回列名 / 删约束 / 删索引）；改回的旧列名按原值语义（`code` → `module_key` 等）。

### 7.3 索引口径 <a id="migration-index"></a>

- **`parent_id` 索引**：**层级字典**（`sys_menu` 已备；本次无新层级字典）与**层级明细**建索引；**非层级表**（`sys_role` / `sys_user` / `sys_tenant` / `sys_business` / `sys_action` / `sys_module` / `sys_product` / `sys_config` 等）`parent_id` 恒为 `NULL`、**不建索引**（守「无冗余索引 + 每表 ≤ 5」）。该项为设计口径（§3.1.3 字面为「建索引」，此处按「层级才建」执行，随设计评审确认）。
- **索引计数**：每表新增 1 个唯一约束（含索引）＋ 至多 1 个 `parent_id` 索引；新增后逐表核对 ≤ 5（现有超出者按「去掉冗余」处理并登记）。

## 8. 基座校验扩展 <a id="guards"></a>

- **`bms/scripts/tools/base-check/check-system-fields.py`（新）**：断言 ① 每张「字典表」表文件含 `form_key` 列行、且值 ∈ `FORM_CATALOG`；② `FORM_CATALOG` 与表文件**双向一致**（清单项 ↔ 表文件，无缺漏 / 无多余）；③ `form_key` **跨表全局唯一**；④ 每张「明细表」表文件含 `parent_id` 行。纳入 `preflight --fast` 与 CI `base-integrity`。
- **`bms/backend/ops/check_tables.py` 扩展**：断言「判为字典 / 明细的模型，其 `__table_args__` / 列含 `form_key` / `parent_id`」（模型侧存在性）；纳入后端 job。
- **`FORM_CATALOG.validate()`**：启动期 / 离线自检（格式 + 唯一 + 表归属）。
- **`check-base.py`**：不变（继续守表文件 ↔ 总览登记 ↔ 目录一致性）。

## 9. 交付物清单 <a id="deliverables"></a>

```
bms/backend/libs/bms_core/src/bms_core/registry/
├─ __init__.py               # 导出 FormRecord / FORM_CATALOG / FormCatalog / merge_form_records
└─ forms.py                  # 新增：form_key 构建期清单 + 记录 + 校验
bms/backend/services/platform/src/bms_platform/models/
├─ catalog.py                # sys_module / sys_product：+form_key +parent_id；module_key/product_key → code
├─ menu.py                   # sys_business / sys_action：+form_key +parent_id；sys_menu_i18n/sys_field/sys_button/sys_field_i18n：+parent_id
├─ role.py                   # sys_role：+form_key +parent_id；sys_role_permission/sys_role_field/sys_data_scope：+parent_id
├─ user.py                   # sys_user：+form_key +parent_id、username→code；sys_account_lock：+parent_id
├─ system.py                 # sys_task/sys_icon：+form_key（+code/status/parent_id）；sys_task_log/sys_user_preference/sys_icon_i18n/sys_user_extension：+parent_id
bms/backend/services/tenant/src/bms_tenant/models/
├─ tenant.py                 # sys_tenant：+form_key +parent_id
└─ tenant_database.py        # sys_tenant_database：+parent_id
bms/backend/services/identity/src/bms_identity/models/
├─ identity_provider.py      # sys_identity_provider：+form_key +parent_id、idp_key→code
└─ client.py                 # sys_client：+form_key +parent_id、client_id→code
bms/backend/services/txn/src/bms_txn/models/ledger.py        # txn_global_branch / txn_global_recovery：+parent_id
bms/backend/alembic/versions/
├─ platform/platform/0010_system_fields_form_key.py
├─ platform/tenant/0015_system_fields_form_key.py
├─ tenant/platform/0007_system_fields_form_key.py
├─ identity/tenant/0006_system_fields_form_key.py
└─ txn/platform/0003_system_fields_form_key.py
bms/scripts/tools/base-check/check-system-fields.py          # 新增：表文件 ↔ 清单 ↔ 唯一性 断言
bms/backend/ops/check_tables.py                              # 扩展：模型侧 form_key / parent_id 存在性
bms/bms文档/设计/数据库设计/数据表设计/*.md                    # 逐表补列 + 变更记录
```

## 10. 测试设计与验收映射 <a id="accept"></a>

| 验收项 | 测试 / 校验 |
| --- | --- |
| 字典表 `form_key` / `code` / `name` / `status` / `parent_id` 齐备 | 表文件断言（`check-system-fields`）+ 定向用例 |
| 明细表 `parent_id` 齐备 | 同上 |
| 既有标识列改名为 `code`，契约字段名不变 | 契约快照零变化（`ops.contract_snapshot` / `contract_gate`）+ 前端 `api-types` 零漂移 |
| 迁移可跑、模型零漂移 | 各链 `alembic -n alembic:{链} upgrade head`（SQLite 开发库 + 三库按需）+ 逐链 autogenerate 比对 |
| `form_key` 全局唯一、清单一致 | `FormCatalog.validate()` + `check-system-fields` |
| 门禁全绿 | `preflight --fast`（含 `check-base` / `check-backend-base` / `check-service-boundaries` / `check-system-fields`） |

- 用例**先登记 Kiwi TCMS 取编号**再编码；界面无关（纯数据底座）→ 测试记录「原型对照结论」节写「不适用」+ 理由。
- 定向用例只跑受变更影响部分（迁移 / 模型 / 清单 / 校验脚本）。

## 11. 登记回写与跨仓 <a id="registry-writeback"></a>

- **回写**：各表文件（含变更记录）、`设计/数据库设计/01_数据库设计_总览.md`「已设计数据表登记」（状态不变，结构变更不改状态）、本任务 `实施/`、`测试/` 记录、计划表（进度唯一落点）。
- **规范登记**：《命名规范》「标识用 `key`、代码用 `code`」条需登记**例外**——凡规范 §3.1.3 字典表，其「代码」列统一 `code`（既有 `xxx_key` 标识列按字典口径改名为 `code`；非字典表的标识仍用 `key`）。
- **跨仓**：mdm（`org_dept` / `org_post` / `org_role_dept` / `org_role_post` / `org_user_dept` / `org_user_post`）、biz / cw 的表文件与模型随**各自产品仓任务**按本口径对齐，各仓独立提交（本任务范围外）。

## 12. 风险与遗留 <a id="risk"></a>

- **常量列的语义（设计说明）**：`form_key` 为**每表常量**，其**核心用途＝多表联合（union）取数的表判别列**（同表所有行同值，联合结果按它区分来源），故「同表多行同值」是**设计意图**而非缺陷；`(form_key, deleted_at)` 复合唯一在 MySQL / PostgreSQL 下（`NULL` 互异）对同表多行不产生额外约束力，「全局唯一」由 `FORM_CATALOG` 跨表校验承担。本任务按规范原文落地并登记说明，**不在应用层按方言各有实现**（沿用 §4「达梦 `NULL` 语义差异归口方言特性文档」）。
- **达梦复合唯一差异**：`(form_key, deleted_at)` 中 `NULL` 语义差异（已实测，归口 `设计/数据库设计/方言特性/03_DM8.md`）；本任务沿用既有口径，真库实测随部署窗口回写。
- **列改名**：涉及 `sys_module` / `sys_product` / `sys_user` / `sys_config` / `sys_identity_provider` / `sys_client` 六张表；**只改 DB 列名**（表文件 + 迁移），ORM 属性与全仓代码 / 契约字段名**不动**（`mapped_column("code", …)` 映射），故无代码回归面；须在表文件登记「列名 ↔ 属性 / 契约字段名」映射，防止后续读表文件误判。
- **`parent_id` 冗余**：非层级字典 / 明细的 `parent_id` 为按需冗余列（依 q6 决策），长期恒 `NULL`；已在判定表逐表登记，后续如判定无必要可单独立项移除。
- **产品仓待办**：mdm / biz / cw 的表文件与模型尚未按本口径对齐（本次范围外），需在产品仓任务登记，防遗漏。

> 本文档为需求评审后的详细设计稿 · 与《文档生成规范》配套
