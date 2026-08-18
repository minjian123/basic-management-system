# basic-management-system

基础管理系统（Base Management System，简称 BMS），主要用作后端管理。支持分布式、集群部署；多租户 SaaS 架构（租户独立库）、SSO 单点登录，内置报表 BI 与移动端 H5。

## 项目状态

- **当前为规划与设计阶段**：技术栈、功能模块、开发计划与验收标准已定案，架构设计（01-31）、概要设计（01-38）、布局设计（01-16）、组件设计与原型设计已就绪，尚无源代码。动手写代码前先读[《项目规划说明》](文档/规划/项目规划说明.html)。
- 开发环境已部署：开发服务器 mjbk（Ubuntu 24.04.4 + Docker，GitLab CI、三库、开发依赖服务全部就绪），详见[《开发服务器部署使用说明》](文档/资料/开发服务器/开发服务器部署使用说明.html)。

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

- **开发服务器 mjbk**（192.168.0.107，Ubuntu 24.04.4，常开）：GitLab CE（HTTP 8080 + Registry 5050 + SSH 2222）、gitlab-runner、开发依赖服务（Redis/MinIO，Docker Compose）、常驻 MySQL 8 / PostgreSQL 16 / 达梦 DM8 三库、监控与 Milvus（按阶段引入）。磁盘分工：512G 系统盘（`/`）+ 2T NVMe SSD（`/mnt/ssd2t`，Docker data-root 与 GitLab 数据）+ 1T HDD（`/mnt/data`，备份与系统快照）。
- **开发机 mjpc**（192.168.0.124）：本地编码与运行开发服务器（uv + uvicorn、npm + Vite），日常开发默认 SQLite，内网访问 mjbk 共享服务。
- 远程操作 mjbk：SSH（22，公钥免密），各服务部署与运维详见[《开发服务器部署使用说明》](文档/资料/开发服务器/开发服务器部署使用说明.html)；远程唤醒/关机见[《开发服务器电源控制使用说明》](文档/资料/工具/开发服务器电源控制使用说明.html)。

## 文档导航

- **[文档首页](文档/文档首页.html)**：`文档/` 目录全量导航入口

```
文档/
├── 文档首页.html   # 文档全量索引
├── 规划/        # 项目规划说明、开发部署规划
├── 规范/        # 文档生成规范、命名规范、前后端/安全/数据库等规范
├── 资料/        # 部署说明与工具文档
│   ├── 开发服务器/   # 各服务部署使用说明
│   ├── AI/       # graphify、视觉识图
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

日常开发流程：`feature/xxx` 分支开发 → push 至 mjbk GitLab → Merge Request → CI 通过后合入 main。
