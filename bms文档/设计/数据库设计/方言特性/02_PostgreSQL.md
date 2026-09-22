# 方言特性 · PostgreSQL 16

> BMS · 数据库设计 · 方言特性 · 库 02（PostgreSQL 16）

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [数据规范](../02_数据库设计_数据规范.md) › PostgreSQL 16　|　[MySQL](01_MySQL.md) · [达梦 DM8](03_DM8.md)

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 库与版本 | PostgreSQL 16（mjbk 常驻，开发联调与 CI 三库测试共用） |
| 应用侧接入 | 驱动 `psycopg`（异步方言 `postgresql+psycopg`） |
| 字符集 | UTF8（库默认） |
| 上游依据 | [数据规范](../02_数据库设计_数据规范.md)、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》「数据规范」「迁移策略」节、《[架构设计 · 数据访问与分片](../../架构设计/13_架构设计_子系统_数据访问与分片.md)》「多数据源管理」「查询规范」节 |
| 结论口径 | 本文每条结论标注 **实测**（已真库验证）或 **待验**（尚未真库验证，实施前须实测并回写） |
| 状态 | 已实测（2026-09-22 三库迁移演练，见第 8 节） |

## 2. 类型映射 <a id="type"></a>

| 逻辑类型（设计侧写法） | PostgreSQL 16 落点 | 结论 |
| --- | --- | --- |
| `BIGINT`（主键 / 外键） | BIGINT | 实测（DDL 编译 + 真库建表） |
| `DATETIME`（各 `*_at`） | TIMESTAMP WITHOUT TIME ZONE | 实测（UTC naive 存储口径一致） |
| `INT` / `SMALLINT` | INTEGER / SMALLINT | 实测 |
| `VARCHAR(n)` | VARCHAR(n) | 实测 |
| `TEXT` | TEXT | 实测 |
| `BOOLEAN` | BOOLEAN（原生布尔） | 实测 |
| `JSON`（多值字段） | JSON（**非** JSONB） | 实测（真库建表通过；JSON 值读写 **待验**） |
| `DECIMAL(20,4)`（金额） | NUMERIC(20,4) | 实测（DDL 编译） |

- 禁用方言专用类型：`SERIAL` / `BIGSERIAL`（主键为应用侧雪花 ID 的 BIGINT）、`TIMESTAMPTZ`、`BYTEA` 直写。
- 需按时间排序 / 比较的列统一 naive TIMESTAMP（UTC），不使用 `WITH TIME ZONE`。

## 3. DDL 与对象差异 <a id="ddl"></a>

| 事项 | PostgreSQL 16 行为 | 对平台的影响 |
| --- | --- | --- |
| 库与模式层级 | 库内可有多个 schema（默认 `public`）；`CREATE DATABASE` **不能在事务内**执行 | 建删库经 `ops/db_admin.py`（独立连接、非事务路径，实测）；平台不使用多 schema |
| 表 / 列注释 | 独立语句 `COMMENT ON TABLE/COLUMN` | SQLAlchemy 迁移自动生成注释语句 |
| 幂等建表 | 支持 `CREATE TABLE IF NOT EXISTS` | 与其余库形态一致 |
| DDL 事务性 | **事务性**（DDL 可回滚） | 迁移失败可整体回滚（与 MySQL 的隐式提交不同），迁移仍需幂等 |
| 索引重命名 | `ALTER INDEX old RENAME TO new`（**无** `RENAME INDEX`） | 迁移脚本改索引名须按方言分流（或建新删旧） |
| 索引并发创建 | `CREATE INDEX CONCURRENTLY` 不可在事务内 | 平台迁移不使用（**待验**：大表在线加索引场景） |

- 迁移、建删库与批量迁移命令口径见《[数据库开发规范](../../../规范/数据库开发规范.md)》「迁移与建表口径」节。

## 4. 空值与排序 <a id="null"></a>

| 事项 | PostgreSQL 16 行为 | 平台口径 |
| --- | --- | --- |
| 默认 NULL 位次 | NULL 视作**最大**（升序在后、降序在前）——与 MySQL **相反** | 不依赖库默认：统一「NULL 恒排末位」，由 ORDER BY 内 `列 IS NULL` 排序键实现（四库行为一致） |
| `NULLS FIRST/LAST` 语法 | 支持 | 仍**禁止**写入 SQL（其他库不支持，见 [MySQL](01_MySQL.md) 第 4 节） |
| 唯一索引与多 NULL | 唯一索引允许多个 NULL | 复合唯一 `(唯一字段, deleted_at)` 未删行不冲突（实测通过） |
| 部分唯一索引 | 支持 `CREATE UNIQUE INDEX … WHERE deleted_at IS NULL` | 可选优化（仅未删行唯一索引更小）；平台基础口径仍用复合唯一，启用需逐表评估（**待验**） |
| 空串与 NULL | `''` 与 NULL 可区分 | 不用 NULL 表达空串 |

## 5. 标识符与模式 <a id="identifier"></a>

- 未加引号的标识符折叠为**小写**；须保留大小写时用双引号（平台统一小写，不用引号）。
- **索引与约束名在库内唯一**（不限于表内）——故平台索引命名必须含表名（`idx_{表}_{列}`），否则同名列索引跨表冲突（实测编译期暴露）。
- 标识符长度上限 63 字节；超出需截短命名（平台命名均在限内）。

## 6. 索引与约束 <a id="index"></a>

- 索引名库内唯一（见第 5 节）；每表索引 ≤ 5 个（平台强制）。
- 唯一索引允许重复 NULL；「仅未删行唯一」除复合唯一外可用部分唯一索引优化（第 4 节，**待验**）。
- 无物理外键；逻辑外键由应用侧维护（与其余库一致）。
- 默认使用 B-tree 索引；表达式 / 函数索引仅在实测有收益时使用（**待验**）。

## 7. 事务与连接 <a id="tx"></a>

| 事项 | PostgreSQL 16 行为 / 平台做法 | 结论 |
| --- | --- | --- |
| 默认隔离级别 | READ COMMITTED | 实测（默认值）；业务不依赖隔离级别差异 |
| DDL 与事务 | 事务性 DDL（可回滚） | 迁移失败可整体回滚，版本行由 Alembic 事务写入（实测） |
| 连接池 | `pool_size` / `max_overflow` / `pool_timeout` / `pool_recycle` / `connect_timeout` 取配置 `[database.*.pool]` | 实测（配置项生效） |
| 慢查询日志 | 开启（`log_min_duration_statement`，开发联调） | 实测（已配置） |
| 主从（只读副本） | 支持；读写绑定见《[架构设计 · 数据访问与分片](../../架构设计/13_架构设计_子系统_数据访问与分片.md)》「读写分离」节 | 未启用（**待验**） |

- 应用侧经引擎注册表与会话入口取连接（不自行 `create_engine`）；异步会话不得跨请求 / 跨事件循环复用。

## 8. 实测记录 <a id="measured"></a>

| 日期 | 项 | 结论 | 证据 |
| --- | --- | --- | --- |
| 2026-09-22 | 平台链迁移（临时库 `bms_migrcheck`） | 建库 → 迁移 → 校验（`0001_sys_tenant_module`，表 4/4）→ 清理，通过 | 01_04 测试记录「三库真库迁移演练」 |
| 2026-09-22 | 租户链迁移（临时库 `bms_migrcheck_tenant`） | 建库 → 迁移 → 校验（`0001_dict_query_scheme`，表 8/8）→ 清理，通过 | 同上 |
| 2026-09-22 | 类型映射与 DDL 编译 | 四方言 DDL 编译断言通过（含原生 `BOOLEAN` 与 `JSON` 列） | `tests/models/test_type_mapping.py` |
| 待验 | 部分唯一索引优化、`CREATE INDEX CONCURRENTLY` 在线加索引、JSON 值读写与检索、主从只读路由 | — | — |

> 数据库设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「表与字段口径」至「数据库设计文档体系」各节配套
