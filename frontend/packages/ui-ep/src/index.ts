/**
 * `@bms/ui-ep`：PC 渲染插件入口（Element Plus 组件实现）。
 *
 * 具体组件按族分目录（`src/components/<族>/`）；组合式落 `src/composables/`。
 */

export { default as EmptyState, type EmptyStateType } from './components/feedback/EmptyState.vue'
export { default as ErrorPage, type ErrorPageCode } from './components/feedback/ErrorPage.vue'
export { default as LoadingMask } from './components/feedback/LoadingMask.vue'
export { default as SkeletonBlock, type SkeletonBlockVariant } from './components/feedback/SkeletonBlock.vue'
export { default as CollapsePanel } from './components/layout/CollapsePanel.vue'
export { default as DualTabs } from './components/layout/DualTabs.vue'
export { default as TabNavBar } from './components/layout/TabNavBar.vue'
export { default as TabNavContextMenu, type TabNavAction } from './components/layout/TabNavContextMenu.vue'
export { default as CollapsePanelGroup } from './components/layout/CollapsePanelGroup.vue'
export { default as ContentTabs, type ContentTabItem } from './components/layout/ContentTabs.vue'
export { default as GridItem } from './components/layout/GridItem.vue'
export { default as GridLayout, type GridAlign, type GridJustify } from './components/layout/GridLayout.vue'
export { default as LayoutCard, type CardPadding } from './components/layout/LayoutCard.vue'
export { default as SpacingDivider, type SpacingSize } from './components/layout/SpacingDivider.vue'
export { default as SplitPane, type SplitDirection } from './components/layout/SplitPane.vue'
export { default as TreeMasterDetail, type MasterTreeNode } from './components/layout/TreeMasterDetail.vue'
export { default as ConfirmDialog } from './components/modal/ConfirmDialog.vue'
export { default as FormDialog } from './components/modal/FormDialog.vue'
export { default as FormDrawer } from './components/modal/FormDrawer.vue'
export { useConfirm, type ConfirmOptions, type ConfirmState } from './composables/useConfirm'
export { useFeedback, type UseFeedbackResult } from './composables/useFeedback'
export {
  useTabNav,
  type TabNavItem,
  type UseTabNavOptions,
  type UseTabNavResult,
} from './composables/useTabNav'
export { useModalShell, type UseModalShellResult } from './composables/useModalShell'
export {
  useFormModal,
  type FormMode,
  type UseFormModalOptions,
  type UseFormModalResult,
} from './composables/useFormModal'
