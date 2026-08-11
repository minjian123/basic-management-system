# basic-management-system

基础管理系统（Base Management System，简称 BMS），主要用作后端管理。支持分布式、集群部署；多租户 SaaS 架构（租户独立库）、SSO 单点登录，内置报表 BI 与移动端 H5。

## 项目状态

- **当前为规划阶段**：技术栈、功能模块、开发计划与验收标准已定案，尚无源代码。动手写代码前先读[《项目规划说明》](文档/规划/项目规划说明.md)。
- 开发环境已部署：开发服务器 mjbk（Ubuntu 24.04.4 + Docker，GitLab CI、三库、开发依赖服务全部就绪），详见[《开发服务器部署使用说明》](文档/资料/开发服务器/开发服务器部署使用说明.html)。

## 技术栈概览

| 层面 | 选型 |
| ---- | ---- |
| 后端 | Python 3.14+ / FastAPI / SQLAlchemy 2.0 异步 / Pydantic v2 / Alembic |
| 前端 | Vue 3 + Vite + TypeScript / Element Plus / Vant（移动端 H5 双工程） |
| 数据库 | SQLite（开发测试）/ MySQL 8.x / PostgreSQL 16+ / 达梦 DM8（信创选配） |
| 中间件 | Redis / RocketMQ 5.x / Celery / MinIO / ElasticSearch 8.x / Milvus（阶段十四） |
| 部署 | Docker Compose / nginx / Docker Engine（开发与生产一致） |
| CI/CD | 自托管 GitLab CE + gitlab-runner（Docker executor）+ Renovate |

完整选型、许可与合规说明见[《项目规划说明》](文档/规划/项目规划说明.md)与[《架构设计》](文档/设计/架构设计/01-架构设计.html)。

## 开发环境

- **开发服务器 mjbk**（192.168.0.107，Ubuntu 24.04.4，常开）：GitLab CE（HTTP 8080 + Registry 5050 + SSH 2222）、gitlab-runner、开发依赖服务（Redis/MinIO，Docker Compose）、常驻 MySQL 8 / PostgreSQL 16 / 达梦 DM8 三库、监控与 Milvus（按阶段引入）。
- **开发机 mjpc**（192.168.0.124）：本地编码与运行开发服务器（uv + uvicorn、npm + Vite），日常开发默认 SQLite，内网访问 mjbk 共享服务。
- 远程操作 mjbk：SSH（22，公钥免密），各服务部署与运维详见[《开发服务器部署使用说明》](文档/资料/开发服务器/开发服务器部署使用说明.html)。

## 文档导航

- **[文档首页](文档/文档首页.html)**：`文档/` 目录全量导航入口

```
文档/
├── 索引         # 文档索引（文档首页）
├── 规划/        # 项目规划说明、开发部署规划
├── 规范/        # 文档生成规范、命名规范、后端/前端开发规范
├── 资料/        # 本地资源、Ubuntu 安装部署、graphify、开发服务器部署说明
└── 设计/        # 架构设计、概要设计、布局设计
```

- [项目规划说明](文档/规划/项目规划说明.md)：技术栈、功能模块、数据表、权限模型、开发计划与验收标准
- [开发部署规划](文档/规划/开发部署规划.html)：开发环境两台机器分工、服务部署、磁盘/端口规划
- [架构设计](文档/设计/架构设计/01-架构设计.html)：总体架构与各子系统设计
- [概要设计](文档/设计/概要设计/01-概要设计.html)：各功能模块详细设计
- [文档生成规范](文档/规范/文档生成规范.html)：AI 生成文档的格式与布局约定

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
