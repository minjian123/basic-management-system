# SQLite 与 aiosqlite 技术介绍

> 开发/测试数据库 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › SQLite 与 aiosqlite 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**SQLite** 是一个**嵌入式关系型数据库**：没有独立服务进程，
数据库就是本机一个文件，零配置、零部署成本。BMS 用它作为**开发与测试环境**的
默认数据库。**aiosqlite** 是 SQLite 的异步 Python 驱动，让它在异步栈里正常工作。

- **定位**：日常开发、单元/接口测试统一用 SQLite，保证环境可移植；生产不用它。
- **版本**：SQLite 3.x（跟随系统/镜像自带版本）；aiosqlite 0.2x 系列。
- **许可**：SQLite 公有领域（Public Domain）；aiosqlite 为 MIT。
- **语言**：C（SQLite）/ Python（aiosqlite），经 SQLAlchemy dialect（sqlite+aiosqlite）接入。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 嵌入式数据库 | 以库文件形式存在，应用进程直接读写文件，无独立服务进程、无网络端口 |
| 文件数据库 | 一个 .db 文件即一个完整库；BMS 用多个 SQLite 文件模拟平台库/租户库/归档库 |
| 零配置 | 无需安装服务、无需建账号密码，uv 环境自带，克隆仓库即可跑 |
| 类型亲和性 | SQLite 对列类型宽松（任何列可存任意类型），与 MySQL/PostgreSQL 的严格类型不同，方言验证时不代表生产行为 |
| WAL 模式 | 写前日志：提高并发读写性能，读写可并行；生产型数据库（MySQL/PG）不需要此配置 |
| 并发限制 | 单写者模型：同一时刻只有一个连接能写库，写频繁时产生锁等待 |
| aiosqlite | 把同步 sqlite3 模块包一层线程池异步化：调用不阻塞事件循环，但底层仍是同步执行 |
| 内存库（:memory:） | 数据库建在内存中，测试隔离场景常用；连接关闭即销毁 |
| 与四库兼容口径 | 规划要求 SQLite/MySQL/PostgreSQL/达梦四库行为一致：软删除复合唯一索引等 SQLite 也需验证（见《[项目规划说明》11.1 节](../../../规划/项目规划说明.md#dbrule)） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 开发环境默认数据库：`BMS_ENV=dev` 时连接本地 SQLite 文件，零部署即可起后端（见《[开发部署规划](../../../规划/开发部署规划.md)》5.3 节）。
- 多库拓扑模拟：用多个 SQLite 文件分别模拟平台库、租户库与归档库，与生产多数据源策略一一对应（见《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource)）。
- **测试统一用 SQLite 保证可移植**：pytest 单测/接口测试全部跑 SQLite，本地与 CI 同源，任何人克隆即测（见《[项目规划说明》16 节](../../../规划/项目规划说明.md#test)）。
- 异步驱动 aiosqlite 经 SQLAlchemy `sqlite+aiosqlite` dialect 接入，与整体异步栈一致（见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》）。
- SQLite 开发库自动建表（不跑 Alembic 迁移），schema 一致性由三库 CI 方言测试兜底（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **SQLite（开发/测试，选中）** | 零部署、零维护、单文件可复制可重置；并发与功能弱于生产库，方言不完全等同 | 开发/测试场景成本最低，CI 可移植性最好 |
| MySQL / PostgreSQL 本地装 | 方言与生产一致；但每台开发机都要装服务、建库建号，CI 也要起容器 | 只留 CI 三库方言测试兜底，日常开发不用 |
| 内存库替代 | 测试更快；但多文件模拟拓扑、跨连接可见性与调试便利不如文件库 | 按需局部使用，不作为默认 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **SQLite 过不代表三库过**：类型亲和性、JSON、索引等行为与 MySQL/PostgreSQL/达梦有差异，方言相关代码必须靠 CI 三库集成测试验证，不能只跑本地。
- **并发写锁**：测试或本地联调时并发写多会报 "database is locked"，必要时开 WAL；应用层仍要按单写者思维设计。
- **多文件拓扑别串库**：平台库/租户库/归档库是不同文件，SQLAlchemy 多 engine 配置要对号入座，避免租户数据写错库。
- **aiosqlite 本质是线程池**：它不是真正的异步内核，只是不阻塞事件循环；大事务性能不必在本地较真。
- **生产禁用**：SQLite 仅限开发与测试，生产三库（MySQL/PostgreSQL/达梦）不支持文件库形态。
- **字符集与排序**：SQLite 默认大小写行为与生产库不同（如 LIKE 对 ASCII 大小写不敏感），测试断言注意别依赖这些边界。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| SQLite 官网 | https://www.sqlite.org/ | 权威资料：语法、文档、许可说明 |
| SQLite WAL 模式文档 | https://www.sqlite.org/wal.html | WAL 并发模型官方说明 |
| aiosqlite GitHub | https://github.com/omnilib/aiosqlite | 异步驱动源码与 issue |
| aiosqlite 文档 | https://aiosqlite.omnilib.dev/ | API 与用法说明 |
| SQLAlchemy SQLite 方言文档 | https://docs.sqlalchemy.org/en/20/dialects/sqlite.html | sqlite dialect 特性与限制说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：SQLite（开发/测试，aiosqlite）条目 |
| 《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat) | 数据库兼容：SQLite 纳入四库行为一致口径 |
| 《[开发部署规划](../../../规划/开发部署规划.md)》 | 开发环境 SQLite 配置与多文件模拟说明 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 异步 engine 与多数据源管理 |
| 《[Alembic 技术介绍](Alembic技术介绍.md)》 | SQLite 自动建表、三库跑迁移的边界 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | 测试库统一 SQLite 的测试策略 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19