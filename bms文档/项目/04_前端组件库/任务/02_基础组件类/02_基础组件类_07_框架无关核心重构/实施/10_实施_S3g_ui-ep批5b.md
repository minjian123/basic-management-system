# 框架无关核心重构 · S3g 实施记录（ui-ep 重建 · 批 5b）：布局余件

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 5b）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 5b（布局余件；累计迁入 27 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈2.5h |
| 结论 | 批 5b 完成：布局五件 + 两个组合式 + 视图解析注入点，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 视图解析注入点（新） | `frontend/packages/ui-ep/src/components/layout/viewResolver.ts`：`configureViewResolver(resolver)` / `resolveView(name)`（**未注入 = 未注册**，返回 `null` 回退占位视图）+ `nameComponent`（keep-alive 固定 name，纯 Vue 实现随迁、去宿主 glob） |
| 迁移（5 件 + 2 组合式） | `PageContainer`（标题 / 描述 / 面包屑 / 返回与刷新事件 / 插槽）、`AppLayout`（槽位布局 + 窄屏抽屉 + `toggleSidebar`）、`FormFrame`（列表 / 详情的标签 · 抽屉 · 页面三形态 + 视图解析 + 缓存）、`MasterDetail`（主从 + 可拖拽分栏 + 详情空态）、`MasterTree`（树渲染 / 懒加载 / 工具栏 / 右键菜单 / 权限控制）；`useFormFrame`（类型来源改 `tabs/types`）与 `useMasterDetail`（`usePersistedState` → `@bms/vue`） |
| 依赖改造 | `useComponentBase` → `@bms/vue`；`EmptyState` / `SkeletonBlock` default 导入；`hasPerm` → `checkPerm`（权限注入点）；EP `el-drawer` / `el-button` / `el-input` / `el-tree` 显式导入与按需样式 |
| EP 类型收口 | `MasterTree` 三处 `el-tree` 回调（`load` / `filter-node-method` / `node-click` / `node-contextmenu`）加类型兼容包装（`onLoadCompat` / `filterNodeCompat` / `onNodeClickCompat` / `onNodeContextMenuCompat`），运行期行为不变 |
| 用例（+5） | `tests/layout.spec.ts`：PageContainer（标题 / 描述 / 面包屑 / 插槽）、AppLayout（槽位渲染与 `showSidebar` / `showTabs` 开关）、FormFrame（未注入空态 / 注入后渲染视图）、MasterDetail（主从槽位 / 详情空态）、MasterTree（树渲染 / 懒加载 `loadChildren` / 骨架 / 空态） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **40** 用例，vue-tsc 无错 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| `@/router/routeComponent` 的 `resolveView` 依赖宿主 `import.meta.glob('../views/**')` | 拆为注入点：`nameComponent` 纯 Vue 实现随迁 ui-ep；`resolveView` 由宿主经 `configureViewResolver` 注入（未注入 = 未注册 → 空态，占位保真） |
| ui-ep `tabs` 目录无 `index.ts` | `useFormFrame` 从 `tabs/types` 取类型、`FormFrame` default 导入 `FormFrameTabs.vue` |
| EP `el-tree` 回调签名与组件内部窄类型不匹配 | 兼容包装层（模板绑定 Compat 函数），内部实现与运行期不变 |

## 5. 回写清单 <a id="writeback"></a>

| 文档 | 回写点 |
| --- | --- |
| [任务文档](../02_基础组件类_07_框架无关核心重构.md) | 状态行（S3 批 5b）与阶段记录追加 |
| [计划](../../../../计划/01_计划_前端组件库.md) | §3 表 `02_07` 行（批 5b 与累计 27 件、用例数） |
