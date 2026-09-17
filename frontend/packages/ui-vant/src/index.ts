/**
 * @bms/ui-vant：移动端实现插件（Vant）。
 *
 * 组件实现依赖 `@bms/core`（能力与协议）与 `@bms/vue`（绑定投影）；
 * 与 `@bms/ui-ep`（PC 实现插件）为同一契约的多实现（契约测试同一套断言）。
 */

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
export {
  AspectRatio,
  AutoHeight,
  FullscreenContainer,
  LazyContainer,
  LoadingContainer,
  ScrollContainer,
  SectionContainer,
  VirtualList,
} from './components/container'
export {
  EmptyState,
  ErrorPage,
  LoadingMask,
  SkeletonBlock,
  type FeedbackAction,
} from './components/feedback'
export {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
  resolveSize,
  type ScrollMetrics,
  type ScrollPositionStore,
  type ScrollStorage,
  type VirtualScrollMetrics,
} from '@bms/core'
export { useVirtualRange, type VirtualRangeOptions, type VirtualRangeReturn } from '@bms/vue'
