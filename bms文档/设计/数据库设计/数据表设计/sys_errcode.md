# sys_errcode（产品错误码声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_errcode

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | [需求 02-5](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-5)、[需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysErrcode`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_module](sys_module.md)（段位来源） |

- **语义**：一行 = 一个产品错误**码级**声明（第七类记录）；段位来自服务行的 `errcode_segment`，本表存码。
- **写入归属**：写方 = platform 服务（注册通道）。读方 = 错误响应渲染（按视图取 `http_status` 与文案键）、错误码手册导出、契约反向对账。
- **只存声明不存文案**：文案本体在产品语言包，本表只持 `message_key`；缺失时回退 `description` 并告警。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `code` | INT | 否 | 全局唯一（含 `deleted_at`） | 错误码（6 位 = 2 位段 + 4 位序号） |
| `product_key` | VARCHAR(32) | 否 | 索引 | 声明方产品键 |
| `segment` | VARCHAR(2) | 否 | 索引 | 段位（取自服务行 `errcode_segment`，装载/注册期注入） |
| `domain` | VARCHAR(64) | 否 | — | 所属业务域 |
| `http_status` | SMALLINT | 否 | — | 渲染用 HTTP 状态码 |
| `message_key` | VARCHAR(128) | 否 | — | 文案键（`<product>.error.<snake>`） |
| `severity` | VARCHAR(16) | 否 | — | 严重级（`info` / `warning` / `error`） |
| `description` | VARCHAR(255) | 是 | — | 中文描述（文案缺失时的回退与审计读用） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_errcode_code_deleted_at` | 唯一 | `(code, deleted_at)` | 码全局唯一（跨产品撞码由注册校验先拦，DB 兜底） |
| `idx_sys_errcode_product_status` | 普通 | `(product_key, status)` | 按声明方取全量（注册对账 / 手册导出） |
| `idx_sys_errcode_segment` | 普通 | `(segment, status)` | 段位治理查询（段位跨产品复用排查） |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级为「产品数 × 码数」，百级）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入；平台自身码仍以 `ErrorCode` 枚举为源（注册即对账），合并视图在运行期拼接。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写
