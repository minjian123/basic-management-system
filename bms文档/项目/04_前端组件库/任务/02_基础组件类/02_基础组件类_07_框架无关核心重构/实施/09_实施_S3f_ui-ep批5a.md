# 框架无关核心重构 · S3f 实施记录（ui-ep 重建 · 批 5a）：侧边菜单

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 5a）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 5a（侧边菜单；累计迁入 22 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈2h |
| 结论 | 批 5a 完成：菜单两件 + 菜单状态注入点，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 菜单状态注入点（新） | `frontend/packages/ui-ep/src/components/menu/menuSource.ts`：`configureMenuSource(provider)` / `getMenuSource()`（可见菜单 / 展开集 / `setExpanded` / `expandByPath`）——非受控模式消费；**未注入 = 空菜单**（占位保真，对齐旧 store「未注入 loader 置空清单」）；受控模式（传 `menus` 数组）不依赖注入 |
| 纯函数随迁 | `sortVisible` 从旧 store 移入 `menu/types.ts`（与 `filterMenuTree` / `findAncestorKeys` / `menuKey` 同处，去除 pinia 依赖） |
| 迁移（2 件） | `MenuNode`（递归；EP `ElSubMenu` / `ElMenuItem` 显式导入）、`SideMenu`（`@/stores/menu` → 注入点；`getCurrentInstance().$router` → `useRouter()`；`EmptyState` 复用迁移件）；搜索 / 手风琴 / 外链 / 高亮自动展开语义保持 |
| 用例（+4） | `tests/menu.spec.ts`：受控渲染（hidden 过滤 / sort 排序 / 子菜单保留与顺序）、搜索（父链命中 / 无匹配空态 / 折叠隐藏搜索框）、导航（`navigate` + `router.push` / 外链 `window.open` 且不导航）、非受控（注入菜单渲染 + `expandByPath` 回写 / 未注入为空 + 空态） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **35** 用例，vue-tsc 无错 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| 旧 store 的 `expandedKeys` 为响应式（随 store 更新驱动 `default-openeds`） | 迁移版非受控初始展开集在 setup 读注入一次（`initialOpeneds`）；后续展开由 EP 承接并回写 `setExpanded`（持久化归宿主）；受控模式主导，偏差已记录 |
| `EmptyState` 为 default 导出，目录无 `index.ts` | `SideMenu` 按 `../feedback/EmptyState.vue` default 导入（与主出口导出方式一致） |

## 5. 回写清单 <a id="writeback"></a>

| 文档 | 回写点 |
| --- | --- |
| [任务文档](../02_基础组件类_07_框架无关核心重构.md) | 状态行（S3 批 5a）与阶段记录追加 |
| [计划](../../../../计划/01_计划_前端组件库.md) | §3 表 `02_07` 行（批 5a 与累计 22 件、用例数） |
