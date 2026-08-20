# PostgreSQL 技术介绍

> 生产数据库之一 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › PostgreSQL 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**PostgreSQL** 是功能最丰富的开源关系型数据库，以严格的标准实现、
强大的扩展生态著称（JSONB、部分索引、PostGIS 等）。BMS 将其作为**生产数据库之一**，
与 MySQL、达梦 DM8 并行支持。

- **定位**：生产可选数据库；开发服务器 mjbk 常驻实例供联调与 CI 方言测试。
- **版本**：16+（16 及以后大版本，具体以部署环境为准）。
- **许可**：PostgreSQL License——宽松许可，类 MIT/BSD，商用无传染顾虑。
- **Python 驱动**：psycopg 3（官方维护，原生异步）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| MVCC | 多版本并发控制：读写互不阻塞，读查询不抢锁，高并发读友好 |
| WAL（预写日志） | 变更先写日志再落数据页：崩溃恢复与时间点恢复（PITR）的基础 |
| JSONB | 二进制 JSON 类型：可索引、可查询，适合半结构化数据（BMS 表单定制等场景） |
| 部分索引 | 只对满足条件的行建索引：软删除场景的优化手段（规划 11.1 节提及可选优化） |
| 序列（SERIAL/IDENTITY） | 自增值生成机制，与 MySQL 的 AUTO_INCREMENT 对应但语义不同 |
| 主从复制与流复制 | WAL 流式复制到从库，支持读写分离与故障切换 |
| psycopg 3 | PostgreSQL 官方维护的 Python 驱动：原生异步支持，dialect `postgresql+psycopg`，替代已冻结的 psycopg2 |
| psycopg2 | 经典同步驱动，已进入冻结（仅修 bug）状态，本项目不采用 |
| UTF8 字符集 | 本项目字符集约定：PostgreSQL UTF8 |
| 扩展生态 | PostGIS、pgvector 等扩展可平滑扩展能力（后续演进按需评估） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 生产数据库之一，与 MySQL、达梦 DM8 三库并行支持；开发/测试默认 SQLite（见《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend)）。
- **psycopg 3 驱动**：PostgreSQL 官方维护、原生异步（dialect `postgresql+psycopg`），替代已冻结的 psycopg2（见《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend)）。
- 数据层主从：PostgreSQL 主从（读写分离 + 故障切换），1 平台库 + N 租户库 + 1 归档库（见《[项目规划说明》19.1 节](../../../规划/项目规划说明.md#deploy-topo)）。
- 软删除优化：PostgreSQL 可另加部分唯一索引优化（基础方案四库统一的 (唯一字段, deleted_at) 复合唯一索引）（见《[项目规划说明》11.1 节](../../../规划/项目规划说明.md#dbrule)）。
- 备份与恢复：每日全量备份 + WAL 时间点恢复（PITR），保留 30 天异机存储（见《[项目规划说明》19.4 节](../../../规划/项目规划说明.md#deploy-backup)）。
- CI 三库方言集成测试：复用 mjbk 常驻 PostgreSQL，job 内建 bms_test 前缀测试库，迁移 → 测试 → 清理（见《[开发部署规划](../../../规划/开发部署规划.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **PostgreSQL 16+（选中）** | 功能丰富、许可宽松（PostgreSQL License）、驱动官方维护；部分客户不熟悉其运维 | 作为生产三库之一，尤适合重视功能与合规的场景 |
| MySQL 8.x | 生态广、团队熟悉；功能与许可条款略逊 | 与 PostgreSQL 并行支持，按客户环境选用（见《[MySQL 技术介绍](MySQL技术介绍.md)》） |
| asyncpg（驱动层） | 性能最好的异步驱动；但非官方、API 另起炉灶，与 SQLAlchemy 集成需适配 | psycopg 3 已满足需求且官方维护，不引入 |
| psycopg2（驱动层） | 经典稳定；已冻结停更，异步需配线程池 | 明确不采用，用 psycopg 3 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **psycopg2 已冻结**：老资料与网上示例大量基于 psycopg2，本项目的连接串是 `postgresql+psycopg`（3），别混用两个 dialect。
- **自增语义差异**：序列与 MySQL AUTO_INCREMENT 行为不同（批量插入、回滚后序号不重用），跨库测试时别断言具体序号值。
- **方言差异**：部分索引、JSONB、ILIKE 等是 PG 特性，ORM 层统一用跨方言写法，方言优化只在三库验证通过的迁移/查询中使用（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。
- **连接池规划**：与 MySQL 同口径——worker × (pool_size + max_overflow) ≤ max_connections 的 70%（见《[项目规划说明》14 节](../../../规划/项目规划说明.md#perf)）。
- **主从延迟**：流复制异步语义下从库可能滞后，"读后写"场景走主库路由。
- **事务边界**：长事务会堆积 MVCC 旧版本（膨胀），大事务显式声明边界并及时提交（见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》）。
- **驱动注意**：psycopg 3 在 Python 3.14 的兼容性纳入阶段一逐依赖验证口径（见《[Python 技术介绍](Python技术介绍.md)》）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| PostgreSQL 官网 | https://www.postgresql.org/ | 下载、文档与社区入口 |
| PostgreSQL 官方文档 | https://www.postgresql.org/docs/ | 权威参考：SQL、复制、备份恢复 |
| psycopg 3 官网 | https://www.psycopg.org/ | psycopg 3 文档与下载 |
| psycopg 3 文档 | https://www.psycopg.org/psycopg3/ | 异步用法、连接参数参考 |
| psycopg GitHub | https://github.com/psycopg/psycopg | 源码与 issue |
| SQLAlchemy PostgreSQL 方言文档 | https://docs.sqlalchemy.org/en/20/dialects/postgresql.html | postgresql dialect 特性说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：PostgreSQL 16+ 与 psycopg 3 条目 |
| 《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend) | 选型说明：psycopg 3 替代 psycopg2 |
| 《[项目规划说明》11.1 节](../../../规划/项目规划说明.md#dbrule) | 数据规范：软删除与部分唯一索引优化 |
| 《[PostgreSQL 部署使用说明](?../../开发服务器/PostgreSQL部署使用说明.md》 | 开发服务器 mjbk 上的部署与访问细节 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 异步 engine、连接池与多数据源 |
| 《[Alembic 技术介绍](Alembic技术介绍.md)》 | PostgreSQL 方言迁移脚本与三库验证 |
| 《[MySQL 技术介绍](MySQL技术介绍.md)》 | 并行支持的另一生产数据库 |
| 《[数据库开发规范](../../../规范/数据库开发规范.md)》 | 字符集、命名、索引等落地约束 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19