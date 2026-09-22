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

BMS 作为平台支撑独立业务产品按"平台扩展"复用（产品仓库：biz 企业运营管理、CW 创作系统），业务不入平台，机制见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》；平台内部模块与产品以**微服务为目标架构**（从一开始分布式构建、每服务独立库），见《[微服务演进规划](bms文档/规划/微服务演进规划.md)》。

**技术栈概览**

| 层面 | 技术 |
| --- | --- |
| 后端 | Python 3.14+ · FastAPI · uvicorn · Pydantic v2 · SQLAlchemy 2.0+（异步）· Alembic · structlog · Celery · SpiffWorkflow |
| 数据库 / 中间件 | SQLite（开发/测试）· MySQL 8.4 · PostgreSQL 16 · 达梦 DM8（信创选配）· Redis 8 · RocketMQ 5.x · ElasticSearch 8.x · MinIO |
| 前端 | Vue 3.5+ · Vite 8 · TypeScript 6 · Vue Router 4 · Pinia · vue-i18n · Element Plus（PC）/ Vant 4（移动端 H5）· Axios |
| 工程与质量 | uv（Python 依赖）· npm（前端依赖）· ESLint / Prettier · openapi-typescript（契约生成）· GitLab CI · Renovate · pytest / Vitest / Playwright |
| 部署与运维 | Docker 27+ · Docker Compose 2.33+ · nginx · GitLab CE 18+ · Prometheus / Loki / Grafana / Alertmanager（监控）· OpenTelemetry / Jaeger（链路追踪） |

## 项目状态

> 阶段划分与验收口径见《[项目规划说明](bms文档/规划/项目规划说明.md)》「开发计划与验收标准」节；工期、里程碑与甘特图见《[总体项目规划](bms文档/规划/总体项目规划.md)》（19 个阶段：Alpha 阶段一~十 / Beta 阶段十一~十五 / GA 阶段十六~十九）。

- **微服务目标架构已定（2026-09-22）**：平台内部模块与产品（biz / cw）全服务化、从一开始分布式构建（逻辑多服务 + 物理单机多容器、每服务独立库）；服务化地基并入**阶段二（后端基座与服务化地基）**，技术选型与演进路线见《[微服务演进规划](bms文档/规划/微服务演进规划.md)》，选型对比见知识档案[微服务 · 12 选型对比（BMS）](bms文档/资料/知识档案/微服务/12_微服务_选型对比.md)。

- **阶段一（项目骨架，含后端基座体系）已完成（2026-09-15 起，2026-09-20 收口，184h）**：69 条需求闭环（工程骨架 6 / 后端基座 56 / 后端基础能力 3 / CI 与阶段验收 4）；**M1 门禁达标**（骨架 + 基座体系（占位口径）可用），逐项结论与证据索引见《[阶段测试报告](bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md)》与《[需求总览](bms文档/项目/01_项目骨架/需求/00_需求_项目骨架.md)》「M1 验收门禁」表。
- **阶段三（后端插件化）已完成（2026-09-15）**：11 条需求全部闭环，M3 门禁 8/8 达标，[阶段测试报告](bms文档/项目/03_后端插件化/01_测试报告_后端插件化.md)归档（Kiwi 529 ~ 534、565 ~ 568、651 / 652 / 655、661 ~ 664、675 ~ 678）。
- **阶段四（前端组件库）已完成（2026-09-21，M4 达成）**：40 条需求 / 41 个任务 / 846h 全部收口——前端基类体系（固定三段 / 组件根 / 能力基类族 / 组件基类族 / 体系机制）与八类组件（基础 / 布局 / 容器 / 基础控件 / 字段 / 展示 / 交互）及微前端骨架起步交付；**阶段索引**见《[前端组件库](bms文档/项目/04_前端组件库/README.md)》，**阶段测试报告**见《[前端组件库测试报告](bms文档/项目/04_前端组件库/01_测试报告_前端组件库.md)》（160 文件 / 2054 用例全绿、宿主语句覆盖 86.79%、首屏 127.5 KB），**合规审计**见[首审](bms文档/项目/04_前端组件库/审计/01_审计_前端合规审计（首审）.md)与[复审](bms文档/项目/04_前端组件库/审计/02_审计_前端合规审计（复审）.md)。
- **阶段五（前端插件化）需求、任务与计划基线已建（2026-09-21），阶段未开工**：需求 8 条 / 4 域见《[需求总览](bms文档/项目/05_前端插件化/需求/00_需求_前端插件化.md)》，任务 8 项 / 132h 见《[任务基线](bms文档/项目/05_前端插件化/任务/01_扩展点与装配/01_扩展点与装配.md)》，排期与 M5 门禁见《[前端插件化计划](bms文档/项目/05_前端插件化/计划/01_计划_前端插件化.md)》。
- 阶段二（后端基座与服务化地基）待启动；移动端 H5 宿主与渲染插件（阶段十七）、前端全页面（阶段十五）随后续阶段交付，当前工程未建。
- 阶段一交付的后端基座与机制类当前为**接口占位**（应用可启动、依赖注入可解析、占位可断言），真实实现随**阶段二 后端基座与服务化地基**回补；待办逐条登记于《[项目骨架计划](bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md)》「后续阶段待办」节。
- **阶段二（后端基座与服务化地基）需求 / 任务 / 计划基线已建（2026-09-22）**：29 条需求 / 10 域；29 子任务 / 256h（域一~十）；排期 2026-09-22 起 **8 周**（工期由原基线 4 周重估）。见《[需求总览](bms文档/项目/02_后端基座与服务化地基/需求/00_需求_后端基座与服务化地基.md)》《[任务基线](bms文档/项目/02_后端基座与服务化地基/任务/01_后端基座真实实现/01_后端基座真实实现.md)》《[计划](bms文档/项目/02_后端基座与服务化地基/计划/01_计划_后端基座与服务化地基.md)》。
- 可本地起服务：后端 `/healthz`（存活）与 `/readyz`（就绪）+ PC 前端页面（`frontend/apps/desktop`）；详细进度见《[文档首页](bms文档/文档首页.md)》第 5 节「项目文档」。

## 快速启动

> 前置：Python 3.14（uv 管理）、Node 22（nvm 管理）。

```bash
# 后端（端口 8000；默认 dev 环境，可用 BMS_ENV 切换 test / prod）
cd backend
uv sync
uv run uvicorn app.asgi:app --port 8000
# 验证：GET http://127.0.0.1:8000/healthz 返回 {"status":"ok"}；/readyz 为就绪检查
uv run pytest          # 全量用例（含 Kiwi TCMS 用例编号标注）

# PC 前端（端口 5173）
cd frontend/apps/desktop
npm ci
npm run dev
npm run test           # Vitest 冒烟

# 移动端 H5（端口 5174）—— 随阶段十七交付，当前工程未建（命令预留）
# cd frontend/apps/mobile && npm ci && npm run dev && npm run test
```

本地门禁（与 CI 同口径；先 `cd backend`）：

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q --cov=app --cov-branch --cov-fail-under=70    # 覆盖率门禁 ≥ 70%
uv run python -m ops.check_modules                             # 模块注册清单校验
cd ../frontend/apps/desktop && npm run lint && npm run test:cov && npm run build && npm run budget   # 移动端：cd ../frontend/apps/mobile（覆盖率 ≥ 70%、体积预算门禁）
cd .. && python3 scripts/tools/base-check/check-base.py        # 基座自检（须在仓库根）
python3 scripts/tools/base-check/check-links.py                # 链接自洽校验（本地手工跑，不挂 CI）
python3 scripts/tools/check-docs/check-status.py              # 需求 / 任务 / 计划状态一致性
python3 scripts/tools/governance/collect_metrics.py           # 阶段度量与用例统计（阶段末）
python3 scripts/tools/governance/review_stage.py              # 阶段末复盘清单
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
├── .vscode/                  # 编辑器共享配置（Python 解释器 / 推荐扩展）
├── backend/                  # FastAPI 后端（阶段一：工程骨架与后端基座已交付，基础能力收尾）
│   ├── .python-version       # 固定 Python 版本（3.14）
│   ├── .env.example          # BMS_ 应用键模板（复制为 .env 填值，密钥留空）
│   ├── pyproject.toml        # 元数据 + 依赖 + ruff / pyright / pytest 配置
│   ├── uv.lock               # 依赖锁定（必须提交）
│   ├── config.toml           # 配置基线（分区与关键键，不含密钥）
│   ├── config.dev.toml       # dev 环境覆盖（日志 console / CORS 放行）
│   ├── config.test.toml      # test 环境覆盖（日志 json / CORS 空）
│   ├── config.prod.toml      # prod 环境覆盖（日志 json / CORS 空）
│   ├── alembic.ini           # 迁移配置（env.py，表结构随落库阶段填充）
│   ├── alembic/              # 迁移目录（versions 置空）
│   ├── README.md             # 工程说明
│   ├── typings/              # 局部类型存根（sortedcontainers / fakeredis）
│   ├── benchmarks/           # 微基准（手动执行、CI 不跑）
│   ├── ops/                  # 运维脚本（模块检查 / 租户库初始化 / 批量迁移）
│   ├── app/                  # 应用代码（分层与基类体系见《后端基类清单》）
│   │   ├── main.py           # 应用工厂 create_app：中间件 / 异常处理 / 路由 / 能力域装配
│   │   ├── core/             # L0 根基类 · 集合体系（有序 / 并发 / Redis）· 中间层基类 · core 横切（配置 / 异常 / 安全 / 日志 / 序列化 / 锁 / 雪花 ID / 上下文 / 资源）
│   │   ├── api/              # 聚合路由（demo / modules / health）+ 依赖 / 中间件 / 异常处理器
│   │   ├── models/           # ORM 模型：BaseModel + platform / system / demo
│   │   ├── repositories/     # 仓储基类（契约 / 内存 / 作用域 / DB 骨架）+ demo 仓储
│   │   ├── schemas/          # 契约基类 BaseSchema + 分页 / 排序 / 统一响应
│   │   ├── services/         # 服务基类（含事务扩展）/ 模块注册表 / demo 服务
│   │   ├── db/               # 数据访问底座（引擎 / 会话 / 读写路由 / 租户 / 引擎注册表 / 工作单元）
│   │   ├── cache/            # 缓存 Region 分域（跨阶段基座）
│   │   ├── scope/            # 数据范围注入（跨阶段基座）
│   │   ├── sharding/         # 分片路由（跨阶段基座）
│   │   ├── events/           # 事件发布 / 消费（跨阶段基座）
│   │   ├── tasks/            # Celery 任务基类（跨阶段基座）
│   │   ├── audit/            # 审计捕获 + 哈希链
│   │   ├── archive/          # 归档策略 / 查询路由
│   │   ├── captcha/          # 图形验证码
│   │   ├── circuit/          # 熔断器
│   │   ├── dashboard/        # 工作台卡片注册表
│   │   ├── fallback/         # 降级策略
│   │   ├── fieldtype/        # 字段类型注册表（动态表单）
│   │   ├── health/           # 健康检查项注册表（/readyz 聚合）
│   │   ├── i18n/             # 多语言翻译
│   │   ├── idempotency/      # 幂等去重
│   │   ├── idp/              # 外部身份源（OIDC / CAS）
│   │   ├── llm/              # LLM 适配（对话 / 向量 / OCR）
│   │   ├── lock/             # 分布式锁
│   │   ├── masking/          # 数据脱敏
│   │   ├── metrics/          # 指标采集
│   │   ├── notify/           # 通知渠道（站内信 / 邮件 / 短信）
│   │   ├── oauth/            # 开放接口服务端 / scope 校验
│   │   ├── outbound/         # 出站 HTTP / Webhook
│   │   ├── password/         # 密码策略
│   │   ├── permission/       # 权限校验
│   │   ├── query/            # 数据查询提供者注册表
│   │   ├── ratelimit/        # 限流
│   │   ├── replay/           # 防重放
│   │   ├── search/           # 全文检索索引
│   │   ├── session/          # 会话存储
│   │   ├── storage/          # 对象存储
│   │   ├── tracing/          # 链路追踪
│   │   ├── transfer/         # 导入导出
│   │   ├── workflow/         # 工作流引擎适配
│   │   └── ws/               # 实时推送
│   └── tests/                # 测试（与 app 同构 + crosscut / ops / integration）
├── frontend/                     # 前端单仓多包（与 backend/ 对称：apps 宿主 + packages 基座）
│   ├── apps/desktop/                 # Vue 3 + Vite PC 管理端（Element Plus + Router + Pinia + i18n；消费 @bms/* 新体系）
│   │   ├── .npmrc                # npmmirror 源 + legacy-peer-deps
│   │   ├── .nvmrc                # 固定 Node 版本（22）
│   │   ├── .env.development      # VITE_API_BASE=/api
│   │   ├── eslint.config.js      # ESLint flat config
│   │   ├── .prettierrc.json
│   │   ├── vitest.config.ts
│   │   ├── package.json
│   │   ├── package-lock.json     # 依赖锁定（必须提交）
│   │   ├── vite.config.ts        # 固定开发端口 5173 + @ / @bms/* 别名 + 分包 + 代理
│   │   ├── tsconfig.json         # 及 tsconfig.app.json / tsconfig.node.json（@bms/* paths）
│   │   ├── index.html
│   │   ├── README.md             # 工程说明
│   │   ├── public/favicon.svg
│   │   ├── src/
│   │   │   ├── main.ts           # 挂载 router / pinia / i18n + ui-ep 装配 + v-perm
│   │   │   ├── App.vue           # 路由出口
│   │   │   ├── adapters/         # ui-ep 注入接线 / 标签桥接 / 宿主根系出口（host-base）
│   │   │   ├── api/              # 契约类型 / BaseApi / Axios 基线 / OpenAPI 生成类型
│   │   │   ├── router/           # 静态路由 + 菜单 → 动态路由（@bms/vue useDynamicRoutes）
│   │   │   ├── stores/           # Pinia：createCrudStore / permission / menu / user
│   │   │   ├── layouts/          # BasicLayout 基础壳
│   │   │   ├── views/            # HomeView 默认页
│   │   │   ├── i18n/             # vue-i18n（zh-CN / en-US）
│   │   │   ├── styles/           # 设计令牌 tokens.scss（size / density）
│   │   │   └── utils/            # useRequest / useListPage / useTabs / validators / status / serialize
│   │   └── tests/                # Vitest：宿主用例（base / http / request / permission / layout / menu / tabs / modal / home / utils 等）
│   ├── apps/mobile/                  # 移动端 H5 宿主（**随阶段十七交付，当前未建**；端口预留 5174）
│   └── packages/                 # 前端基座多包（源码头，宿主经 vite alias / tsconfig paths 消费）
│       ├── core/                     # 框架无关核心（纯 TS：固定三段 / 组件根 / 能力基类族 / 组件基类族 / 机制 / 领域 / 契约；`@bms/core/testing` 契约用例工厂；护栏用例含基类清单对账）
│       ├── vue/                      # Vue 绑定插件（组合式投影：useValue / useField / useAccess / useVirtualRange …）
│       ├── ui-ep/                    # PC 实现插件（Element Plus，按族组织的组件 + 基类投影 composables + 注入点 + 单一落点 utils）
│       └── ui-vant/                  # 移动端实现插件（**随阶段十七交付，当前未建**；与 ui-ep 同契约）
├── deploy/                   # 部署配置
│   │   ├── .env.example          # 开发服务器与服务凭据模板（复制为 .env）
│   │   ├── ci/                   # CI 构建（后端 / 前端 Dockerfile + 基础镜像构建脚本）
│   │   ├── compose/              # Docker Compose（base / gitlab / kiwi）
│       └── setup/                # 环境安装脚本（install-all.sh）
├── scripts/                  # 开发期工具链
│       └── tools/                # backup / base-check / bg / check-docs / defect / dsh / gitlab / governance / reorder-design / reorder-stage / vision / winrm / wol / workbuddy
├── ops/                      # 产品运维脚本（种子数据、备份恢复、租户库迁移，后续阶段填充）
│       └── README.md             # 目录说明
├── test文档 -> ../test/test文档  # 测试资产仓软链（工作区并置，不入库）
└── bms文档/                  # 项目文档
    ├── 基座文档清单.md        # 通用基座权威清单（产品不复制）
    ├── 后端基类清单.md        # 后端基类权威清单（分层 / 代码位置 / 状态）
    ├── 前端基类清单.md        # 前端基类权威清单（L0-L4 / 代码位置 / 状态）
    ├── 文档首页.md            # 全量导航
    ├── 规划/                  # 5 篇：项目规划说明、总体项目规划、开发部署规划、平台可扩展性规划、微服务演进规划
    ├── 规范/                  # 20 篇：文档、命名、英文简称、前后端、数据库、API、安全、测试、日志、评审、国际化、Git、部署发布、原型审查、项目管理、需求/计划/任务文档、AI 开发
    ├── 设计/                  # 架构设计 / 概要设计 / 数据库设计 / 布局设计 / 原型设计 / 组件设计
    ├── 项目/                  # 按阶段的项目基线：需求 / 计划 / 任务（00_准备期、01_项目骨架、03_后端插件化、04_前端组件库、05_前端插件化）
    ├── 资料/                  # 共享基础设施资料（开发服务器 / 开发机 / 工具 / AI / 知识档案）
    ├── 用户文档/              # 本地资源（机器凭据等，已 gitignore）
    └── 资源/                  # 文档共享样式与 mermaid 资产
```

> 凭据统一存 `deploy/.env`（已 gitignore，模板见 `deploy/.env.example`）。
>
> `AGENTS.md` 与 `.opencode` 位于**工作区根**（工作区模型见《[平台可扩展性规划](bms文档/规划/平台可扩展性规划.md)》4.3），不在本仓库内。
>
> `app/` 下除 core / api / models / repositories / schemas / services / db 外，跨阶段基座与能力域基座（cache ~ ws，如缓存、事件、能力域横切）当前均为**占位契约**（Null 实现），真实实现随对应阶段回补；分层、职责与状态以《[后端基类清单](bms文档/后端基类清单.md)》为准。

## 文档导航

> 全部文档位于 `bms文档/` 目录，入口为《[文档首页](bms文档/文档首页.md)》（全量导航）。正文以 Markdown 为载体，线框图/可交互原型保留 `.html` 资产。

| 目的 | 文档 |
| --- | --- |
| 规划主文件（技术栈、功能范围、验收口径、AI 治理与变更管理、开发计划） | [规划/项目规划说明](bms文档/规划/项目规划说明.md) |
| 阶段工期、里程碑与甘特图、交付物、质量与风险 | [规划/总体项目规划](bms文档/规划/总体项目规划.md) |
| 开发环境部署方案（分工、服务清单、端口与磁盘规划） | [规划/开发部署规划](bms文档/规划/开发部署规划.md) |
| 平台可扩展性（三层模型、工作区模型） | [规划/平台可扩展性规划](bms文档/规划/平台可扩展性规划.md) |
| 微服务目标架构（服务清单、服务化地基、演进路线） | [规划/微服务演进规划](bms文档/规划/微服务演进规划.md) |
| 阶段一 需求基线（54 条）与 M1 验收门禁 | [项目/01_项目骨架/需求/00_需求_项目骨架](bms文档/项目/01_项目骨架/需求/00_需求_项目骨架.md) |
| 阶段一 任务基线（需求域 01 ~ 04） | [项目/01_项目骨架/任务/01_工程骨架](bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架.md) · [04_CI与阶段验收](bms文档/项目/01_项目骨架/任务/04_CI与阶段验收/04_CI与阶段验收.md) |
| 阶段一 排期计划与遗留台账 | [项目/01_项目骨架/计划/01_计划_项目骨架](bms文档/项目/01_项目骨架/计划/01_计划_项目骨架.md) |
| **阶段测试报告（阶段一）** | [项目/01_项目骨架/01_测试报告_项目骨架](bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md) |
| 阶段二 需求基线（29 条，后端基座与服务化地基） | [项目/02_后端基座与服务化地基/需求/00_需求_后端基座与服务化地基](bms文档/项目/02_后端基座与服务化地基/需求/00_需求_后端基座与服务化地基.md) |
| 阶段二 任务与计划基线（29 子任务 / 256h / 8 周） | [任务/01 后端基座真实实现](bms文档/项目/02_后端基座与服务化地基/任务/01_后端基座真实实现/01_后端基座真实实现.md) · [计划](bms文档/项目/02_后端基座与服务化地基/计划/01_计划_后端基座与服务化地基.md) |
| 阶段三 需求基线（11 条）与 M3 验收门禁 | [项目/03_后端插件化/需求/00_需求_后端插件化](bms文档/项目/03_后端插件化/需求/00_需求_后端插件化.md) |
| 阶段三 任务基线（需求域 01 ~ 05） | [任务/01_插件化基座](bms文档/项目/03_后端插件化/任务/01_插件化基座/01_插件化基座.md) · [计划](bms文档/项目/03_后端插件化/计划/01_计划_后端插件化.md) |
| **阶段测试报告（阶段三）** | [项目/03_后端插件化/01_测试报告_后端插件化](bms文档/项目/03_后端插件化/01_测试报告_后端插件化.md) |
| 阶段四 需求基线（40 条）与 M4 验收门禁 | [项目/04_前端组件库/需求/00_需求_前端组件库](bms文档/项目/04_前端组件库/需求/00_需求_前端组件库.md) |
| 阶段四 任务与排期（八类组件域 · 41 任务 / 846h） | [阶段索引](bms文档/项目/04_前端组件库/README.md) · [计划](bms文档/项目/04_前端组件库/计划/01_计划_前端组件库.md) |
| **阶段测试报告（阶段四）** | [项目/04_前端组件库/01_测试报告_前端组件库](bms文档/项目/04_前端组件库/01_测试报告_前端组件库.md) |
| 阶段四 合规审计（首审 / 复审） | [审计（首审）](bms文档/项目/04_前端组件库/审计/01_审计_前端合规审计（首审）.md) · [审计（复审）](bms文档/项目/04_前端组件库/审计/02_审计_前端合规审计（复审）.md) |
| 阶段五 需求 / 任务 / 计划基线（M5 门禁） | [需求总览](bms文档/项目/05_前端插件化/需求/00_需求_前端插件化.md) · [任务基线](bms文档/项目/05_前端插件化/任务/01_扩展点与装配/01_扩展点与装配.md) · [计划](bms文档/项目/05_前端插件化/计划/01_计划_前端插件化.md) |
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
