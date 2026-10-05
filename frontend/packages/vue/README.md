# Vue 绑定插件（frontend/packages/vue）

> `@bms/vue`：把核心基座投影为 Vue 组合式 API 的绑定插件。

## 定位

- 连接 `@bms/core` 的基类与 Vue 运行时：以组合式函数（`useValue` / `useField` / `useAccess` / `useVirtualRange` 等）把基座能力投影为宿主与模块可直接消费的响应式面。
- 承载路由与菜单绑定（`useDynamicRoutes` 等），供宿主把菜单数据转成动态路由。
- 经 `testing/` 提供 Vue 侧契约用例工厂。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/vue typecheck
pnpm --filter @bms/vue lint
pnpm --filter @bms/vue test
pnpm run vue:check           # 上方三项聚合（根脚本）
```

## 目录结构

```text
frontend/packages/vue/
├── src/
│   ├── index.ts       # 包根出口（组合式投影具名导出）
│   └── bindings/      # Vue 绑定实现（投影 / 生命周期 / 路由与菜单绑定等）
└── testing/           # Vue 侧契约用例工厂
```

## 关键约定

- 新增投影须在 `src/index.ts` 具名导出，并同步《[前端基类清单](../../../bms文档/前端基类清单.md)》中对应条目的消费口径。
- 组件侧必须**值引入** `Base*` / `useBaseXxx`（不得只作类型引入），否则运行期投影缺失。
- 跨实例基类对象经 props 进响应式前须 `markRaw(toRaw(x))`，避免被深度代理。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../../../bms文档/前端基类清单.md)》
- 《[架构设计 · 前端架构](../../../bms文档/设计/架构设计/08_架构设计_前端架构.md)》
