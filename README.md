<div align="center">

![Python](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node-22_LTS-5FA04E?logo=nodedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-2F5B7C?logo=sqlalchemy&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5+-42B883?logo=vue.js&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-7-B47159?logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Element Plus](https://img.shields.io/badge/Element_Plus-2.x-364FD1?logo=element&logoColor=white)
![Vant](https://img.shields.io/badge/Vant-4.x-3C8DDE?logo=apacheflink&logoColor=white)
![bpmn-js](https://img.shields.io/badge/bpmn--js-17+-2C7A79)
![Redis](https://img.shields.io/badge/Redis-8+-DC382D?logo=redis&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.4+-4479A1?logo=mysql&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-27+-2496ED?logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2.33+-2496ED?logo=docker&logoColor=white)
![GitLab](https://img.shields.io/badge/GitLab-18+-FC6A21?logo=gitlab&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## 简介

基础管理系统（BMS）是一个面向企业级场景的后端管理系统，支持分布式、集群部署；多租户 SaaS 架构（租户独立库），支持 SSO 单点登录，内置报表 BI 与移动端 H5。

后端基于 FastAPI + SQLAlchemy，前端基于 Vue 3 + Vite（PC 管理端 + 移动端 H5 双工程），通过知识图谱（graphify）辅助代码理解与架构分析。

BMS 作为平台支撑独立业务产品按"平台扩展"复用（产品仓库：biz 企业运营管理、CW 创作系统），业务不入平台，机制见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》。

**技术栈概览**

| 层面 | 技术 |
| --- | --- |
| 后端 | Python 3.14+ · FastAPI · uvicorn · Pydantic v2 · SQLAlchemy 2.0+（异步）· Alembic · Celery · SpiffWorkflow |
| 数据库 / 中间件 | SQLite（开发/测试）· MySQL 8.x · PostgreSQL 16+ · 达梦 DM8（信创选配）· Redis · RocketMQ 5.x · ElasticSearch 8.x · MinIO |
| 前端 | Vue 3.5+ · Vite 7 · TypeScript · Element Plus（PC）/ Vant 4（移动端 H5）· Pinia |
| 工程与质量 | uv（Python 依赖）· npm（前端依赖）· GitLab CI · Renovate · pytest / Vitest / Playwright |
| 部署与运维 | Docker 27+ · Docker Compose 2.33+ · nginx · GitLab CE 18+ · Prometheus / Loki / Grafana / Alertmanager（监控）· Jaeger（链路追踪） |

## 快速启动

> 前置：Python 3.14（uv 管理）、Node 22（nvm 管理）。

```bash
# 后端（端口 8000）
cd backend
uv sync
uv run uvicorn app.main:create_app --factory --port 8000
# 验证：访问 http://127.0.0.1:8000/healthz 返回 {"status":"ok"}

# PC 前端（端口 5173）
cd frontend
npm ci
npm run dev
# 验证：访问 http://127.0.0.1:5173 看到占位页

# 移动端（端口 5174）
cd frontend-mobile
npm ci
npm run dev
# 验证：访问 http://127.0.0.1:5174 看到占位页
```

## 目录结构

```text
bms/
├── README.md                 # 本文件
├── LICENSE                   # MIT 许可
├── .gitignore                # Python / Node / 环境与凭据 / 编辑器 / 图谱产物
├── .editorconfig             # 编辑器统一配置（UTF-8 / LF / 缩进）
├── .gitlab-ci.yml            # CI 流水线定义（GitLab CE）
├── renovate.json             # Renovate 依赖升级配置
├── backend/                  # FastAPI 后端（01 占位，02 初始化，03 分层完成）
│   ├── .python-version       # 固定 Python 版本（3.14）
│   ├── pyproject.toml        # 元数据 + 依赖 + ruff / pyright / pytest 配置
│   ├── uv.lock               # 依赖锁定（必须提交）
│   ├── config.toml           # 配置占位（02-1 填充）
│   ├── alembic.ini           # 迁移配置占位（03-6 填充）
│   ├── alembic/              # 迁移目录占位（03-6 填充）
│   ├── README.md             # 工程说明
│   ├── app/                  # 分层：core / api / models / schemas / services / repositories / db / tasks / ws / i18n
│   ├── tests/                # 测试（与 app 同构：api/core/repositories/services/schemas）
│   ├── benchmarks/           # 微基准（手动执行）
│   └── typings/              # 局部类型存根（sortedcontainers / fakeredis）
├── frontend/                 # Vue 3 + Vite PC 管理端（01 最小占位，04 细化）
│   ├── .nvmrc                # 固定 Node 版本（22）
│   ├── package.json
│   ├── package-lock.json     # 依赖锁定（必须提交）
│   ├── vite.config.ts        # 固定开发端口 5173
│   ├── tsconfig.json         # 及 tsconfig.app.json / tsconfig.node.json
│   ├── index.html
│   ├── README.md             # 工程说明
│   ├── public/favicon.svg
│   └── src/
│       ├── main.ts
│       ├── App.vue           # 占位页面
│       └── vite-env.d.ts
├── frontend-mobile/          # Vue 3 + Vant 移动端 H5（01 最小占位，05 细化）
│   └── …                     # 结构同 frontend，端口固定 5174
├── deploy/                   # 部署配置
│   ├── .env.example          # 凭据模板
│   ├── compose/              # Docker Compose（base / gitlab / kiwi）
│   └── setup/                # 环境安装脚本
├── scripts/                  # 开发期工具链
│   └── tools/                # backup / bg / defect / dsh / gitlab / graphify / reorder-design / vision / winrm / wol / base-check
├── ops/                      # 产品运维脚本（种子数据、备份恢复、租户库迁移，后续阶段填充）
│   └── README.md             # 目录说明
└── bms文档/                  # 项目文档
    ├── 基座文档清单.md        # 通用基座权威清单（产品不复制）
    ├── 文档首页.md            # 全量导航
    ├── 规划/                  # 4篇：项目规划说明、总体项目规划、开发部署规划、平台可扩展性规划
    ├── 规范/                  # 19篇：文档、命名、前后端、数据库、API、安全、测试、日志、评审、国际化、Git、部署发布、原型审查、项目管理、需求/计划/任务文档、英文简称
    ├── 设计/                  # 架构设计 / 概要设计 / 布局设计 / 原型设计 / 组件设计
    ├── 项目/                  # 按阶段的项目基线：需求 / 计划 / 任务（00_准备期、01_项目骨架 …）
    ├── 资料/                  # 共享基础设施资料（开发服务器 / 开发机 / 工具 / AI / 知识档案）
    ├── 用户文档/              # 本地资源（机器凭据等，已 gitignore）
    └── 资源/                  # 文档共享样式与 mermaid 资产
```

> 凭据统一存 `deploy/.env`（已 gitignore，模板见 `deploy/.env.example`）。
>
> `AGENTS.md`、`.opencode` 与知识图谱 `graphify-out/` 位于**工作区根**（工作区模型见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》4.3），不在本仓库内。

## 文档导航

> 全部文档位于 `bms文档/` 目录，入口为《[文档首页](bms文档/文档首页.md)》（全量导航）。正文以 Markdown 为载体，线框图/可交互原型保留 `.html` 资产。

| 目的 | 文档 |
| --- | --- |
| 快速上手（技术栈、功能范围、开发计划） | [规划/项目规划说明](bms文档/规划/项目规划说明.md) |
| 开发环境部署方案（分工、服务清单、端口与磁盘规划） | [规划/开发部署规划](bms文档/规划/开发部署规划.md) |
| 平台可扩展性（三层模型、工作区模型） | [规划/平台可扩展性规划](bms文档/规划/平台可扩展性规划.md) |
| 全量文档导航 | [文档首页](bms文档/文档首页.md) |
| 文档格式与检查清单 | [规范/文档生成规范](bms文档/规范/文档生成规范.md) |
| 命名约定（代码 / 数据库 / API / 基础设施） | [规范/命名规范](bms文档/规范/命名规范.md) |
| 原型审查 | [规范/原型审查规范](bms文档/规范/原型审查规范.md) |
| 开发服务器环境部署 | [资料/开发服务器/开发服务器部署使用说明总览](bms文档/资料/开发服务器/linux/开发服务器部署使用说明总览.md) |
| 技术栈知识档案（选型背景） | [资料/知识档案/技术栈知识档案总览](bms文档/资料/知识档案/技术栈知识档案总览.md) |
| 架构设计入口 | [设计/架构设计/01_总览](bms文档/设计/架构设计/01_架构设计_总览.md) |
