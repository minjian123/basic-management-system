/**
 * @bms/ui-ep：PC 实现插件（Element Plus）。
 *
 * 组件实现依赖 `@bms/core`（能力与协议）与 `@bms/vue`（绑定投影）；
 * 与 `@bms/ui-vant`（移动端实现插件）为同一契约的多实现（契约测试同一套断言）。
 */

export { default as GridRow } from './components/layout/GridRow.vue'
export { default as GridCol } from './components/layout/GridCol.vue'
export { default as Space } from './components/layout/Space.vue'
export { default as Divider } from './components/layout/Divider.vue'
export { default as SkeletonBlock } from './components/feedback/SkeletonBlock.vue'
export { default as Card } from './components/layout/Card.vue'
export { default as Collapse } from './components/layout/Collapse.vue'
export { default as CollapseItem } from './components/layout/CollapseItem.vue'
export { default as Tabs } from './components/layout/Tabs.vue'
export { default as TabPane } from './components/layout/TabPane.vue'
export { default as Split } from './components/layout/Split.vue'
export { default as LoadingMask } from './components/feedback/LoadingMask.vue'
export { default as TabsNav } from './components/tabs/TabsNav.vue'
export { default as FormFrameTabs } from './components/tabs/FormFrameTabs.vue'
export { configureDirtyConfirm, type DirtyConfirm } from './components/tabs/confirmClose'
export type { TabNavItem } from './components/tabs/types'
