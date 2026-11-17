# sys_help_package（产品帮助包装载登记）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_package

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（产品帮助包版本 / 校验和 / 条数 / 装载状态） |
| 上游依据 | [需求 09-2](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-2)、《[概要设计 · 帮助中心](../../概要设计/17_概要设计_帮助中心.md)》§4、《[帮助包规范](../../../规范/帮助包规范.md)》§3 / §7 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpPackage`（继承 `BaseModel`） |
| 状态 | 已设计（随 08_03 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_article](sys_help_article.md)（来源文章）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 装载记录标识 |
| `product_key` | VARCHAR(64) | 否 | — | 产品键（`platform` / `biz` / `mdm` / `cw`…） |
| `package_version` | VARCHAR(32) | 否 | — | 语义化版本 `X.Y.Z` |
| `schema_version` | INT | 否 | 默认 1 | 包格式版本 |
| `checksum` | VARCHAR(80) | 否 | — | 装载时校验通过的 `sha256:<64 位十六进制>` |
| `article_count` | INT | 否 | 默认 0 | 该版本清单内文章总数（含 `offline` 与宽松模式跳过的篇） |
| `generated_at` | DATETIME | 是 | — | 清单 `generated_at`（UTC；仅登记） |
| `loaded_at` | DATETIME | 否 | — | 本次装载时间（UTC） |
| `status` | VARCHAR(16) | 否 | 默认 `loaded` | 状态：`loaded` 当前版本 / `outdated` 已被更高版本取代 / `unloaded` 已卸载 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **一行一个版本**：同一产品可有多个历史版本行；同一时刻最多一行 `loaded`，其余为 `outdated` / `unloaded`。
- **幂等判定**：`(product_key, package_version)` + `checksum` 相同且 `status=loaded` → 重复装载零变更；同版本不同 `checksum` 拒收（版本不可变）。
- **卸载**：按 `product_key` 把该产品全部包行置 `unloaded`，并把该产品包来源文章置 `offline`；租户自建（`source=tenant`）不受影响。
- **条数口径**：`article_count` 记录清单内文章总数，不随后续文章状态变化回写；用于「装载了哪些内容」的审计对账。
- **不物理删**：历史版本行保留，卸载只改状态。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_help_package_product_version_deleted_at` | 唯一 | `(product_key, package_version, deleted_at)` | 一个产品一个版本一行（软删除后释放） |
| `idx_sys_help_package_product_status` | 普通 | `(product_key, status)` | 按产品取当前 / 历史 / 已卸载版本 |

- 公共 `deleted_at` 索引由元数据命名约定生成；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`sys_help_article.package_id` 指向本表 `id`（同库逻辑外键）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；包版本量级小）。
- **归档**：不归档；历史版本行随文章长期保留，用于追溯。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建（08_03 产品帮助包装载注册）：包版本登记，幂等 / 升级 / 卸载状态载体 | minjian |
