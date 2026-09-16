# 框架无关核心重构 · S3e 实施记录（ui-ep 重建 · 批 4b）：弹窗抽屉表单

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 4b）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 4b（弹窗抽屉表单；累计迁入 20 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈2.5h |
| 结论 | 批 4b 完成：确认注入点收敛 + 弹窗域 3 件 + `useModalShell` 迁移，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 确认注入点收敛（改） | 新增 `ui-ep/src/confirm.ts`：`configureConfirm(handler)` / `confirm(options)`——**默认实现 = `ElMessageBox.confirm`**（非占位放行，真实可用），宿主可覆盖；`confirmClose.ts` 改用 `confirm()`（删 `DirtyConfirm` / `configureDirtyConfirm`，未注入亦真实弹确认）；批 3 两条 spec 同步改 `configureConfirm` |
| 迁移（3 件 + 组合式） | `FormDialog` / `FormDrawer`（`useModalShell` 三态标题、宽度档位、页脚动作含 `submitPerm` 与删除权限、关闭拦截链、`defineExpose` submit/close/resetFields/setFormData）、`ConfirmDialog`（缺省标题、danger 语义、强制禁遮罩 / Esc 不关）、`useModalShell.ts`（共享 props / emits / 关闭链）与 `index.ts` |
| 依赖改造 | `useComponentBase` → `@bms/vue`；`i18n` 单例 → `useI18n()`；`hasPerm` → `checkPerm`（权限注入点）；`useConfirm` → `confirm`（确认注入点）；`useContainer` 声明删除（无返回值使用，容器语义由组件结构直接承担）；EP `ElDialog` / `ElDrawer` / `ElButton` 显式导入与按需样式 |
| 用例（+5） | `tests/modal.spec.ts`：FormDialog 三态标题 + 页脚动作（提交 emit）/ 关闭拦截链（确认拒绝不放行、放行 cancel）/ 权限控制（`submitPerm` 空集隐藏提交）；FormDrawer 渲染与标题；ConfirmDialog 缺省标题 + 取消 / 确定事件 |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **31** 用例（8 + 1 + 5 文件），vue-tsc 无错 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| EP 弹窗首次以 `modelValue=true` 挂载不渲染（懒渲染） | 测试装置改「先关后开」：`mount({ modelValue: false })` → `setProps({ modelValue: true })` → `nextTick()` 后断言 |
| EP 弹窗经 Teleport 渲染，`wrapper.find` 不命中 | 测试装置 `global.stubs: { teleport: true }`（内容留在 wrapper 内）；`setProps` 需 `as never`（组件类型为泛型参数） |
| 批 3「确认未注入放行」的占位语义 | 本轮升级为**默认 `ElMessageBox` 实现**（真实确认可用）；`configureConfirm` 仍可覆盖（宿主自定义 UI） |

## 5. 回写清单 <a id="writeback"></a>

| 文档 | 回写点 |
| --- | --- |
| [任务文档](../02_基础组件类_07_框架无关核心重构.md) | 状态行（S3 批 4b）与阶段记录追加 |
| [计划](../../../../计划/01_计划_前端组件库.md) | §3 表 `02_07` 行（批 4b 与累计 20 件、用例数） |
