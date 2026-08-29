# MySQL 技术介绍

> 生产数据库之一 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › MySQL 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**MySQL** 是世界上最流行的开源关系型数据库之一（Oracle 公司维护），
以成熟稳定、生态庞大著称。BMS 将其作为**生产数据库之一**，
与 PostgreSQL、达梦 DM8 并行支持（部署时按客户环境选择）。

- **定位**：生产可选数据库；开发服务器 mjbk 常驻实例供联调与 CI 方言测试。
- **版本**：8.x（8.0 系列 / 8.4 LTS，以部署环境为准）。
- **许可**：GPL-2.0（社区版）。作为独立数据库服务、Python 驱动走协议连接时不触发传染；商业交付需关注 Oracle 双许可条款（详见规划 2.5 节）。
- **Python 驱动**：aiomysql（异步，默认）/ PyMySQL（同步 fallback）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 关系型数据库 | 数据按表/行/列组织，通过 SQL 查询；事务保证 ACID |
| InnoDB 存储引擎 | 默认引擎：支持事务、外键、行级锁、崩溃恢复，是 8.x 的事实标准 |
| 事务与 ACID | 原子性/一致性/隔离性/持久性：多步写操作要么全成功要么全回滚 |
| Binlog（二进制日志） | 记录所有变更，用于主从复制与时间点恢复（PITR），是备份策略的基石 |
| 主从复制 | 一主多从异步复制：主库写、从库读，实现读写分离与故障切换 |
| max_connections | 最大连接数：应用连接池规划的硬上限（≤ 其 70%） |
| utf8mb4 | 完整 Unicode 字符集（含 emoji），本项目字符集约定 |
| aiomysql | MySQL 异步驱动，与整体异步栈一致；其底层为 PyMySQL 的移植（见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》） |
| PyMySQL | 纯 Python 同步驱动，用作同步 fallback 场景 |
| asyncmy | 备选异步驱动：性能更好，但维护活跃度一般，不入选 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 生产数据库之一，与 PostgreSQL、达梦 DM8 三库并行支持；开发/测试默认 SQLite（见《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend)）。
- **aiomysql 异步驱动**（dialect `mysql+aiomysql`）；同步 fallback 可换 PyMySQL；备选 asyncmy 性能更好但维护活跃度一般，故不采用（见《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend)）。
- 数据层主从：MySQL 主从读写分离 + 故障切换，1 平台库 + N 租户库 + 1 归档库（见《[项目规划说明》19.1 节](../../../规划/项目规划说明.md#deploy-topo)）。
- 字符集 utf8mb4；连接池按 worker 数规划（≤ 70% max_connections）；慢查询日志开发联调用（见《[项目规划说明](../../../规划/项目规划说明.md#dbrule)》11.1 节与《[开发部署规划](../../../规划/开发部署规划.md)》，部署口径见《[开发服务器部署使用说明总览](../../开发服务器/开发服务器部署使用说明总览.md)》）。
- 备份与恢复：每日全量备份 + Binlog 时间点恢复（PITR），保留 30 天异机存储（见《[项目规划说明》19.4 节](../../../规划/项目规划说明.md#deploy-backup)）。
- CI 三库方言集成测试：复用 mjbk 常驻 MySQL，job 内建 bms_test 前缀测试库，迁移 → 测试 → 清理（见《[开发部署规划](../../../规划/开发部署规划.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **MySQL 8.x（选中）** | 生态最广、资料多、团队熟悉度高；GPL-2.0 社区版商用需注意边界 | 作为生产三库之一，满足常规客户环境 |
| PostgreSQL 16+ | 功能更丰富（部分索引/JSONB）、许可更宽松；与 MySQL 同列三库并行而非替代（见《[PostgreSQL 技术介绍](PostgreSQL技术介绍.md)》） | 并行支持，按客户环境选用 |
| MariaDB | MySQL 分支、许可宽松；但与官方 MySQL 行为渐有差异，生态对齐成本 | 沿用 MySQL 官方路线，不引入分支 |
| asyncmy（驱动层） | 性能更好；但维护活跃度一般、社区小 | 默认 aiomysql，不追求极限性能 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **GPL 传染误读**：社区版 GPL-2.0 只约束 MySQL 自身及衍生修改；BMS 作为独立应用通过协议连接、不修改不分发其源码即不传染。介意或需官方支持时采购商业版（见《[项目规划说明》2.5 节](../../../规划/项目规划说明.md#stack-license)）。
- **utf8 与 utf8mb4**：MySQL 的 `utf8` 是历史遗留别名（3 字节），emoji 会存失败；统一用 utf8mb4。
- **连接数规划**：worker × (pool_size + max_overflow) 必须 ≤ max_connections 的 70%，并预留监控/运维连接。
- **方言差异**：JSON 类型、大小写敏感（表名/列名）、索引长度限制与 PostgreSQL/达梦不同，迁移脚本在三库分别验证（见《[Alembic 技术介绍](Alembic技术介绍.md)》）。
- **主从延迟**：读写分离下从库读到旧数据，涉及"读后写"的接口需走主库（BMS 在主从路由层处理）。
- **保留字**：如 sys_config 的 config_key 字段即因 key 为保留字改名，新表设计时避开保留字（见《[项目规划说明》6 节](../../../规划/项目规划说明.md#tables)）。
- **默认隔离级别**：InnoDB 默认 REPEATABLE READ，大事务下间隙锁易放大，事务边界要小（见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| MySQL 官网 | https://www.mysql.com/ | 官方产品与下载入口 |
| MySQL 8.0 参考手册 | https://dev.mysql.com/doc/refman/8.0/en/ | 权威文档：SQL、InnoDB、复制、备份 |
| aiomysql GitHub | https://github.com/aio-libs/aiomysql | 异步驱动源码与 issue |
| PyMySQL GitHub | https://github.com/PyMySQL/PyMySQL | 同步驱动源码与文档 |
| SQLAlchemy MySQL 方言文档 | https://docs.sqlalchemy.org/en/20/dialects/mysql.html | mysql dialect 特性说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：MySQL 8.x 与 aiomysql 条目 |
| 《[项目规划说明》2.5 节](../../../规划/项目规划说明.md#stack-license) | GPL-2.0 使用边界与商用注意事项 |
| 《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat) | 数据库兼容：跨方言类型与字符集约定 |
| 《[MySQL 部署使用说明](?../../开发服务器/MySQL部署使用说明.md》 | 开发服务器 mjbk 上的部署与访问细节 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 异步 engine、连接池与多数据源 |
| 《[Alembic 技术介绍](Alembic技术介绍.md)》 | MySQL 方言迁移脚本与三库验证 |
| 《[PostgreSQL 技术介绍](PostgreSQL技术介绍.md)》 | 并行支持的另一生产数据库 |
| 《[数据库开发规范](../../../规范/数据库开发规范.md)》 | 字符集、命名、索引等落地约束 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19