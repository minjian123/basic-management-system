<div align="center">

![Python](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node-22_LTS-5FA04E?logo=nodedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-2F5B7C?logo=sqlalchemy&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5+-42B883?logo=vue.js&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-B47159?logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white)
![Element Plus](https://img.shields.io/badge/Element_Plus-2.14-364FD1?logo=element&logoColor=white)
![Vant](https://img.shields.io/badge/Vant-4.10-3C8DDE?logo=apacheflink&logoColor=white)
![bpmn-js](https://img.shields.io/badge/bpmn--js-18+-2C7A79)
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

后端基于 FastAPI + SQLAlchemy，前端基于 Vue 3 + Vite（PC 管理端 + 移动端 H5 双工程）。

BMS 作为平台支撑独立业务产品按"平台扩展"复用（产品仓库：biz 企业运营管理、mdm 主数据管理、CW 创作系统等），业务不入平台，机制见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》；平台内部模块与产品以**微服务为目标架构**（从一开始分布式构建、每服务独立库），见《[微服务演进规划](bms文档/规划/微服务演进规划.md)》。

**技术栈概览**

| 层面 | 技术 |
| --- | --- |
| 后端 | Python 3.14+ · FastAPI · uvicorn · Pydantic v2 · SQLAlchemy 2.0+（异步）· Alembic · structlog · Celery · SpiffWorkflow |
| 数据库 / 中间件 | SQLite（开发/测试）· MySQL 8.4 · PostgreSQL 16 · 达梦 DM8（信创选配）· Redis 8 · RocketMQ 5.x · ElasticSearch 8.x · MinIO |
| 前端 | Vue 3.5+ · Vite 8 · TypeScript 6 · Vue Router 4 · Pinia · vue-i18n · Element Plus（PC）/ Vant 4（移动端 H5）· Axios |
| 工程与质量 | uv（Python 依赖）· pnpm（前端依赖）· ESLint / Prettier · openapi-typescript（契约生成）· GitLab CI · pytest / Vitest / Playwright |
| 部署与运维 | Docker 27+ · Docker Compose 2.33+ · nginx · GitLab CE 18+ · Prometheus / Loki / Grafana / Alertmanager（监控）· OpenTelemetry / Jaeger（链路追踪） |

## 项目状态

> 阶段内容与完成标准见《[总体项目规划](bms文档/规划/总体项目规划.md)》，范围与验收口径见《[项目规划说明](bms文档/规划/项目规划说明.md)》；各阶段文档入口见《[文档首页](bms文档/文档首页.md)》「项目文档」节。

- **当前阶段**：**阶段七 RBAC 基础模块**（进行中；阶段一 ~ 阶段六已收口）。进度明细以**各阶段计划表为唯一落点**（见下），本文件不承载进度。
- **阶段进度与交付**：各阶段需求 / 任务 / 计划基线见《[文档首页](bms文档/文档首页.md)》「项目文档」节；阶段内容与完成标准见《[总体项目规划](bms文档/规划/总体项目规划.md)》。
- **阶段计划（进度唯一落点）**：阶段一《[项目骨架计划](bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md)》· 阶段二《[后端基座与服务化地基计划](bms文档/项目/02_后端基座与服务化地基/计划/01_计划_后端基座与服务化地基.md)》· 阶段三《[后端插件化计划](bms文档/项目/03_后端插件化/计划/01_计划_后端插件化.md)》· 阶段四《[前端组件库计划](bms文档/项目/04_前端组件库/计划/01_计划_前端组件库.md)》· 阶段五《[前端插件化计划](bms文档/项目/05_前端插件化/计划/01_计划_前端插件化.md)》· 阶段六《[认证与安全计划](bms文档/项目/06_认证与安全/计划/01_计划_认证与安全.md)》· 阶段七《[RBAC 基础模块计划](bms文档/项目/07_RBAC基础模块/计划/01_计划_RBAC基础模块.md)》。

- 移动端 H5 宿主与渲染插件（阶段十七）、前端全页面（阶段十五）、平台自身页面迁移为模块与生产模块部署形态随后续阶段交付。
- 后端基座与机制类的交付形态与遗留归口见《[项目骨架计划](bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md)》「后续阶段待办」节。
- **可本地起服务**：本机裸跑全套（后端三服务 + PC 前端宿主），见「快速启动」节；后端 `/healthz`（存活）与 `/readyz`（就绪）。

## 快速启动

> 前置：Python 3.14（uv 管理）、Node 22（nvm 管理）。依赖**不进仓库树**：前端 node_modules 与后端 .venv 均外置到本地依赖仓（口径见《[开发机部署使用说明总览](bms文档/资料/开发机/开发机部署使用说明总览.md)》）。

**推荐：本机裸跑全套（后端三服务 + PC 宿主；无需 Docker / 无需开发服务器）**

```bash
# 后端三服务（identity / tenant / platform，绑 127.0.0.2 / 4 / 5 别名，统一端口 8000；org 已退役归 mdm 产品）
bash scripts/tools/dev/本地全套.sh up        # 启动（幂等 + 有界起停；自愈 hosts 别名与开发密钥）
bash scripts/tools/dev/本地全套.sh seed      # 建演示租户与管理员账号（口令见《本地资源》，不写入本文件）
bash scripts/tools/dev/本地全套.sh status    # 进程与 /healthz、/readyz 一览
bash scripts/tools/dev/本地全套.sh logs      # 打印日志尾部（追看用 tail -f）
bash scripts/tools/dev/本地全套.sh down      # 停止（或 stop <服务> 单独腾位给调试）
# 验证：GET http://127.0.0.1:8000/healthz 返回 {"status":"ok"}；/readyz 为就绪检查

# PC 前端宿主（端口 5173）
pnpm install --frozen-lockfile               # 前端依赖在工作区根（bms/）统一安装
pnpm --filter @bms/desktop dev
```

**底线：单服务启动**

```bash
cd backend
uv sync
uv run uvicorn bms_platform.asgi:app --port 8000
uv run pytest          # 全量用例（含 Kiwi TCMS 用例编号标注）
```

**依赖外置维护**（`pnpm install` 前必须先还原，装完恢复外置态）：

```bash
bash scripts/tools/deps/还原依赖.sh          # 外置态 → 还原为可安装态
bash scripts/tools/deps/外置依赖.sh          # 安装完成后恢复外置态（推荐常驻）
```

**移动端 H5**（端口 5174）—— 随阶段十七交付，当前工程未建（命令预留）：`cd frontend/apps/mobile && pnpm run dev`。

本地门禁（与 CI 同口径；先 `cd backend`）：

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright   # 依赖外置态下 pyright 可能不可用，交 CI 兜底
uv run pytest -q --cov=bms_core --cov=bms_platform --cov-branch --cov-fail-under=70    # 覆盖率门禁 ≥ 70%
uv run python -m ops.check_modules                             # 模块注册清单校验
cd ../frontend/apps/desktop && pnpm run lint && pnpm run test:cov && pnpm run build && pnpm run budget   # 宿主（覆盖率 ≥ 70%、体积预算门禁）
cd ../../.. && python3 scripts/tools/base-check/check-base.py  # 基座自检（须在仓库根）
python3 scripts/tools/base-check/check-links.py                # 链接自洽校验（本地手工跑，不挂 CI）
python3 scripts/tools/check-docs/check-status.py --stage <阶段> --strict   # 需求 / 任务 / 计划状态一致性
python3 scripts/tools/preflight/check-preflight.py --fast      # 推送前预检（秒级；只跑 --fast，不跑全量）
python3 scripts/tools/governance/collect_metrics.py           # 阶段度量与用例统计（阶段末）
python3 scripts/tools/governance/review_stage.py              # 阶段末复盘清单
```

> 本地测试只跑**受变更影响的定向用例**；全量与集成验证交 CI 按需触发（口径见《[AI开发规范](bms文档/规范/AI开发规范.md)》）。

## 目录结构

> 只列顶层与关键文件；各工程内部细节见其自带 `README.md`，文档入口见《[文档首页](bms文档/文档首页.md)》。

```text
bms/
├── README.md                    # 本文件
├── LICENSE                      # MIT 许可
├── .editorconfig                # 编辑器统一配置（UTF-8 / LF / 缩进）
├── .gitignore                   # Python / Node / 环境与凭据 / 编辑器 / 产物
├── .gitlab-ci.yml               # CI 流水线定义（GitLab CE）
├── renovate.json                # Renovate 配置（已置 enabled:false，停用自动升级）
├── backend/                     # FastAPI 后端工作区（uv workspace）
│   ├── libs/bms_core/           # 共享基座库（包 bms_core：core / api / db / 各横切能力域）
│   ├── services/                # 各服务工程（identity / tenant / platform / txn / notification / file / search / report / ai）
│   ├── alembic/                 # 数据库迁移（按「服务 × 数据源」分链）
│   └── ops/                     # 运维脚本（模块检查 / 租户库初始化 / 批量迁移 / 测试库流程）
├── frontend/                    # 前端单仓多包（pnpm workspace）
│   ├── packages/                # 基座多包：core / vue / ui-ep / api-types（ui-vant 随阶段十七）
│   ├── apps/                    # 宿主应用：desktop（PC 管理端）/ mobile（随阶段十七交付）
│   ├── modules/                 # 运行时模块（demo / sample / slot-sample 等）
│   ├── scripts/                 # 模块产物发布与托管脚本（release-module / serve-module-releases）
│   └── releases/                # 模块产物归档（不入库；仅 release-log.{json,md} 入库）
├── deploy/                      # 部署配置（ci / compose / contracts / events / gateway / keycloak / observability / postgres / setup / boundaries 等）
├── scripts/tools/               # 开发期工具链（base-check / check-docs / deps / dev / preflight / governance 等）
├── ops/                         # 产品运维脚本（种子数据 / 备份恢复 / 租户库迁移，后续阶段填充）
├── package.json                 # 前端根脚本（core:check / vue:check / ui-ep:check / api-types:gen 等）
├── pnpm-workspace.yaml          # 前端 workspace 收敛（frontend/{packages,apps,modules}/*）
├── pnpm-lock.yaml               # 单一锁文件（必须提交）
├── tsconfig.base.json           # 前端 TypeScript 基线
├── bms文档/                     # 项目文档
│   ├── 基座文档清单.md           # 通用基座权威清单（产品不复制）
│   ├── 后端基类清单.md           # 后端基类权威清单
│   ├── 前端基类清单.md           # 前端基类权威清单
│   ├── 文档首页.md               # 全量导航
│   ├── 规划/ · 规范/ · 设计/     # 规划（5 篇）/ 规范（22 篇）/ 架构 · 概要 · 数据库 · 布局 · 原型 · 组件设计
│   ├── 项目/                    # 按阶段的项目基线（00_准备期 ~ 07_RBAC基础模块）：需求 / 计划 / 任务
│   ├── 资料/                    # 共享基础设施资料（开发服务器 / 开发机 / 工具 / AI / 知识档案）
│   ├── 用户文档/                # 本地资源（机器凭据等，已 gitignore）
│   └── 资源/                    # 文档共享样式与 mermaid 资产
├── test文档 -> ../test/test文档   # 测试资产仓软链（工作区并置，不入库）
└── mdm文档 -> ../mdm/mdm文档      # 主数据文档软链（工作区并置，不入库）
```

> 凭据统一存 `deploy/.env`（已 gitignore，模板见 `deploy/.env.example`）。
>
> `AGENTS.md` 与 `.opencode/` 位于**工作区根**（工作区模型见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》4.3），不在本仓库内。
>
> 后端跨阶段基座与能力域基座（cache ~ ws 等）当前多为**占位契约**（Null 实现），真实实现随对应阶段回补；分层、职责与状态以《[后端基类清单](bms文档/后端基类清单.md)》为准（前端对应《[前端基类清单](bms文档/前端基类清单.md)》）。

## 文档导航

> 全部文档位于 `bms文档/` 目录，入口为《[文档首页](bms文档/文档首页.md)》（全量导航）。正文以 Markdown 为载体，线框图/可交互原型保留 `.html` 资产。

| 目的 | 文档 |
| --- | --- |
| 规划主文件（技术栈、功能范围、验收口径、AI 治理与变更管理、开发计划） | [规划/项目规划说明](bms文档/规划/项目规划说明.md) |
| 总体规划与阶段计划 | [规划/总体项目规划](bms文档/规划/总体项目规划.md) |
| 开发环境部署方案（分工、服务清单、端口与磁盘规划） | [规划/开发部署规划](bms文档/规划/开发部署规划.md) |
| 平台可扩展性（三层模型、工作区模型） | [规划/平台可扩展性规划](bms文档/规划/平台可扩展性规划.md) |
| 微服务目标架构（服务清单、服务化地基、演进路线） | [规划/微服务演进规划](bms文档/规划/微服务演进规划.md) |
| 阶段一 需求基线 | [项目/01_项目骨架/需求/00_需求_项目骨架](bms文档/项目/01_项目骨架/需求/00_需求_项目骨架.md) |
| 阶段一 任务基线（需求域 01 ~ 04） | [项目/01_项目骨架/任务/01_工程骨架](bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架.md) · [04_CI与阶段验收](bms文档/项目/01_项目骨架/任务/04_CI与阶段验收/04_CI与阶段验收.md) |
| 阶段一 计划 | [项目/01_项目骨架/计划/01_计划_项目骨架](bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md) |
| **阶段测试报告（阶段一）** | [项目/01_项目骨架/01_测试报告_项目骨架](bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md) |
| 阶段二 需求基线（29 条，后端基座与服务化地基） | [项目/02_后端基座与服务化地基/需求/00_需求_后端基座与服务化地基](bms文档/项目/02_后端基座与服务化地基/需求/00_需求_后端基座与服务化地基.md) |
| 阶段二 任务与计划基线 | [任务/01 后端基座真实实现](bms文档/项目/02_后端基座与服务化地基/任务/01_后端基座真实实现/01_后端基座真实实现.md) · [计划](bms文档/项目/02_后端基座与服务化地基/计划/01_计划_后端基座与服务化地基.md) |
| 阶段三 需求基线 | [项目/03_后端插件化/需求/00_需求_后端插件化](bms文档/项目/03_后端插件化/需求/00_需求_后端插件化.md) |
| 阶段三 任务基线（需求域 01 ~ 05） | [任务/01_插件化基座](bms文档/项目/03_后端插件化/任务/01_插件化基座/01_插件化基座.md) · [计划](bms文档/项目/03_后端插件化/计划/01_计划_后端插件化.md) |
| **阶段测试报告（阶段三）** | [项目/03_后端插件化/01_测试报告_后端插件化](bms文档/项目/03_后端插件化/01_测试报告_后端插件化.md) |
| 阶段四 需求基线 | [项目/04_前端组件库/需求/00_需求_前端组件库](bms文档/项目/04_前端组件库/需求/00_需求_前端组件库.md) |
| 阶段四 任务与计划 | [阶段索引](bms文档/项目/04_前端组件库/README.md) · [计划](bms文档/项目/04_前端组件库/计划/01_计划_前端组件库.md) |
| **阶段测试报告（阶段四）** | [项目/04_前端组件库/01_测试报告_前端组件库](bms文档/项目/04_前端组件库/01_测试报告_前端组件库.md) |
| 阶段四 合规审计（首审 / 复审） | [审计（首审）](bms文档/项目/04_前端组件库/审计/01_审计_前端合规审计（首审）.md) · [审计（复审）](bms文档/项目/04_前端组件库/审计/02_审计_前端合规审计（复审）.md) |
| 阶段五 需求 / 任务 / 计划基线 | [需求总览](bms文档/项目/05_前端插件化/需求/00_需求_前端插件化.md) · [任务基线](bms文档/项目/05_前端插件化/任务/01_扩展点与装配/01_扩展点与装配.md) · [计划](bms文档/项目/05_前端插件化/计划/01_计划_前端插件化.md) |
| **阶段测试报告（阶段五）** | [项目/05_前端插件化/01_测试报告_前端插件化](bms文档/项目/05_前端插件化/01_测试报告_前端插件化.md) |
| 阶段六 需求基线（认证与安全） | [项目/06_认证与安全/需求/00_需求_认证与安全](bms文档/项目/06_认证与安全/需求/00_需求_认证与安全.md) |
| 阶段六 任务与计划基线 | [任务/01 认证与会话](bms文档/项目/06_认证与安全/任务/01_认证与会话/01_认证与会话.md) · [计划](bms文档/项目/06_认证与安全/计划/01_计划_认证与安全.md) |
| **阶段测试报告（阶段六）** | [项目/06_认证与安全/01_测试报告_认证与安全](bms文档/项目/06_认证与安全/01_测试报告_认证与安全.md) |
| 阶段七 需求 / 任务 / 计划基线 | [需求总览](bms文档/项目/07_RBAC基础模块/需求/00_需求_RBAC基础模块.md) · [任务基线](bms文档/项目/07_RBAC基础模块/任务/01_插件化挂接/01_插件化挂接.md) · [计划](bms文档/项目/07_RBAC基础模块/计划/01_计划_RBAC基础模块.md) |
| 全量文档导航 | [文档首页](bms文档/文档首页.md) |
| 通用基座文件权威清单（产品引用口径） | [基座文档清单](bms文档/基座文档清单.md) |
| 后端基类体系（基类清单 + 强制用法） | [后端基类清单](bms文档/后端基类清单.md) · [规范/后端开发规范](bms文档/规范/后端开发规范.md) |
| 前端基类体系（基类清单 + 强制用法） | [前端基类清单](bms文档/前端基类清单.md) · [规范/前端开发规范](bms文档/规范/前端开发规范.md) |
| 文档格式与检查清单 | [规范/文档生成规范](bms文档/规范/文档生成规范.md) |
| 命名约定（代码 / 数据库 / API / 基础设施） | [规范/命名规范](bms文档/规范/命名规范.md) |
| 测试分层与缺陷管理 | [规范/测试规范](bms文档/规范/测试规范.md) |
| 原型审查 | [规范/原型审查规范](bms文档/规范/原型审查规范.md) |
| 开发服务器环境部署 | [资料/开发服务器/开发服务器部署使用说明总览](bms文档/资料/开发服务器/linux/开发服务器部署使用说明总览.md) |
| 开发机环境与 AI 工具（CodeBuddy / WorkBuddy / opencode 等） | [资料/开发机/开发机部署使用说明总览](bms文档/资料/开发机/开发机部署使用说明总览.md) |
| 技术栈知识档案（选型背景） | [资料/知识档案/技术栈知识档案总览](bms文档/资料/知识档案/技术栈知识档案总览.md) |
| 架构设计入口 | [设计/架构设计/01_总览](bms文档/设计/架构设计/01_架构设计_总览.md) |
| 概要设计入口 | [设计/概要设计/01_总览](bms文档/设计/概要设计/01_概要设计_总览.md) |
| 数据库设计入口 | [设计/数据库设计/01_总览](bms文档/设计/数据库设计/01_数据库设计_总览.md) |
