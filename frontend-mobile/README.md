# BMS 移动端 H5（frontend-mobile）

> Vue 3 + Vite + TypeScript 移动端工程（01-05 完整初始化：Vant 4 / Router / Pinia / Axios / i18n + 视口适配）

## 项目简介

BMS 平台移动端 H5：Vue 3 + Vite + TypeScript 严格模式；Vant 4（unplugin 按需引入）、Vue Router 4、Pinia、Axios 统一响应解析（与 PC 端同款基线）、vue-i18n；postcss px→vw 视口适配（设计稿 375）+ 安全区变量；ESLint + Prettier + Vitest 质量链路。

## 快速启动

前置：Node 22（nvm 管理）；先启动 backend（`cd ../backend && uv run uvicorn app.main:create_app --factory --port 8000`）。

```bash
cd frontend-mobile
npm ci
npm run dev       # http://127.0.0.1:5174（默认页展示 backend 连通状态；375×667 视口）
npm run lint      # ESLint（--max-warnings 0）
npm run test      # Vitest 冒烟（Kiwi 20）
npm run build     # vue-tsc -b && vite build
```

- 代理：`/api`、`/healthz` → `http://localhost:8000`；`/info` 重写至 backend 根（连通验证）；`/docs` 不代理。
- npm 源：`.npmrc` 配 npmmirror；因 `openapi-typescript` 暂声明 TS ^5（项目 TS 6）设 `legacy-peer-deps=true`（待其支持后移除）。

## 目录结构

```text
frontend-mobile/
├── .npmrc                  # npmmirror + legacy-peer-deps（见上）
├── .nvmrc                  # 固定 Node 22
├── .env.development        # VITE_API_BASE=/api
├── postcss.config.js       # px→vw（设计稿 375，保留 1px）
├── eslint.config.js
├── .prettierrc.json
├── vitest.config.ts
├── package.json
├── package-lock.json       # 依赖锁定（必须提交）
├── vite.config.ts          # 端口 5174 + @ 别名 + 代理 + Vant 按需
├── tsconfig.json           # 及 app / node 子配置（@ 路径映射）
├── index.html              # 标题 + viewport-fit=cover
├── README.md               # 本文件
├── public/
│   └── favicon.svg
├── src/
│   ├── main.ts             # 挂载 router / pinia / i18n + 安全区样式
│   ├── App.vue             # 路由出口
│   ├── api/                # 同款契约类型 / BaseApi / Axios 基线
│   ├── router/             # routes.ts（动态路由骨架）
│   ├── stores/             # base.ts（createCrudStore）/ useUserStore（token 仅内存）
│   ├── views/              # HomeView（默认页）
│   ├── components/         # 组件（占位）
│   ├── i18n/               # index + zh-CN / en-US（含 error.{code} 占位）
│   ├── styles/             # safe-area.scss（安全区变量）
│   └── utils/              # serialize.ts（stableStringify）/ 工具占位
└── tests/
    ├── home.spec.ts        # 默认页冒烟（Kiwi 20）
    └── base.spec.ts        # 基础类用例（Kiwi 22）
```

## 文档导航

- 仓库根 [README](../README.md)
- [01_05 任务文档](../bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架_05_frontend-mobile工程初始化/01_工程骨架_05_frontend-mobile工程初始化.md) · [详细设计](../bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架_05_frontend-mobile工程初始化/设计/05_详细设计_01_frontend-mobile工程初始化.md)
- 《[前端开发规范](../bms文档/规范/前端开发规范.md)》
- 《[架构设计 · 前端架构](../bms文档/设计/架构设计/28_架构设计_前端架构.md)》移动端节
