# sys_scope_resource_type（作用域资源类型登记）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_scope_resource_type

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`、业务域 `platform_registry`、库类别 `platform`） |
| 覆盖模块 | 07D-产品租户与安全接入（01 通用三级作用域） |
| 上游依据 | 《[架构设计 · 产品租户与安全接入](../../架构设计/41_架构设计_子系统_产品租户与安全接入.md)》「通用三级作用域」节、[需求 01-1](../../../项目/07D_产品租户与安全接入/需求/01_需求_通用三级作用域.md#r01-1)、[01-1 详细设计 §3.2](../../../项目/07D_产品租户与安全接入/任务/01_通用三级作用域/设计/01_详细设计_01_通用三级作用域.md#table) |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysScopeResourceType`（继承 `BaseModel`，与九类声明表同族） |
| 状态 | 待落库（随 07D `01-1` 进 `platform:platform` 链，启动期自动建表） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)、[sys_module](sys_module.md)、[sys_product](sys_product.md)、[sys_domain](sys_domain.md) |

- **语义**：产品声明的**作用域资源类型**（三级作用域的第三级约束）——一类型一行，`{module_key}.{kind}` 全局唯一。
- **写入归属**：声明态（`status` / 命名规则 / 保留期 / 声明版本）由**产品声明注册通道**写入（第十类记录 `[[resource_types]]`）；运营态（`admin_status` / `disabled_at` / `disabled_by`）**只由平台运营期停用接口写入**，声明重放不回写该组列。
- **只读投影口径**：与九类声明一致——`content_hash` 未变不写、本次全量未声明即置 `status = retired`（不删行）、运行期平台不手写产品记录。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表只列业务字段。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `resource_type_key` | VARCHAR(128) | 否 | 与 `deleted_at` 复合唯一（`uq_sys_scope_resource_type_key_deleted_at`） | 类型标识 `{module_key}.{kind}`（如 `msg.topic`）；`module_key` / `kind` 由本列前缀派生，**不另落列**（避免两处事实源） |
| `name` | VARCHAR(64) | 否 | — | 显示名（人读，如「主题」） |
| `name_pattern` | VARCHAR(128) | 否 | — | `resource_key` 取值正则（装载期校验：可编译、长度受限、禁嵌套量词） |
| `max_length` | INT | 否 | 默认 64 | `resource_key` 最大长度（1~255；与正则双重约束） |
| `retention_days` | INT | 否 | 默认 0 | 保留期（天；0 = 永久保留）；租户删除后按此归档或清理（`01_04` 消费） |
| `removal_policy` | VARCHAR(16) | 否 | 默认 `archive` | 到期处置：`archive` 归档 / `purge` 物理删除 |
| `product_key` | VARCHAR(32) | 否 | — | 声明方产品键（跨库逻辑外键 → `sys_product.product_key`，只持值） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | **声明态**：`enabled` / `disabled` / `retired`（登记即定；退役由未声明表达） |
| `admin_status` | VARCHAR(16) | 否 | 默认 `enabled` | **运营态**：`enabled` / `disabled`（运营期停用写本列；声明重放不写） |
| `disabled_at` | DATETIME | 是 | — | 最近运营期停用时间（UTC） |
| `disabled_by` | DECIMAL(38,0) | 是 | — | 停用操作人（平台租户 `sys_user.id`） |
| `declaration_version` | INT | 否 | 默认 1 | 声明版本（声明要素变更 +1，注册通道派生，不手写；**与乐观锁 `version` 语义不同**） |
| `content_hash` | CHAR(64) | 否 | — | 声明要素稳定哈希（未变不写；`admin_status` 等运营态列不进要素） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |

- **有效态**：`status = enabled` 且 `admin_status = enabled` 才视为启用；两者分离是为了让「运营期紧急停用」不被下一次声明重放冲掉。
- 注册表类表不落 `form_key`（非业务单据表，与 `sys_errcode` / `sys_seed` 同口径）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_scope_resource_type_key_deleted_at` | 唯一 | `(resource_type_key, deleted_at)` | 类型标识全局唯一（软删除后可重挂）；同时承担按类型取行 |

- 无物理外键；`product_key` 指向 `sys_product.product_key`（同库逻辑外键，只持值）。
- 不建 `module_key` 索引：该段由 `resource_type_key` 前缀派生，运营视图按内存视图分组（行数受产品类型数约束）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（注册契约元数据；退役保留登记、不物理删除）。
- **建表**：随 **`platform:platform` 链**幂等建表落地（表集经表归属登记派生；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-07 | v1 | 新建表结构（07D `01_01`：作用域资源类型登记；声明态与运营态分列、声明版本与内容指纹；PLANNED） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套
