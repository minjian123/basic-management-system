# 框架无关核心重构 · S3b 实施记录（ui-ep 重建 · 批 2）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 2）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 2（累计迁入 12 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈2h |
| 结论 | 批 2 完成：7 件 + 2 上下文迁移、`usePersistedState` 投影接入，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 迁移（7 件 + 2 上下文） | `Card` / `Collapse` / `CollapseItem` / `Tabs` / `TabPane` / `Split` / `LoadingMask` + `collapseContext.ts` / `tabsContext.ts`（EP 显式导入与按需样式；`useComponentBase` / `usePersistedState` 改源 `@bms/vue`；Card 的 `SkeletonBlock` 改相对导入） |
| 新投影 | `@bms/vue` 增 `usePersistedState`（核心 `BasePersistedState` ↔ Vue；接口面与旧片段同构——`state` / `syncing` / `synced` / `isPlaceholder` / `get` / `set` / `reset` / `syncFromRemote` / `flush`，**远端同步为占位**） |
| 依赖 | ui-ep 增 `vue-i18n`（peer `^11.0.0` + dev 对齐 `^11.4.10`；`LoadingMask` 文案 `feedback.loading`） |
| 用例（+5） | Card 标题/内容；Collapse 渲染与面板；Tabs 内容区；Split 拖拽条（`bms-split-splitter`）；LoadingMask 遮罩显示/隐藏（`delay=0` 即时） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **8** 用例 |
| `npm run ui-ep:typecheck` | 通过（vue-tsc） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 新装 EP 类型更严（对照 frontend lock）：`Tabs.type`（`'line'` 不在 EP 类型面）/ `TabPaneName`（含 number）/ `CollapseModelValue` | 类型收口（**运行期行为不变**）：`epType`（`line → ''`，EP 空值即线型默认）、事件 `String($event)`、`normalize/onUpdate` 参数放宽 `unknown` 并按字符串归一 |
| 2 | 测试断言与真实结构不符（Card 无 `#header` 插槽；Split 拖拽条类名 `split-splitter`；LoadingMask 根常驻 + `delay` 默认 200ms） | 按真实结构/行为校准用例（Card 用 `title` prop；Split 断言实际类名；LoadingMask 断言遮罩层 + `delay=0`） |
| 3 | `TabPane` 独立 mount 无上下文（不渲染） | 用例改为在 `Tabs` 内验证内容区（TabPane 的上下文依赖属 EP 语义，不单测脱离场景） |

## 5. 偏差与遗留 <a id="deviations"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 已迁 12 / 约 42 件（余 ~30：布局余件 / 菜单 / 标签（TabsNav 需 `useTabs` 投影）/ 弹窗 / 反馈余（svg + perm 依赖）/ 域包装 / 宿主壳） | S3 续批 3+（模板稳定：显式 EP + `@bms/vue` 投影 + 用例校准） |
| 2 | `usePersistedState` 远端同步 / scope 语义 | 占位；真实偏好接口随认证 / 个人中心任务 |
| 3 | `LoadingMask` / `Split` / `Collapse` 等交互细节（延迟取消、拖拽边界、手风琴） | 已由迁移保真；深入用例随 ui-ep 完整回归（S5） |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
