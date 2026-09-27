# sys_config（系统参数）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_config

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 11-系统参数 |
| 上游依据 | [需求 03-8](../../../项目/06_认证与安全/需求/03_需求_验证码与账号治理.md#r03-8)、《[概要设计 · 系统参数](../../概要设计/10_概要设计_系统参数.md)》「核心表」节、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》§4.1 |
| ORM 模型 | `bms_core/config/models.py::SysConfig`（继承 `BaseModel`；登记于 `db/migration.py::COMMON_MODEL_MODULES`） |
| 状态 | 已设计（随 `03_08` 落 `platform:tenant` 链迁移 `0002_sys_config`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 10-系统参数](../../概要设计/10_概要设计_系统参数.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `config_key` | VARCHAR(128) | 否 | 与 `deleted_at` 复合唯一 | 参数键（点分小写，如 `captcha.scene.login.required`；`key` 为 MySQL 保留字故用 `config_key`） |
| `value` | TEXT | 否 | 默认空串 | 参数值（标量 / 布尔 / JSON 字符串统一按文本承载，由消费方按类型解析；仅应用侧读写、无库内 JSON 检索需求，取 `TEXT` 最大跨方言安全） |
| `remark` | VARCHAR(255) | 是 | — | 备注（参数用途说明） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_config_config_key_deleted_at` | 唯一 | `(config_key, deleted_at)` | 参数键唯一（软删除后可复用） |

- 无物理外键；`config_key` 为平台统一命名空间键（消费方自定义前缀，如 `captcha.` / `password.` / `session.`）。
- 无独立业务索引（查询按 `config_key` 唯一键命中或 `IN` 子集）；公共软删除索引 `idx_sys_config_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在本表重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（参数为小型热配置数据）。
- **归档**：不归档（在用配置数据）。
- **迁移**：随 **`platform:tenant` 链** Alembic 迁移落地（`alembic/versions/platform/tenant/0002_sys_config.py`）；命令 `alembic -n alembic:platform:tenant upgrade head`；SQLite 开发库由启动期自动建表覆盖。
- **缓存**：`bms:{tenant}:config:{config_key}`（短 TTL + 随机偏移；版本键 `bms:{tenant}:config:version`），变更后删 key 并递增版本号（先写库后删缓存）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（platform 服务租户库；随 `03_08` 落 `platform:tenant` 链迁移 `0002_sys_config`） | minjian |
