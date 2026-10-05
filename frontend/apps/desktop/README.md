# PC 管理端宿主（frontend/apps/desktop）

> `@bms/desktop`：PC 管理端宿主应用（Vue 3 + Vite + Element Plus），装配基座包并承载运行时模块。

## 定位

- 装配 `@bms/core` / `@bms/vue` / `@bms/ui-ep` / `@bms/api-types`，提供路由、状态（Pinia）、i18n、请求层与模块宿主。
- 通过 Module Federation 在运行时装载 `frontend/modules/*`，把模块贡献经扩展点注册表装配进宿主（路由 / 菜单 / 页面区域 / 通用组件 / 字段渲染器 / 图标 / 工作台卡片 / 主题令牌 / i18n）。
- 附**开发态核对页**：根目录 `<主题>-check.html` + `src/dev/XxxCheck.vue`（不进构建产物，供人工逐族核对）。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/desktop dev            # 开发服务器（端口 5173）
pnpm --filter @bms/desktop test           # Vitest 宿主用例（含 guard-* 护栏）
pnpm --filter @bms/desktop test:cov       # 覆盖率
pnpm --filter @bms/desktop lint
pnpm --filter @bms/desktop build          # vue-tsc -b && vite build
pnpm --filter @bms/desktop budget         # 首屏体积预算门禁
pnpm --filter @bms/desktop guard:shared   # MF 共享依赖白名单校验
```

本地联调后端：`bash scripts/tools/dev/本地全套.sh up`（后端四服务）→ `bash scripts/tools/dev/本地全套.sh env`（写 `.env.local` 的本地服务映射）→ 起宿主。

## 目录结构

```text
frontend/apps/desktop/
├── src/
│   ├── main.ts          # 挂载 router / pinia / i18n + ui-ep 装配 + v-perm
│   ├── App.vue          # 路由出口（登录族路由独立全屏）
│   ├── api/             # 契约类型 / BaseApi / Axios 基线（401 保留业务码口径）
│   ├── router/          # 静态路由 + 菜单 → 动态路由 + 布局作用域（layout-scope）
│   ├── stores/          # Pinia：user / permission / menu 等
│   ├── module/          # 模块宿主：federation / manifest / registries / entries / boundary / themeTokens / i18n
│   ├── components/      # 宿主自用组件
│   ├── composables/     # 组合式工具
│   ├── directives/      # v-perm 等自定义指令
│   ├── dev/             # 开发态核对页（XxxCheck.vue + xxxCheck.ts）
│   ├── observability/   # 前端观测（web-vitals 等）
│   ├── styles/          # 设计令牌 tokens.scss
│   ├── utils/           # useRequest / useListPage / useTabs / validators / status / serialize
│   └── views/           # 页面视图
├── tests/               # Vitest 宿主用例（api / session / module / guard-* …）
├── public/modules.json  # 模块装配清单（远端入口与版本）
├── scripts/             # check-bundle-budget.mjs
├── *-check.html         # 开发态核对页入口（不进构建）
└── vite.config.ts       # 端口 5173 + @bms/* 别名 + 分包 + 后端代理
```

## 关键约定

- **登录族路由独立全屏**：`/login`、`/login/qr` 不套主框架外壳、不入页签（判定 `src/router/layout-scope.ts::isStandalonePath`）；错误页（`/403` `/404` `/500`）仍在框架内。
- **宿主用例必须跑**：根 `pnpm run check` 只含基座四包，**不含宿主**——改宿主或 `modules/*` 后必须另跑 `pnpm --filter @bms/desktop test`。
- **裸原生元素禁用**：模板内不得出现 `<input>` / `<button>` / `<select>` / `<textarea>`，走组件库件或 Element Plus 基础件（护栏 `tests/guard-library-components.spec.ts`）。
- **区域条目只挂紧凑件**：`layout.header` 等 `inline` 区域是**一行高窄容器**（徽标 / 按钮 / 状态标签），整页 / 大面板走页面路由。
- **构建产物噪声**：跑生产 `build` 会重写 `components.d.ts`（`unplugin-vue-components` 生成物），构建后 `git checkout --` 回退再提交。
- **新增核对页**：`src/dev/XxxCheck.vue` + `xxxCheck.ts` + 根 `xxx-check.html`，并在两处 `.vscode/launch.json` 选页清单同步。
- **原型对照**：界面改动收口须过 `check-prototype-review.py`（依据取 `bms文档/设计/原型设计/` 或《组件设计》，须有截图与逐页结论）。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../../../bms文档/前端基类清单.md)》
- 《[组件设计总览](../../../bms文档/设计/组件设计/01_组件设计_总览.md)》·《[原型设计总览](../../../bms文档/设计/原型设计/01_原型设计_总览.html)》
- 《[布局设计 · 主框架](../../../bms文档/设计/布局设计/04_布局设计_主框架.html)》·《[布局设计 · 导航](../../../bms文档/设计/布局设计/05_布局设计_导航.html)》·《[布局设计 · 设计令牌](../../../bms文档/设计/布局设计/02_布局设计_设计令牌.html)》
- 《[开发机部署使用说明总览](../../../bms文档/资料/开发机/开发机部署使用说明总览.md)》
