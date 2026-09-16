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
export { default as ErrorPage } from './components/feedback/ErrorPage.vue'
export { default as EmptyState } from './components/feedback/EmptyState.vue'
export type { FeedbackAction } from './components/feedback/types'
export { default as PermButton } from './components/common/PermButton.vue'
export { checkPerm, configurePermissionChecker, type PermissionChecker, type PermissionMode } from './permission'
export { confirm, configureConfirm, type ConfirmHandler, type ConfirmOptions } from './confirm'
export { default as FormDrawer } from './components/modal/FormDrawer.vue'
export { default as FormDialog } from './components/modal/FormDialog.vue'
export { default as ConfirmDialog } from './components/modal/ConfirmDialog.vue'
export type {
  FormModalMode,
  FormModalWidth,
  SharedModalEmits,
  SharedModalProps,
  UseModalShellOptions,
  UseModalShellReturn,
} from './components/modal/useModalShell'

export { default as TabsNav } from './components/tabs/TabsNav.vue'
export { default as FormFrameTabs } from './components/tabs/FormFrameTabs.vue'
export { confirmDirtyClose } from './components/tabs/confirmClose'
export type { TabNavItem } from './components/tabs/types'
