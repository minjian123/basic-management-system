# frontend（BMS 管理端 · PC）

BMS 基础管理系统前端（PC 管理端）：Vue 3 + Vite + TypeScript + Element Plus。
属于 pnpm workspace 工程之一，与 `frontend-mobile`（H5）共享仓库级依赖管理。

## 启动命令

```bash
# 开发（默认 http://localhost:5173）
pnpm --filter frontend dev

# 类型检查 + 构建（产物输出 dist/）
pnpm --filter frontend build

# 单元测试（vitest，jsdom 环境）
pnpm --filter frontend test

# 代码检查（eslint）
pnpm --filter frontend lint

# 格式化（prettier）
pnpm --filter frontend format
```

Node 版本由根目录 `.nvmrc`（20.19.0）固定，建议 `nvm use` 后运行。

## 目录结构

```
frontend/
├── src/
│   ├── api/          # axios 封装骨架（baseURL /api，预留拦截器）
│   ├── router/       # vue-router：/ → MainLayout（Home），/health → HealthCheck
│   ├── stores/       # pinia 实例（占位）
│   ├── views/        # 页面：Home（欢迎占位）、HealthCheck（后端健康检查演示页）
│   ├── layouts/      # MainLayout：侧边栏 + 顶栏 + router-view 槽
│   ├── components/   # 通用组件（占位）
│   ├── i18n/         # vue-i18n 实例与语言包（占位）
│   ├── utils/        # 工具函数（format 时间/文本格式化）及单测 __tests__
│   ├── App.vue       # 根组件（仅 router-view）
│   └── main.ts       # 挂载 App，注册 router / pinia / i18n
├── vite.config.ts    # Element Plus 按需引入（unplugin-vue-components）+ vitest 配置 + /healthz 代理
├── eslint.config.js  # ESLint flat config
└── .prettierrc.json  # Prettier 配置
```

## 健康检查页说明

`/health` 页面直接 `fetch('/healthz')` 展示后端健康状态（loading / 成功 / 失败三态）。
开发模式下 Vite 已将该路径代理到后端 8000 端口（见 `vite.config.ts` 的 `server.proxy`）；
构建产物部署时，`/healthz` 由网关或反向代理转发到后端。
