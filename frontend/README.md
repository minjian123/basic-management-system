# BMS PC 管理端（frontend）

> Vue 3 + Vite + TypeScript 前端工程（01-04 完整初始化：Element Plus / Router / Pinia / Axios / i18n + 质量链路）

## 项目简介

BMS 平台 PC 管理端：Vue 3 + Vite + TypeScript 严格模式；Element Plus UI、Vue Router 4、Pinia、Axios 统一响应解析、vue-i18n；ESLint + Prettier + Vitest 质量链路；开发代理连通 backend。

## 快速启动

前置：Node 22（nvm 管理）；先启动 backend（`cd ../backend && uv run uvicorn app.main:create_app --factory --port 8000`）。

```bash
cd frontend
npm ci
npm run dev       # http://127.0.0.1:5173（默认页展示 backend 应用名/版本）
npm run lint      # ESLint（--max-warnings 0）
npm run test      # Vitest 冒烟（Kiwi 19）
npm run build     # vue-tsc -b && vite build
```

- 代理：`/api`、`/healthz` → `http://localhost:8000`；`/info` 重写至 backend 根（连通验证）；`/docs` 不代理（后端 Swagger 直连 8000）。
- npm 源：`.npmrc` 配 npmmirror；因 `openapi-typescript` 暂声明 TS ^5（项目 TS 6）设 `legacy-peer-deps=true`（待其支持后移除）。

## 目录结构

```text
frontend/
├── .npmrc              # npmmirror + legacy-peer-deps（见上）
├── .nvmrc              # 固定 Node 22
├── .env.development    # VITE_API_BASE=/api
├── eslint.config.js    # ESLint flat config
├── .prettierrc.json
├── vitest.config.ts
├── package.json
├── package-lock.json   # 依赖锁定（必须提交）
├── vite.config.ts      # 端口 5173 + @ 别名 + 代理
├── tsconfig.json       # 及 app / node 子配置（@ 路径映射）
├── index.html
├── README.md           # 本文件
├── public/
│   └── favicon.svg
├── src/
│   ├── main.ts         # 挂载 router / pinia / i18n / Element Plus
│   ├── App.vue         # 路由出口
│   ├── api/            # types.ts（契约基类）/ base.ts（BaseApi）/ http.ts（Axios 基线）/ types.gen.ts（生成占位）
│   ├── router/         # routes.ts（动态路由骨架）
│   ├── stores/         # base.ts（createCrudStore）/ useUserStore（token 仅内存）
│   ├── layouts/        # BasicLayout（基础壳）
│   ├── views/          # HomeView（默认页）
│   ├── components/     # 通用组件（占位）
│   ├── i18n/           # index + zh-CN / en-US（含 error.{code} 占位）
│   └── utils/          # serialize.ts（stableStringify）/ 工具占位
└── tests/
    ├── home.spec.ts    # 默认页冒烟（Kiwi 19）
    └── base.spec.ts    # 基础类用例（Kiwi 21）
```

## 文档导航

- 仓库根 [README](../README.md)
- [01_04 任务文档](../bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架_04_frontend工程初始化/01_工程骨架_04_frontend工程初始化.md) · [详细设计](../bms文档/项目/01_项目骨架/任务/01_工程骨架/01_工程骨架_04_frontend工程初始化/设计/04_详细设计_01_frontend工程初始化.md)
- 《[前端开发规范](../bms文档/规范/前端开发规范.md)》
- 《[架构设计 · 前端架构](../bms文档/设计/架构设计/28_架构设计_前端架构.md)》
