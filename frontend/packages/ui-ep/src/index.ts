/**
 * `@bms/ui-ep`：PC 渲染插件入口（Element Plus 组件实现）。
 *
 * 具体组件按族分目录（`src/components/<族>/`）；组合式落 `src/composables/`。
 */

export { default as EmptyState, type EmptyStateType } from './components/feedback/EmptyState.vue'
export { default as ErrorPage, type ErrorPageCode } from './components/feedback/ErrorPage.vue'
export { default as LoadingMask } from './components/feedback/LoadingMask.vue'
export { default as SkeletonBlock, type SkeletonBlockVariant } from './components/feedback/SkeletonBlock.vue'
export { default as AspectRatioContainer } from './components/container/AspectRatioContainer.vue'
export { default as AutoHeightContainer } from './components/container/AutoHeightContainer.vue'
export { default as FullscreenContainer } from './components/container/FullscreenContainer.vue'
export { default as LazyContainer } from './components/container/LazyContainer.vue'
export { default as ScrollContainer } from './components/container/ScrollContainer.vue'
export { default as StatusContainer, type StatusContainerState } from './components/container/StatusContainer.vue'
export { default as VirtualListContainer } from './components/container/VirtualListContainer.vue'
export { default as SectionContainer } from './components/container/SectionContainer.vue'
export { default as CollapsePanel } from './components/layout/CollapsePanel.vue'
export { default as DualTabs } from './components/layout/DualTabs.vue'
export { default as FormLayoutShell } from './components/layout/FormLayoutShell.vue'
export { default as MainLayout } from './components/layout/MainLayout.vue'
export { default as PageContainer, type BreadcrumbItem } from './components/layout/PageContainer.vue'
export { default as SideMenu } from './components/layout/SideMenu.vue'
export { default as SideMenuItem } from './components/layout/SideMenuItem.vue'
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
  useBaseContainer,
  type UseBaseContainerOptions,
  type UseBaseContainerResult,
} from './composables/useBaseContainer'
export {
  useBaseLayout,
  type UseBaseLayoutOptions,
  type UseBaseLayoutResult,
} from './composables/useBaseLayout'
export {
  useBaseDisplay,
  type UseBaseDisplayResult,
} from './composables/useBaseDisplay'
export {
  useBaseTreeData,
  type UseBaseTreeDataOptions,
  type UseBaseTreeDataResult,
} from './composables/useBaseTreeData'
export {
  useBaseAccess,
  type UseBaseAccessResult,
} from './composables/useBaseAccess'
export {
  useBasePersistedState,
  type UseBasePersistedStateOptions,
  type UseBasePersistedStateResult,
} from './composables/useBasePersistedState'
export {
  useBaseDesignToken,
  type UseBaseDesignTokenOptions,
  type UseBaseDesignTokenResult,
} from './composables/useBaseDesignToken'
export {
  DEFAULT_BREAKPOINTS,
  useResponsive,
  type ResponsiveBreakpoint,
  type ResponsiveBreakpoints,
  type UseResponsiveOptions,
  type UseResponsiveResult,
} from './composables/useResponsive'
export {
  useFormShell,
  type DetailRecord,
  type UseFormShellOptions,
  type UseFormShellResult,
} from './composables/useFormShell'
export {
  useSideMenu,
  type UseSideMenuOptions,
  type UseSideMenuResult,
} from './composables/useSideMenu'
export {
  useTabNav,
  type TabNavItem,
  type UseTabNavOptions,
  type UseTabNavResult,
} from './composables/useTabNav'
export { useModalShell, type UseModalShellResult } from './composables/useModalShell'
export {
  useFormModal,
  type UseFormModalOptions,
  type UseFormModalResult,
} from './composables/useFormModal'
export {
  useBaseFormPage,
  type FormMode,
  type UseBaseFormPageOptions,
  type UseBaseFormPageResult,
} from './composables/useBaseFormPage'
