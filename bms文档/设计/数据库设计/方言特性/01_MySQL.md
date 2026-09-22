# 方言特性 · MySQL 8

> BMS · 数据库设计 · 方言特性 · 库 01（MySQL 8）

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [数据规范](../02_数据库设计_数据规范.md) › MySQL 8　|　[PostgreSQL](02_PostgreSQL.md) · [达梦 DM8](03_DM8.md)

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 库与版本 | MySQL 8（mjbk 常驻，开发联调与 CI 三库测试共用） |
| 应用侧接入 | 驱动 `aiomysql`（异步方言 `mysql+aiomysql`）；连接串形如 `mysql+aiomysql://bms_dev@<host>:3306/{database}` |
| 字符集 | `utf8mb4`（排序规则按库默认） |
| 上游依据 | [数据规范](../02_数据库设计_数据规范.md)、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》「数据规范」「迁移策略」节、《[架构设计 · 数据访问与分片](../../架构设计/13_架构设计_子系统_数据访问与分片.md)》「多数据源管理」「查询规范」节 |
| 结论口径 | 本文每条结论标注 **实测**（已真库验证）或 **待验**（尚未真库验证，实施前须实测并回写） |
| 状态 | 已实测（2026-09-22 三库迁移演练，见第 8 节） |

## 2. 类型映射 <a id="type"></a>

| 逻辑类型（设计侧写法） | MySQL 8 落点 | 结论 |
| --- | --- | --- |
| `BIGINT`（主键 / 外键） | BIGINT | 实测（DDL 编译 + 真库建表） |
| `DATETIME`（各 `*_at`） | DATETIME | 实测 |
| `INT` / `SMALLINT` | INTEGER / SMALLINT | 实测 |
| `VARCHAR(n)` | VARCHAR(n)（长度以字符计） | 实测 |
| `TEXT` | TEXT | 实测 |
| `BOOLEAN` | BOOL（TINYINT(1)） | 实测（DDL 编译） |
| `JSON`（多值字段） | JSON | 实测（`sys_dict_item.attr_json` / `sys_query_scheme.*` 真库建表通过；JSON 值写入读回一致） |
| `DECIMAL(20,4)`（金额） | DECIMAL(20,4) | 实测（DDL 编译） |

- 禁用方言专用类型：`ENUM`、`SET`、`TINYINT` 直写（布尔经 `BOOLEAN` 逻辑类型表达）、`UNSIGNED`。
- 时间字段为 naive DATETIME（UTC），**不使用** `TIMESTAMP`（隐式时区转换）与 `ON UPDATE CURRENT_TIMESTAMP`。

## 3. DDL 与对象差异 <a id="ddl"></a>

| 事项 | MySQL 8 行为 | 对平台的影响 |
| --- | --- | --- |
| 库与模式层级 | 库即模式（无独立 schema 层） | 库级隔离即 `CREATE DATABASE` / `DROP DATABASE`（经 `ops/db_admin.py`，实测） |
| 表 / 列注释 | 内联 `COMMENT '…'` | 建表语句自带注释，无需额外语句 |
| 幂等建表 | 支持 `CREATE TABLE IF NOT EXISTS` | SQLite 开发库自动建表走同一形态 |
| DDL 事务性 | **隐式提交**（DDL 不可回滚） | 迁移中途失败需人工核对后重跑（与 PostgreSQL 不同，见 [PostgreSQL](02_PostgreSQL.md)） |
| 索引重命名 | `ALTER TABLE … RENAME INDEX old TO new` | 迁移脚本改名索引用的形态（其余库见各自文档） |
| 表引擎 | InnoDB（默认） | 事务与外键能力来源 |

- 迁移、建删库与批量迁移命令口径见《[数据库开发规范](../../../规范/数据库开发规范.md)》「迁移与建表口径」节。

## 4. 空值与排序 <a id="null"></a>

| 事项 | MySQL 8 行为 | 平台口径 |
| --- | --- | --- |
| 默认 NULL 位次 | NULL 视作**最小**（升序在前、降序在后） | 不依赖库默认：统一「NULL 恒排末位」，由 ORDER BY 内 `列 IS NULL` 排序键实现 |
| `NULLS FIRST/LAST` 语法 | **不支持**（SQLAlchemy 直接渲染 `NULLS LAST` 会语法报错——实测） | 禁止在任何方言下写 `NULLS FIRST/LAST`，统一用 `IS NULL` 排序键 |
| 唯一索引与多 NULL | 唯一索引允许多个 NULL | 复合唯一 `(唯一字段, deleted_at)` 未删行不冲突（实测通过） |
| 空串与 NULL | `''` 与 NULL 可区分 | 不用 NULL 表达空串；可空字符串列统一写 NULL |

## 5. 标识符与模式 <a id="identifier"></a>

- 标识符（库 / 表 / 列 / 索引）统一**小写**；须引用时用反引号；长度上限 64 字符。
- 库表名大小写敏感性取决于实例参数 `lower_case_table_names`（容器默认与平台约定：统一小写以规避差异；**待验**：变更该参数需重建实例）。
- 无 schema 前缀语法，SQL 中**不写** `库名.表名` 限定（跨库 JOIN 本身禁止）。

## 6. 索引与约束 <a id="index"></a>

- 索引名在**表内**唯一（库内可重名）；平台命名仍含表名（`idx_{表}_{列}` / `uq_{表}_…`）以对齐其余库口径。
- 每表索引 ≤ 5 个（平台强制）；唯一索引允许重复 NULL（见第 4 节）。
- **无部分索引**：以 `(唯一字段, deleted_at)` 复合唯一模拟「仅未删行唯一」（PostgreSQL 可另用部分唯一索引优化，见 [PostgreSQL](02_PostgreSQL.md)）。
- 长 VARCHAR 可用前缀索引（`列(n)`）；平台默认不用，确需时须在表文件注明并实测选择性（**待验**）。

## 7. 事务与连接 <a id="tx"></a>

| 事项 | MySQL 8 行为 / 平台做法 | 结论 |
| --- | --- | --- |
| 默认隔离级别 | REPEATABLE READ | 实测（默认值）；业务**不依赖**读已提交 / 可重复读差异 |
| DDL 与事务 | DDL 隐式提交 | 迁移失败后按「已执行到哪一步」人工核对（幂等靠 `alembic_version`） |
| 连接池 | `pool_size` / `max_overflow` / `pool_timeout` / `pool_recycle` / `connect_timeout` 取配置 `[database.*.pool]` | 实测（配置项生效） |
| 慢查询日志 | 开启（开发联调） | 实测（已配置） |
| 主从（只读副本） | 支持；读写绑定见《[架构设计 · 数据访问与分片](../../架构设计/13_架构设计_子系统_数据访问与分片.md)》「读写分离」节 | 未启用（**待验**；真库仅验证「配置副本后只读请求命中副本引擎」的路由决策） |
| 认证插件与驱动依赖 | MySQL 8.4 默认 `caching_sha2_password`；`aiomysql` 在非 TLS 连接下**冷缓存首连**需 `cryptography` 完成 RSA 公钥取回，缺它报 `cryptography package is required for sha256_password or caching_sha2_password auth methods`（**实测**） | 后端依赖固定含 `cryptography`；CI 基础镜像随锁文件哈希重建（缺失即真库首连失败） |

- 应用侧经引擎注册表与会话入口取连接（不自行 `create_engine`）；事务边界由服务层上下文管理器声明。

## 8. 实测记录 <a id="measured"></a>

| 日期 | 项 | 结论 | 证据 |
| --- | --- | --- | --- |
| 2026-09-22 | 平台链迁移（临时库 `bms_migrcheck`） | 建库 → 迁移 → 校验（`0001_sys_tenant_module`，表 4/4）→ 清理，通过 | 01_04 测试记录「三库真库迁移演练」 |
| 2026-09-22 | 租户链迁移（临时库 `bms_migrcheck_tenant`） | 建库 → 迁移 → 校验（`0001_dict_query_scheme`，表 8/8）→ 清理，通过 | 同上 |
| 2026-09-22 | 类型映射与 DDL 编译 | 四方言 DDL 编译断言通过（含布尔与 `JSON` 列） | `tests/models/test_type_mapping.py` |
| 2026-09-22 | 三库真库集成（库 `bms_test_mysql` / `bms_test_mysql_t1`） | 建库 → 分链迁移（`0001_sys_tenant_module` / `0001_dict_query_scheme`）→ 集成用例 9 条通过（多数据源 / 隔离 / 副本路由 / 分片键 / 类型往返 / NULL 位次 / 复合唯一多 NULL 共存） | 01_05 测试记录「三库真库集成用例」 |
| 2026-09-22 | 认证插件与驱动依赖 | 测试账号（`bms_test`，`caching_sha2_password`）冷缓存首连报 `cryptography package is required…`，补齐 `cryptography` 后连通 | 01_05 实施记录「问题与处置」 |
| 2026-09-22 | JSON 值读写 | 写入读回一致（真库集成用例「类型落库往返」） | 01_05 集成用例 |
| 待验 | 字符集与 emoji 写入、`lower_case_table_names` 变更影响、前缀索引选择性、主从只读路由、JSON 检索 | — | — |

> 数据库设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「表与字段口径」至「数据库设计文档体系」各节配套
