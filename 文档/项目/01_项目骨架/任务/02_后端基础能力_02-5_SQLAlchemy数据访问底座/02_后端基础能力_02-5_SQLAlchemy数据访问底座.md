# 02-5 SQLAlchemy 数据访问底座

> 项目骨架 · 02 后端基础能力 · 子任务 02-5

[文档首页](../../../../文档首页.md) › [02 后端基础能力](../02_后端基础能力.md) › 02-5 SQLAlchemy 数据访问底座　|　[← 父任务](../02_后端基础能力.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02-5 |
| 父任务 | [02 后端基础能力](../02_后端基础能力.md) |
| 对应需求 | [02-5](../../需求/02_需求_后端基础能力.md#r02-5) |
| 禅道任务 | 144（父任务 130） |
| 工时（重估） | 6h |
| 依赖 | 01-6（依赖锁定）、02-1（数据源配置） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. 引擎工厂（`app/db/engine.py`）：四方言 URL 模板（sqlite+aiosqlite / mysql+aiomysql?charset=utf8mb4 / postgresql+psycopg / dm+dmPython）；统一连接池参数来自 config.toml；字符集 MySQL utf8mb4、PostgreSQL/达梦 UTF8
2. **达梦同步驱动接入（先修订口径再实现）**：dmPython 为同步驱动，与《后端开发规范》第 8 节「禁止请求路径同步 DB 驱动」及架构 09「多异步 bind」存在口径缺口——先修订《架构设计 09》与《后端开发规范》第 8 节（同步 engine + asyncio.to_thread 执行器封装的例外口径），确认后实现
3. 会话工厂（`app/db/session.py`）：async_sessionmaker（expire_on_commit=False）、get_db 请求级依赖、异步会话禁止跨请求共享；事务边界 services 层 `with session.begin()`
4. Base 与元数据（`app/models/base.py`）：DeclarativeBase + BaseModel 基类（03-2 字段细节）；表名单数 snake_case、idx_/uq_ 前缀、COMMENT 必填
5. 读写分离占位：读写路由接口（按上下文标记选引擎），阶段一主从同源
6. 查询基线：禁止 SELECT *、bulk 写入、ORM 层禁用方言特有功能、分页统一 limit/offset

## 3. 完成标准 <a id="accept"></a>

SQLite 平台库建库 + 基类模型自动建表 + CRUD 冒烟通过；MySQL/PostgreSQL 异步引擎各连通一次（SELECT 1）；达梦按修订后口径连通（dmPython SELECT 1）；读写路由占位主从同源可用；达梦口径修订已落入《架构设计 09》与《后端开发规范》第 8 节。

## 4. 参考文档 <a id="ref"></a>

- 《项目规划说明》3.1/10/11
- 《后端开发规范》第 7/8 节
- 《架构设计 · 数据访问与分片》
- 《数据库开发规范》第 6 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23
