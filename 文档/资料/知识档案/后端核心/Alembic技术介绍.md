# Alembic 技术介绍

> 数据库迁移工具 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › Alembic 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Alembic** 是 SQLAlchemy 官方出品的**数据库 schema 迁移工具**：
把表结构变更写成带版本号的迁移脚本（revision），支持升级（upgrade）与回滚（downgrade），
并能基于模型自动生成迁移脚本（autogenerate）。它是项目里"改表结构"的唯一正规渠道。

- **定位**：统一管理 MySQL / PostgreSQL / 达梦 DM8 各库 schema 变更；SQLite 开发库自动建表。
- **版本**：1.x 系列（与 SQLAlchemy 2.0 同步演进）。
- **许可**：MIT，OSI 认证开源。
- **语言**：Python（本项目 3.14+）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 迁移脚本（revision） | 一个文件 = 一次 schema 变更，内含 `upgrade()` 与 `downgrade()` 两个方向的操作 |
| versions/ 目录 | 迁移脚本存放目录，按版本号链式组织，是"表结构的历史档案" |
| alembic.ini | 迁移工具配置文件（脚本目录、日志等）；本项目 URL 不从 ini 硬编码，从 config.toml 读取 |
| env.py | 迁移运行入口脚本：决定连接哪个库、加载哪些模型元数据、启用 autogenerate 依据 |
| autogenerate | 对比当前模型声明与数据库实际结构，自动生成迁移脚本草稿（仍需人工复核） |
| alembic_version 表 | 记录当前库已执行到的版本号，升级/回滚以此为准 |
| upgrade / downgrade | 升级（向前应用变更）与降级（回滚变更），支持指定版本号或 head |
| 多方言迁移 | 同一变更在 MySQL/PostgreSQL/达梦上 SQL 不同，脚本需按方言验证（JSON 类型、索引、NULL 唯一键等） |
| 批量迁移 | 遍历全部租户库逐一执行迁移：新租户开通自动建库 + 迁移 + 种子（见《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource)） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为唯一 schema 版本管理工具：目录 `alembic/` + `alembic.ini`，URL 从 config.toml 读取，不写死连接串（见《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend)）。
- 按数据源分别维护迁移脚本：只管理各库 schema；平台库、租户库、归档库各走一套迁移链（见《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource)）。
- **方言差异分环境验证**：维护 MySQL / PostgreSQL / 达梦 DM8 三套方言迁移；SQLite 开发库自动建表不跑迁移（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。
- CI 三库方言集成测试：连 mjbk 常驻三库，建 bms_test 前缀测试库 → Alembic 迁移 → 集成测试 → 删库清理，保证迁移脚本在每类库上真实可执行（见《[开发部署规划](../../../规划/开发部署规划.md)》与《[项目规划说明》16 节](../../../规划/项目规划说明.md#test)）。
- 新租户开通自动建库 + 迁移 + 种子数据，靠批量迁移遍历 sys_tenant 实现。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Alembic（选中）** | 与 SQLAlchemy 同源，autogenerate 直接吃模型声明；Python 生态原生；支持编程式多库遍历 | 与项目 ORM 层零缝隙衔接，天然适配批量/多库场景 |
| Flyway | Java 生态、SQL 文件式迁移成熟；但引入 JVM 工具链，与 Python 模型对比能力弱 | 跨语言心智负担大，排除 |
| Liquibase | XML/YAML 描述变更、多库支持好；重量级、学习成本高 | 过度设计，排除 |
| 手写 SQL 脚本 | 零依赖；无版本链、无自动生成、无回滚保障，容易漏改 | 团队协作下不可靠，明确不用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **autogenerate 必须复核**：它生成的是草稿，类型映射、索引名、注释等常有偏差；提交前逐行检查 diff。
- **三库方言差异**：同一迁移在 MySQL（如 utf8mb4 长度限制）、PostgreSQL（部分索引）、达梦（Oracle 兼容口径的 NULL 唯一键）上表现不同，改表后必须跑三库 CI 方言测试。
- **env.py 的 URL 来源**：不要手改 ini 里的 sqlalchemy.url 写死连接，一律从 config.toml 读取，保持环境一致性。
- **批量迁移失败回滚**：遍历租户库时某库失败要能定位到库、可重入（脚本必须幂等），避免半程状态。
- **downgrade 不一定总是安全**：删列/改类型的数据不可恢复，生产降级前评估数据影响；破坏性变更建议"先加后删"两段式。
- **模型与迁移脱节**：改了模型不生成迁移、或迁移不提交，CI 与测试库就会报警；约定"模型变更必须附迁移脚本"。
- **SQLite 不跑迁移**：开发/测试库自动建表，方言验证只发生在 CI 三库，本地改方言语句前先想清楚后果。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Alembic 官方文档 | https://alembic.sqlalchemy.org/ | 权威文档：命令、env.py、操作参考 |
| Alembic autogenerate 指南 | https://alembic.sqlalchemy.org/en/latest/autogenerate.html | 自动生成迁移的机制与限制说明 |
| Alembic GitHub | https://github.com/sqlalchemy/alembic | 源码、issue 与版本发布 |
| SQLAlchemy 官方文档 | https://docs.sqlalchemy.org/ | 底层模型与元数据机制，理解 env.py 的基础 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：数据库迁移条目（URL 来自 config.toml） |
| 《[项目规划说明》10 节](../../../规划/项目规划说明.md#datasource) | 多数据源策略：按数据源分迁移、租户批量迁移 |
| 《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat) | 数据库兼容：三套方言迁移维护口径 |
| 《[开发部署规划](../../../规划/开发部署规划.md)》 | CI 三库方言测试与 bms_test 测试库流程 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 迁移的对象：模型声明与元数据 |
| 《[MySQL 技术介绍](MySQL技术介绍.md)》等三库文档 | 各库方言特性与差异来源 |
| 《[数据库开发规范](../../../规范/数据库开发规范.md)》 | 表结构变更与迁移脚本的流程要求 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19