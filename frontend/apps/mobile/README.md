# BMS 移动端 H5（frontend/apps/mobile）

> Vue 3 + Vite + TypeScript 移动端工程（Vant 4 / Router / Pinia / Axios / i18n + 视口适配；S4c 起消费基座新体系 `@bms/*`）

## 项目简介

BMS 平台移动端 H5：Vue 3 + Vite + TypeScript 严格模式；Vant 4（unplugin 按需引入）、Vue Router 4、Pinia、Axios 统一响应解析（与 PC 端同款基线）、vue-i18n；postcss px→vw 视口适配（设计稿 375）+ 安全区变量；ESLint + Prettier + Vitest 质量链路（覆盖率阈值 70%）。

**新体系（S4c 切流）**：本工程为**宿主装配**——组件与能力经 `@bms/core`（框架无关核心）、`@bms/vue`（组合式投影）、`@bms/ui-vant`（移动端实现插件）消费；旧 `src/base/` 与 `src/components/base/` 片段层已删除（历史经 git 追溯）。当前 Vitest **10 文件 / 58 用例**全绿（覆盖率语句 ≈ 88%）；体积预算合计 140 KB（gzip）。

## 快速启动

前置：Node 22（nvm 管理）；先启动 backend（`cd ../../../backend && uv run uvicorn app.main:create_app --factory --port 8000`）。

```bash
cd frontend/apps/mobile
npm ci
npm run dev       # http://127.0.0.1:5174（默认页展示 backend 连通状态；375×667 视口）
npm run lint      # ESLint（--max-warnings 0）
npm run test      # Vitest（10 文件 / 58 用例）
npm run test:cov  # 同上 + 覆盖率（v8，阈值 70%）
npm run build     # vue-tsc -b && vite build（@bms/* 经 vite alias 源码直出）
npm run budget    # 构建体积预算（budget.json：合计 140 KB / 最大单文件 83 KB）
```

- 代理：`/api`、`/healthz` → `http://localhost:8000`；`/info` 重写至 backend 根（连通验证）；`/docs` 不代理。
- npm 源：`.npmrc` 配 npmmirror；因 `openapi-typescript` 暂声明 TS ^5（项目 TS 6）设 `legacy-peer-deps=true`（待其支持后移除）。

## 目录结构

```text
frontend/apps/mobile/
├── .npmrc · .nvmrc · eslint.config.js · .prettierrc.json
├── postcss.config.js         # px→vw（设计稿 375，保留 1px）
├── vite.config.ts            # 端口 5174 + @ / @bms/* 别名 + 分包（vendor-vant / bms-base）+ 代理
├── vitest.config.ts          # jsdom + vant inline
├── package.json              # 依赖锁定见 package-lock.json
├── README.md                 # 本文件
├── src/
│   ├── main.ts               # 挂载 router / pinia / i18n + ui-vant 装配（bootstrapUiBridge）+ v-perm
│   ├── adapters/
│   │   ├── ui-bootstrap.ts   # ui-vant 注入点接线（configurePermissionChecker ← 权限 store）
│   │   └── host-base.ts      # 宿主根系出口（日志 / 错误上报 sink；测试可注入）
│   ├── api/                  # 契约类型 / BaseApi（@bms/core 根系）/ Axios 基线（token / adapter / error）
│   ├── directives/perm.ts    # v-perm（判定经 @bms/ui-vant 注入点；权限版本重评）
│   ├── router/routes.ts      # 路由
│   ├── stores/               # base.ts（createCrudStore）/ permission（@bms/vue useAccess 投影）
│   ├── views/HomeView.vue    # 默认页
│   ├── dev/                  # 容器件核对页（containers-check.html，开发专用不计入构建）
│   ├── i18n/                 # index + zh-CN / en-US
│   ├── styles/               # tokens.scss（消费基座令牌）/ safe-area.scss
│   └── utils/                # useRequest / useListPage / useTabs / validators / status / serialize / perm
└── tests/                    # 宿主用例（base / http / request / permission / directive-perm / home / utils / format / tokens）
```

## 文档导航

- 仓库根 [README](../../README.md)
- 专项 [02-7 框架无关核心重构](../../../bms文档/项目/04_前端组件库/任务/02_基础组件类/02_基础组件类_07_框架无关核心重构/02_基础组件类_07_框架无关核心重构.md)（S4 详细设计与实施记录）
- 阶段一：[01-05 任务文档](../../../bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架_05_frontend-mobile工程初始化/01_工程骨架_05_frontend-mobile工程初始化.md) · [阶段测试报告](../../../bms文档/项目/01_项目骨架/01_测试报告_项目骨架.md)
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../../../bms文档/前端基类清单.md)》
- 《[架构设计 · 前端组件体系](../../../bms文档/设计/架构设计/05_架构设计_前端组件体系.md)》「框架无关核心与插件架构」节
