/**
 * 组件域出口：多标签导航（`src/components/tabs/`）。
 *
 * 契约见《组件设计 · 多标签导航》：`TabsNav`（页面级）/ `FormFrameTabs`（表单框架双层）
 * + 公共类型；状态核心为片段 `base/tabs/useTabs`（直接自片段层导入）。
 */

export { default as TabsNav } from './TabsNav.vue'
export { default as FormFrameTabs } from './FormFrameTabs.vue'
export type { TabNavItem } from './types'
