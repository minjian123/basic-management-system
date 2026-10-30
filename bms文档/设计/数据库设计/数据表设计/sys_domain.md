# sys_domain（业务域声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_domain

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（第九类声明，2026-10-29 重开新增） |
| 上游依据 | [07B 04_02 详细设计](../../../项目/07B_跨产品协同/任务/04_护栏与CI/04_护栏与CI_02_CI跨仓契约校验/设计/01_详细设计_02_CI跨仓契约校验.md#domains)、[07C 03_01 详细设计](../../../项目/07C_产品与服务划分/任务/03_边界与数据/03_边界与数据_01_域级边界护栏/设计/01_详细设计_01_业务域级边界护栏.md#mapping) |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysDomain`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_module](sys_module.md)、[sys_collaboration](sys_collaboration.md) |

- **语义**：一行 = 某产品声明的**一个业务域**及其承载服务（第九类记录）；域布局的权威落点。
- **写入归属**：写方 = platform 服务（注册通道）。读方 = 能力寻址第二段（`domain_service_view()` 按注册表快照重建）、装载校验（`[[domains]]` 的承载服务一致性）。
- **为什么落库**：域布局原先是各仓 `deploy/boundaries/domain_layout.json` **文件**，平台注册通道拿不到产品仓的文件，产品声明的业务域在平台侧无登记（实测 `mdm` 8 条 `org` 域能力被拒）。改为声明后域信息随注册通道到达平台，跨进程与 CI 单仓环境都成立；`domain_layout.json` 降为**本仓清单渲染的生成物**（`ops.check_modules --render-domain-layout`）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `product_key` | VARCHAR(32) | 否 | 与 `domain_key`、`deleted_at` 复合唯一 | 声明方产品键 |
| `domain_key` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一（全局唯一） | 业务域标识（`^[a-z][a-z0-9_]*$`；一经发布不改） |
| `service_key` | VARCHAR(64) | 否 | — | 承载服务键（恒不变；表归属双字段一致性与部署单元反推以它为准） |
| `status` | VARCHAR(16) | 否 | 默认 `placement` | 布局状态（`placement` / `legacy` / `planned` / `retired`） |
| `paths` | TEXT | 是 | — | 域代码路径（JSON 数组，相对仓库根，允许 glob） |
| `public_api` | TEXT | 是 | — | 域内公共出口模块名（JSON 数组，≤1；D2 唯一跨域引用面） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_domain_owner_key_deleted_at` | 唯一 | `(product_key, domain_key, deleted_at)` | 同一产品内业务域不重复声明 |
| `uq_sys_domain_key_deleted_at` | 唯一 | `(domain_key, deleted_at)` | 业务域**全局唯一**（跨产品撞键即拒，见注册期校验） |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级为「产品数 × 每产品域数」，个位数到十位数）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入（产品上报 + 平台自身清单第九类 `[[domains]]`）；**校验**：承载服务须在本清单 `[[services]]` 声明、跨产品 `domain_key` 不得撞键（同键同服务放行并记警示）。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写
