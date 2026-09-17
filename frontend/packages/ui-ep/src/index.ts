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
export {
  BaseInput,
  NumberInput,
  PasswordField,
  SelectInput,
  TextareaField,
  TextField,
} from './components/input'
export { checkPerm, configurePermissionChecker, type PermissionChecker, type PermissionMode } from './permission'
export { confirm, configureConfirm, type ConfirmHandler, type ConfirmOptions } from './confirm'
export { default as ScrollContainer } from './components/container/ScrollContainer.vue'
export { default as SectionContainer } from './components/container/SectionContainer.vue'
export { default as LoadingContainer } from './components/container/LoadingContainer.vue'
export { default as LazyContainer } from './components/container/LazyContainer.vue'
export { default as AutoHeight } from './components/container/AutoHeight.vue'
export { default as AspectRatio } from './components/container/AspectRatio.vue'
export { default as VirtualList } from './components/container/VirtualList.vue'
export { default as FullscreenContainer } from './components/container/FullscreenContainer.vue'
export {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
  resolveSize,
  useVirtualRange,
  type ScrollMetrics,
  type ScrollPositionStore,
  type ScrollStorage,
  type VirtualRangeOptions,
  type VirtualRangeReturn,
  type VirtualScrollMetrics,
} from './components/container'
export { default as AppLayout } from './components/layout/AppLayout.vue'
export { default as PageContainer } from './components/layout/PageContainer.vue'
export { default as FormFrame } from './components/layout/FormFrame.vue'
export { default as MasterDetail } from './components/layout/MasterDetail.vue'
export { default as MasterTree } from './components/layout/MasterTree.vue'
export { configureViewResolver, nameComponent, resolveView, type ViewResolver } from './components/layout/viewResolver'
export { useFormFrame, type UseFormFrameReturn } from './components/layout/useFormFrame'
export { useMasterDetail, type TreeNode, type UseMasterDetailReturn } from './components/layout/useMasterDetail'
export { default as MenuNode } from './components/menu/MenuNode.vue'
export { default as SideMenu } from './components/menu/SideMenu.vue'
export {
  configureMenuSource,
  getMenuSource,
  filterMenuTree,
  findAncestorKeys,
  menuKey,
  sortVisible,
  type MenuItem,
  type MenuSourceProvider,
} from './components/menu'
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
