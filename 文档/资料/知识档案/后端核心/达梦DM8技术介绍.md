# 达梦 DM8 技术介绍

> 信创场景选配数据库 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › 达梦 DM8 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**达梦数据库（DM8）** 是武汉达梦数据库股份有限公司推出的国产商业关系型数据库，
与 Oracle 语法高度兼容，是国内**信创（信息技术应用创新）**场景的主流选配数据库。
BMS 将其作为生产数据库之一（信创环境选配），与 MySQL、PostgreSQL 三库并行支持。

- **定位**：生产可选数据库（信创交付必选），开发服务器 mjbk 常驻实例供联调与 CI 方言测试。
- **版本**：DM8（8.x 系列），开发环境用官方镜像 `dmdbms/dm8`（含试用授权）。
- **许可**：商业闭源，需采购商业授权（按套件/核数计费）；交付前须确认客户环境授权。
- **Python 驱动**：dmPython（达梦官方驱动，同步，dialect `dm+dmPython`）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| DM8 | 达梦数据库第 8 代产品：关系型数据库管理系统，语法兼容 Oracle，支持 SQL 标准 |
| dmPython | 达梦官方 Python 驱动，遵循 Python DB API 规范；**同步**驱动，dialect 为 `dm+dmPython` |
| dpi（达梦接口） | 达梦提供的 C 语言访问接口层，dmPython 依赖其头文件编译，安装驱动需 DM_HOME 指向 dpi 所在目录 |
| 模式（Schema） | 达梦以 schema 承载「库」语义，本项目多库划分在达梦中表现为多个 schema |
| Oracle 兼容 | 达梦兼容 Oracle 语法与语义，迁移 Oracle 应用成本低，但方言与 MySQL/PostgreSQL 差异大 |
| 数据守护（Data Guard） | 达梦主备复制方案（类似 Oracle DG），生产高可用场景用其做主从 |
| dmrman | 达梦官方备份恢复工具，本项目达梦库的每日备份用它执行 |
| DM_HOME | 达梦安装目录环境变量；dmPython 编译安装与运行时加载 dpi 动态库均依赖它 |
| UTF8 字符集 | 本项目字符集约定：达梦 DM8 用 UTF8 |
| 复合唯一索引 | 软删除场景四库统一用 (唯一字段, deleted_at) 复合唯一索引，达梦按 Oracle 兼容口径允许多个 NULL，阶段一验证 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 生产数据库之一（信创场景选配），与 MySQL、PostgreSQL 三库并行支持；开发/测试默认 SQLite（见《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend)）。
- **dmPython 驱动**：达梦官方同步驱动，dialect `dm+dmPython`；对 Python 3.14 兼容性未知，纳入阶段一逐依赖验证，不兼容则按规划口径整体回退 Python 3.13（见《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend)）。
- 三库方言测试：mjbk 常驻 MySQL/PostgreSQL/达梦，CI job 内建 `bms_test` 前缀测试库执行迁移与集成测试后清理（见《[开发部署规划](../../../规划/开发部署规划.md)》）。
- 数据库兼容约束：ORM 层禁用方言特有功能，JSON 等类型用跨方言通用类型兜底，分页统一 limit/offset；Alembic 维护三套方言迁移脚本，达梦迁移单独验证（见《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat)）。
- 备份：达梦 DM8 用 dmrman 备份/归档，每日全量 + 归档，保留 30 天异机存储（见《[项目规划说明》19.4 节](../../../规划/项目规划说明.md#deploy-backup)）。
- 开发期连接：通过环境变量 `BMS_DB_URL` 指向 mjbk 达梦库（如 `dm+dmPython://bms_dev:<password>@<mjbk-IP>:5236/bms_dev`）验证方言。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **达梦 DM8（选中）** | 国产自主、Oracle 兼容、信创合规必需；商业闭源需采购授权（按套件/核数计费），社区资料少 | 信创场景必选，非信创场景可不启用 |
| MySQL 8.x | 生态广、团队熟悉、成本低；非国产，信创场景不合规 | 与达梦并行支持，按客户环境选用（见《[MySQL 技术介绍](MySQL技术介绍.md)》） |
| PostgreSQL 16+ | 功能丰富、许可宽松；同样非国产 | 并行支持，与达梦互为替代（见《[PostgreSQL 技术介绍](PostgreSQL技术介绍.md)》） |
| Oracle 商用 | 功能最全、生态成熟；价格高、非国产 | 达梦兼容 Oracle 语法已满足信创需求，不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **驱动是同步的**：dmPython 无异步实现，在 async 接口中使用需线程池（`run_in_executor`）或走同步路径；连接串是 `dm+dmPython`，别混用。
- **Python 3.14 兼容性未知**：dmPython 对 Python 3.14 的支持待阶段一逐依赖验证；任一核心依赖不兼容则整体回退 Python 3.13。
- **方言差异大**：达梦与 Oracle 兼容但与 MySQL/PostgreSQL 差异明显，迁移脚本与集成测试单独维护，三库验证通过才算数（见《[Alembic 技术介绍](Alembic技术介绍.md)》）。
- **JSON 支持有限**：达梦 JSON 类型能力有限，ORM 层用跨方言通用类型兜底，不写方言专属 JSON 查询。
- **分页与自增语义**：分页统一 limit/offset 写法；序号语义与 MySQL AUTO_INCREMENT 不同，跨库测试别断言具体值。
- **安装/编译依赖 dpi**：dmPython 编译与运行需要 DM 安装目录（DM_HOME）下的 dpi 头文件与动态库，镜像环境需先准备；Windows 报 DLL load failed 多为 dpi 未找到。
- **商业授权**：开发镜像含试用授权，商业交付必须按客户环境采购商业许可（按套件/核数计费），红线是修改达梦源码或分发其二进制。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| 达梦数据库官网 | https://www.dameng.com/ | 产品信息、下载试用与商业授权入口 |
| 达梦技术文档（生态社区） | https://eco.dameng.com/ | 官方文档中心：安装手册、开发指南、FAQ |
| dmPython 仓库（Gitee） | https://gitee.com/DamengDB/dmPython | 官方 Python 驱动源码与 issue |
| dmPython 安装文档 | https://eco.dameng.com/document/dm/zh-cn/pm/dmpython-installation.html | 驱动编译安装与环境变量（DM_HOME）说明 |
| 达梦 Python 开发指南 | https://eco.dameng.com/document/dm/zh-cn/start/python-development.html | Python 连接达梦的官方入门文档 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：达梦 DM8 与 dmPython 条目 |
| 《[项目规划说明》3.1 节](../../../规划/项目规划说明.md#sel-backend) | 选型说明：dmPython 与 Python 3.14 兼容性验证口径 |
| 《[项目规划说明》11 节](../../../规划/项目规划说明.md#dbcompat) | 数据库兼容：跨方言类型、分页、软删除唯一索引约定 |
| 《[达梦 DM8 部署使用说明](?../../开发服务器/达梦DM8部署使用说明.md》 | 开发服务器 mjbk 上的部署、库与账号细节 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 异步 engine、多数据源与方言兼容层 |
| 《[Alembic 技术介绍](Alembic技术介绍.md)》 | 三套方言迁移脚本的维护与 CI 验证 |
| 《[MySQL 技术介绍](MySQL技术介绍.md)》《[PostgreSQL 技术介绍](PostgreSQL技术介绍.md)》 | 并行支持的另一生产数据库 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
