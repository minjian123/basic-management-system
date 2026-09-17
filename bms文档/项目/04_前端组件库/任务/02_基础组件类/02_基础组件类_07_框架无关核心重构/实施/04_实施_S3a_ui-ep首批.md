# 框架无关核心重构 · S3a 实施记录（ui-ep 重建 · 首批）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（首批）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · **首批**（组件迁移分步推进；本批 5 件） |
| 对应设计 | 《[架构设计 · 前端组件体系](../../../../../../设计/架构设计/05_架构设计_前端组件体系.md)》「框架无关核心与插件架构（设计变更）」节 |
| 实施日期 | 2026-09-16 |
| 实施人 | minjian |
| 环境 | Linux 开发机（mjpc）；Node v24.20.0；npm workspaces（core / vue / ui-ep） |
| 实测工时 | ≈3h（原估 S3 共 40h；按批推进，本批验证「EP 插件形态」全链路） |
| 结论 | S3a 完成：核心 `BaseComponent` 协议补全、`@bms/vue` 组件根投影落地、`packages/ui-ep` 建立并迁移首批 5 件，`npm run check` 全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 核心协议补全 | `packages/core/src/base/BaseComponent.ts`：`identifier` / `nsClass` / `rootAttrs`（档位属性 + 状态类 `is-loading`·`is-disabled`·`is-hidden` + `aria-*`）/ `passthroughAttrs`（保留键过滤）/ `setProps`（运行期可变字段）/ `notifyLifecycle` / `mechanisms`（装配点骨架）——**与旧实现行为同构（纯 TS）** |
| Vue 组件根投影 | `@bms/vue`：`useComponentBase`（实例化核心 + props 优先 sync + scope 释放；接口面与旧组合式同构——**迁移组件只改 import 源**） |
| EP 插件包（新） | `packages/ui-ep`：deps `element-plus` / `@bms/core` / `@bms/vue`；peer `vue`；测试栈 plugin-vue + jsdom + EP inline + vue-tsc；`env.d.ts`（EP 按需样式模块声明） |
| 首批迁移（5 件） | `GridRow` / `GridCol` / `Space` / `Divider`（**显式导入 EP 组件与按需样式**，替代旧自动导入插件依赖）+ `SkeletonBlock`（原生）——统一改 import 源为 `@bms/vue` |
| 用例（新增 3 条） | `packages/ui-ep/tests/components.spec.ts`：组件根协议（`nsClass` / `data-size` / 透传 `data-foo`）、栅格渲染、骨架行数与 `loading=false` 渲染内容 |
| 工程 | 根 `check` 串联 core + vue + ui-ep；CI `core-check` 增 `@bms/ui-ep` symlink 装配 |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check`（core + vue + ui-ep） | 全绿：core **8 文件 / 41 用例** + vue **1 文件 / 3 用例** + ui-ep **1 文件 / 3 用例** |
| `npm run ui-ep:typecheck` | 通过（vue-tsc；DOM lib + `vite/client` 类型面） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 核心 `BaseComponent` 扩充 `visible` 后与能力撞名（`BaseFieldPerm.visible` / `BaseColumnConfig.visible` / `BaseWatermark.visible`，TS2416/2610） | **能力避让**（既定口径）：`permVisible` / `visibleColumns` / `shown`；S2 行为用例同步 |
| 2 | ui-ep 类型环境缺 `import.meta.env` 与 `console`（DOM） | ui-ep `tsconfig`：`lib: [ES2022, DOM, DOM.Iterable]` + `types: [vite/client]` |
| 3 | `GridRow.gutter`（`number \| [number, number]`）与 EP 类型面（单值）不符 | 类型收口 `gutterValue`（`as unknown as number`）——**运行期原值透传**（与旧实现一致，数组语义由 EP 运行期承担） |
| 4 | 迁移组件原依赖「自动导入插件」（unplugin-vue-components） | 改为**显式导入 EP 组件与按需样式**（包对外自足，不要求宿主配置导入插件） |

## 5. 偏差与遗留 <a id="deviation"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | S3 仅迁首批 5 件（余约 37 件：布局 / 容器 / 菜单 / 标签 / 弹窗 / 反馈其余 / 域包装 / 宿主壳） | S3 续批（按同一模板：改 import 源 + 显式 EP 导入 + 用例）；映射清单化后再批量推进 |
| 2 | 迁移组件的 `@/utils/*`（perm / format）等旧工程依赖 | 用核心能力（`BaseAccess` 等）或注入方式替换（随对应组件批次处置；EmptyState 的 svg 资产迁 `ui-ep` 资源目录） |
| 3 | 旧工程（`apps/desktop/`）仍承载宿主（路由 / 菜单 / 页面） | S5 宿主切流（`apps/desktop`）时归档旧工程 |
| 4 | `mechanisms` 装配点为骨架（占位 / 资源 / 订阅挂接未接） | 随相关能力投影（S3 续批 / S4）按需补 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
