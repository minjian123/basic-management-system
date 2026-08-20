# SQLAlchemy 技术介绍

> 数据库抽象层（ORM/Core） · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › SQLAlchemy 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**SQLAlchemy** 是 Python 最成熟的数据库工具包，提供 **ORM**
（用类与对象操作表）与 **Core**（SQL 表达式）两套 API，并统一屏蔽
MySQL、PostgreSQL、达梦、SQLite 等数据库的方言差异。2.0 版本起两套 API 完全统一，
全面支持异步。

- **定位**：BMS 唯一的数据库抽象层，所有数据访问（含多数据源、多租户路由）经它完成。
- **版本**：2.0+（2.0 于 2023 年 1 月发布，ORM/Core 统一声明式）。
- **许可**：MIT，OSI 认证开源。
- **语言**：Python（本项目 3.14+）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| ORM | 对象关系映射：`class User(Base): ...` 声明模型，表结构映射为类，行映射为对象 |
| Core | SQL 表达式语言：不定义模型，直接用 `table.insert()` 等表达式拼 SQL，适合批量/复杂查询 |
| Engine | 数据库连接入口：持有连接池与方言（dialect），一个数据源对应一个 engine |
| Async Engine | `create_async_engine()` 创建的异步引擎，配套 AsyncSession，所有 I/O 不阻塞事件循环 |
| Session / AsyncSession | 工作单元（Unit of Work）：跟踪对象变更、组装事务；异步会话不可跨请求共享 |
| Declarative 映射 | 用类声明表结构（列、索引、关系），模型同时承担类型提示，与 Pydantic schema 解耦分工 |
| relationship / 关联加载 | 对象间关系的声明式导航；懒加载在异步下会报错，需显式 selectin 等加载策略 |
| 连接池 | pool_size / max_overflow 控制池大小，避免每次请求建连；多 worker 下按 70% 上限规划 |
| N+1 查询 | 遍历 N 条记录时逐条查询关联表的反模式，用 selectinload/joinedload 或明确聚合避免 |
| 方言（Dialect） | 每类数据库的 SQL 差异翻译层：mysql+aiomysql、postgresql+psycopg、dm+dmPython、sqlite+aiosqlite |
| 多 bind / 多 engine | 一个应用同时管理多个数据源：每个数据源独立 engine，按模块或租户选择 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 统一 ORM/Core 两套 API：常规 CRUD 用 ORM 模型，批量与复杂查询用 Core，一套学习曲线覆盖全场景（见《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend)）。
- **多数据源**：多个异步 engine 管理，repositories 层按模块指定数据源；主从读写分离、分片路由均落在数据访问层（见《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource)）。
- **租户独立库动态路由**：一租户一库，请求按 tenant 路由到对应异步 engine——懒加载创建 + 闲置回收 + 池上限控制，避免全量租户连接常驻（见《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource)与《[14 节](../../../规划/项目规划说明.md#perf)》）。
- 异步会话生命周期由 FastAPI 依赖注入管理：每个请求创建独立 AsyncSession，事务随请求关闭（见《[FastAPI 技术介绍](FastAPI技术介绍.md)》）。
- **四库兼容**：ORM 层禁用方言特有功能，JSON 等类型用跨方言通用类型，分页统一 limit/offset；软删除唯一键统一建 (唯一字段, deleted_at) 复合索引（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。
- 连接池按 worker 规划：总连接数 = worker × (pool_size + max_overflow) ≤ 数据库 max_connections 的 70%（见《[项目规划说明》14 节](../../../规划/项目规划说明.md#perf)）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **SQLAlchemy 2.0+（选中）** | ORM/Core 统一、异步支持成熟、四库方言齐全（含达梦 dm+dmPython）、生态最大 | 唯一能满足多数据源 + 多租户 + 四库兼容的成熟选择 |
| SQLModel | FastAPI 作者作品、与 Pydantic 融合好；但达梦方言与复杂场景支持弱、API 仍在演进 | 轻量场景合适，重业务与多库兼容不匹配 |
| Tortoise ORM | 异步原生、Django 风格；社区与三方生态小，达梦无方言 | 无法覆盖达梦与复杂 SQL，排除 |
| Django ORM | 最成熟全家桶；异步支持有限、脱离 Django 框架使用别扭 | BMS 用 FastAPI 而非 Django，不匹配 |
| Peewee | 轻量、上手快；功能与异步支持有限，不适合大型多租户系统 | 玩具级，排除 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **异步会话不可跨请求共享**：AsyncSession 生命周期必须绑定单个请求，由依赖注入创建、请求结束关闭；跨请求复用会造成连接泄漏与脏数据。
- **N+1 查询**：循环内逐条访问 relationship 会按次发 SQL；用 `selectinload` / `joinedload` 预加载或改写为聚合查询。
- **大事务显式声明边界**：事务内不要混入外部 I/O（HTTP 调用、文件写入），长时间持锁会拖垮数据库；跨服务流程把事务范围缩到最小（见《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend)）。
- **懒加载在异步下报错**：异步会话中默认懒加载会抛 MissingGreenlet，关联字段必须用显式加载策略。
- **连接池耗尽**：worker × (pool_size + max_overflow) 超出数据库上限时排队报错；多租户场景靠懒加载 + 闲置回收控制活跃 engine 数。
- **同步/异步 API 混用**：sync Session 与 AsyncSession 不能混用（连接被占用的坑），整个链路上下一律用异步。
- **方言禁用清单**：JSON/分页等用通用类型与通用写法，避免四库迁移时爆差异（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| SQLAlchemy 官方文档 | https://docs.sqlalchemy.org/ | 权威文档：ORM、Core、会话、连接池全参考 |
| SQLAlchemy 异步使用指南 | https://docs.sqlalchemy.org/en/20/orm/async_io.html | 异步 engine/AsyncSession 官方教程，必读 |
| SQLAlchemy 官网 | https://www.sqlalchemy.org/ | 项目主页与新闻 |
| SQLAlchemy GitHub | https://github.com/sqlalchemy/sqlalchemy | 源码、issue 与版本发布 |
| SQLAlchemy 2.0 迁移指南 | https://docs.sqlalchemy.org/en/20/changelog/migration_20.html | 2.0 行为变更对照，参考旧资料时对照 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：数据库抽象条目（异步 ORM/Core，多数据源） |
| 《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource) | 多数据源策略：多 bind、租户路由、懒加载/回收/池上限 |
| 《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat) | 数据库兼容：禁用方言功能、跨方言类型约定 |
| 《[Alembic 技术介绍](Alembic技术介绍.md)》 | 基于 SQLAlchemy 的 schema 迁移工具 |
| 《[MySQL 技术介绍](MySQL技术介绍.md)》等三库文档 | 各数据库驱动与方言（aiomysql/psycopg/dmPython） |
| 《[SQLite 与 aiosqlite 技术介绍](SQLite与aiosqlite技术介绍.md)》 | 开发/测试库与异步驱动 |
| 《[数据库开发规范](../../../规范/数据库开发规范.md)》 | 模型声明、索引、审计字段等约束 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19