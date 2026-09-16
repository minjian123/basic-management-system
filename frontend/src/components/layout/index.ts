/**
 * 组件域出口：布局（`src/components/layout/`）。
 *
 * 当前批次：树形主从布局（`03-3-2`）与基础布局件（`03-3-3`，栅格 / 间距分割线 / 分栏 /
 * 内容页签 / 卡片 / 折叠面板）；框架壳（`AppLayout` / `FormFrame` / `PageContainer`）随 `03_05` 追加。
 */

export { default as MasterDetail } from './MasterDetail.vue'
export { default as MasterTree } from './MasterTree.vue'
export { default as GridRow } from './GridRow.vue'
export { default as GridCol } from './GridCol.vue'
export { default as Space } from './Space.vue'
export { default as Divider } from './Divider.vue'
export { default as Split } from './Split.vue'
export { default as Tabs } from './Tabs.vue'
export { default as TabPane } from './TabPane.vue'
export { default as Card } from './Card.vue'
export { default as Collapse } from './Collapse.vue'
export { default as CollapseItem } from './CollapseItem.vue'
export { default as AppLayout } from './AppLayout.vue'
export { default as FormFrame } from './FormFrame.vue'
export { default as PageContainer } from './PageContainer.vue'
export { useFormFrame } from './useFormFrame'
export { useMasterDetail } from './useMasterDetail'
export type { TreeNode, UseMasterDetailOptions, UseMasterDetailReturn } from './useMasterDetail'
