# 框架无关核心重构 · S3c 实施记录（ui-ep 重建 · 批 3）：标签体系

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 3）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 3（标签体系；累计迁入 14 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈3h |
| 结论 | 批 3 完成：标签域迁入 + `useTabs` 投影与核心 `BaseTabs` 对齐语义，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 核心扩充 | `BaseTabs`：补 `find` / `has` / `activate` + **固定签排前（稳定排序，对齐旧 `sortTabs`）** |
| 新投影 | `@bms/vue` 增 `useTabs`（核心 `BaseTabs` ↔ Vue）：受控（`tabs` / `activeKey` 传入即受控，只经 `onChange` 回写）/ 非受控（核心状态 + 通知）；返回面 `tabs` / `activeKey` / `cachedNames` / `open` / `close` / `find` / `has` / `activate`（与旧片段同构） |
| 迁移（4 文件） | `TabsNav.vue`（多标签导航）/ `FormFrameTabs.vue`（双层标签）/ `types.ts`（`TabNavItem extends TabEntry`）/ `confirmClose.ts`——**注入式改造**：`configureDirtyConfirm`（宿主 / 弹窗能力接入时注入；未注入按占位语义放行），去除对旧 `@/i18n` 与 `@/utils/useConfirm` 的依赖 |
| 用例（+11，移植） | `tests/tabs-nav.spec.ts`（7 条：固定首签 / 点击导航 / 关闭相邻 / 右键五项 / 上限淘汰 / dirty 确认 / refresh 与受控回写）+ `tests/tabs-form-frame.spec.ts`（4 条：列表固定 / 多开激活 / 关闭相邻 / dirty）——由旧工程用例移植，`useConfirm` mock 改 **注入式**、i18n 消息子集自带 |
| 工程 | ui-ep devDeps 增 `vue-router`（用例路由场景） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **19**（8 组件 + 7 多标签 + 4 双层标签）用例 |
| `npm run ui-ep:typecheck` | 通过（vue-tsc） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | ui-ep 用例加载失败（缺 `vue-router`） | devDeps 补 `vue-router@^4.6.4`（与 apps/desktop 对齐） |
| 2 | 「固定首签排首位」用例失败 | 根因：**排序未随迁移**——核心 `BaseTabs` 与投影 `open` 均未做 pinned 前置 → 核心补稳定排序，投影 `open` 两路径统一 `sortTabs`（与旧 `sortTabs` 同口径） |
| 3 | `TabsNav` 依赖旧 `@/utils/useConfirm`（弹窗能力，批 4 才迁） | `confirmClose` 改**注入式**（`configureDirtyConfirm`；未注入放行）——解耦标签与弹窗的批次依赖 |
| 4 | ui-ep 用例 i18n 文案 | 测试自建 i18n 消息子集（`tabs.*`），不再依赖旧工程 `src/i18n` |

## 5. 偏差与遗留 <a id="deviations"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 已迁 14 / 约 42 件（余 ~28：布局余件 / 菜单 / 弹窗 / 反馈余（svg + 权限）/ 域包装 / 宿主壳） | S3 续批 4+ |
| 2 | `dirtyConfirm` 注入实现（弹窗接入后由 ui-ep 提供默认实现） | 批 4（modal 迁移后接 `configureDirtyConfirm`，文案走 i18n） |
| 3 | `TabsNav` 拖拽排序（`draggable`）与 `IconDisplay` 图标 | 迁移保真（未深入用例）；图标随回补波 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
