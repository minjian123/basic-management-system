# basic-management-system

基础管理系统（Base Management System，简称 BMS），主要用作后端管理。支持分布式、集群部署；多租户 SaaS 架构（租户独立库）、SSO 单点登录，内置报表 BI 与移动端 H5。

## 项目状态

- **当前为规划与设计阶段**：技术栈、功能模块、开发计划与验收标准已定案，架构设计（01-31）、概要设计（01-38）、布局设计（01-16）、组件设计与原型设计已就绪，尚无源代码。动手写代码前先读[《项目规划说明》](文档/规划/项目规划说明.html)。
- 开发环境已部署（GitLab CI、三库、开发依赖服务与测试用例平台就绪），部署细节见[《开发服务器部署使用说明》](文档/资料/开发服务器/开发服务器部署使用说明.html)（本地文档）。

## 技术栈概览

| 层面 | 选型 |
| ---- | ---- |
| 后端 | Python 3.14+ / FastAPI / SQLAlchemy 2.0 异步 / Pydantic v2 / Alembic |
| 前端 | Vue 3 + Vite + TypeScript / Element Plus / Vant（移动端 H5 双工程） |
| 数据库 | SQLite（开发测试）/ MySQL 8.x / PostgreSQL 16+ / 达梦 DM8（信创选配） |
| 中间件 | Redis / RocketMQ 5.x / Celery / MinIO / ElasticSearch 8.x / Milvus（阶段十五） |
| 部署 | Docker Compose / nginx / Docker Engine（开发与生产一致） |
| CI/CD | 自托管 GitLab CE + gitlab-runner（Docker executor）+ Renovate |

完整选型、许可与合规说明见[《项目规划说明》](文档/规划/项目规划说明.html)与[《架构设计》](文档/设计/架构设计/01_架构设计_总览.html)。

## 开发环境

开发服务器（常开，承载 GitLab CE 与 CI、三库、开发依赖服务、测试用例平台）与开发机的部署、远程操作与凭据管理见《开发服务器部署使用说明》《开发服务器电源控制使用说明》等本地文档（含内网地址与磁盘规划，不随仓库公开）。

## 文档导航

- **[文档首页](文档/文档首页.html)**：`文档/` 目录全量导航入口

```
文档/
├── 文档首页.html   # 文档全量索引
├── 规划/        # 项目规划说明、开发部署规划
├── 规范/        # 文档生成规范、命名规范、前后端/安全/数据库等规范
├── 资料/        # 部署说明与工具文档
│   ├── 开发服务器/   # 各服务部署使用说明
│   ├── AI/       # graphify、本地多模态（识图/子代理）
│   └── 工具/      # Ubuntu 安装部署、GitLab 迁移
├── 用户文档/    # 用户手写的 md 源文档（项目规划、布局设计、本地资源）
├── 设计/        # 架构设计、概要设计、布局设计、组件设计、原型设计
└── 资源/        # 文档样式等公共资源
```

- [项目规划说明](文档/规划/项目规划说明.html)：技术栈、功能模块、数据表、权限模型、开发计划与验收标准
- [开发部署规划](文档/规划/开发部署规划.html)：开发环境两台机器分工、服务部署、磁盘/端口规划
- [架构设计](文档/设计/架构设计/01_架构设计_总览.html)：总体架构与各子系统设计
- [概要设计](文档/设计/概要设计/01_概要设计_总览.html)：各功能模块详细设计
- [文档生成规范](文档/规范/文档生成规范.html)：AI 生成文档的格式与布局约定
- [Kiwi TCMS 部署使用说明](文档/资料/开发服务器/KiwiTCMS部署使用说明.html)：测试用例管理平台部署与使用（用例库 + 结果归档）

## 知识图谱（graphify）

代码库辅助理解用知识图谱，产物在 `graphify-out/`（`graph.html` 可视化、`graph.json` 数据、`GRAPH_REPORT.md` 报告）。已启用中文查询分词。

- 代码库问题先查图谱：`graphify query "问题"`（关系用 `graphify path`，概念用 `graphify explain`）。
- 代码改动后保持图谱最新：`graphify update .`，然后运行 `python deploy/tools/graphify/localize-graph.py` 收尾（汉化界面 + 生成中文架构图）。
- 安装、排除规则、重建取舍、社区命名等细节见[《graphify 部署与使用说明》](文档/资料/AI/graphify部署使用说明.html)。

## 快速启动

代码就绪后按[《开发部署规划》](文档/规划/开发部署规划.html)第 5 节在开发机启动后端与前端：

```bash
# 后端（backend/）
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 前端（frontend/ 与 frontend-mobile/）
npm ci
npm run dev
```

日常开发流程：`feature/xxx` 分支开发 → push 至 GitLab → Merge Request → CI 通过后合入 main。
