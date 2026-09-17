# 框架无关核心重构 · S3d 实施记录（ui-ep 重建 · 批 4a）：反馈与权限

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 4a）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 4a（反馈与权限；累计迁入 17 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈2h |
| 结论 | 批 4a 完成：权限注入点 + 反馈两件 + 权限按钮迁移，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 权限注入点（新） | `ui-ep/src/permission.ts`：`configurePermissionChecker(checker)` / `checkPerm(code, mode)`——语义与旧 `hasPerm` 一致（未设权限码不限制；**未注入判定器 = 空集（无权限）**，占位保真）；宿主装配时注入 |
| 资产迁移 | `empty-403/404/500.svg` + `empty-list/message/search/todo.svg` 共 7 个 → `ui-ep/src/assets/images/` |
| 迁移（3 件） | `ErrorPage`（**`getCurrentInstance().$router` 改 `useRouter()`** + 无路由回退 `location.assign`）、`EmptyState`、`PermButton`（`checkPerm` 注入点；文案内联占位）——EP `ElButton` 显式导入与按需样式 |
| 依赖 | ui-ep peer 增 `vue-router@^4.0.0`（`ErrorPage` 返回首页） |
| 用例（+7） | EmptyState（场景文案 / small / 按钮权限放行与否 + `action` emit）、ErrorPage（404 单动作 / 403 双动作 + `contact` emit / 500 动作文案 / 自定义 actions 覆盖 + handler）、PermButton（空集 hide / disable + 提示 / 注入放行 + click / 无权限码不限制） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **26** 用例 |
| `npm run ui-ep:typecheck` | 通过（vue-tsc） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | `PermButton` 仍 import 旧基座组合式（迁移遗漏） | 改源 `@bms/vue`（typecheck 捕获） |
| 2 | `ErrorPage` 缺省「返回首页」依赖 `appContext.$router`（组件实例桥） | 改 `useRouter()`（Vue Router 组合式；绑定层合理依赖）；无路由环境回退 `location.assign`（保真） |
| 3 | 权限判定原依赖 pinia 权限 store（应用态） | ui-ep 提供**模块级注入点**（`configurePermissionChecker`）；宿主装配时注入（占位期空集语义 = 受控按钮不显示，与旧一致） |

## 5. 偏差与遗留 <a id="deviations"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 已迁 17 / 约 42 件（余 ~25：modal 三件、菜单两件、布局余件、域包装、宿主壳） | 批 4b（modal）+ 批 5+（菜单 / 布局余 / 域包装 / 宿主壳） |
| 2 | `PermButton` 禁用提示文案内联（旧走 i18n `common.noPermission`） | 待 i18n 资源治理统一（宿主文案注入随 S5） |
| 3 | `EmptyState` 插画为 svg 资源导入（vite 资源处理） | 已随迁移验证（vue-tsc + vitest 通过）；打包策略随 S5 构建 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
