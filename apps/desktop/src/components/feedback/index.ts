/**
 * 组件域出口：异常与空状态（`src/components/feedback/`）。
 *
 * 契约见《组件设计 · 异常与空状态》：`ErrorPage` / `EmptyState` / `SkeletonBlock` / `LoadingMask`
 * 四件 + 组合式 `useFeedback`（`src/utils/`，类型经此出口再导出；组合式本身直接自 utils 导入）。
 */

export { default as ErrorPage } from './ErrorPage.vue'
export { default as EmptyState } from './EmptyState.vue'
export { default as SkeletonBlock } from './SkeletonBlock.vue'
export { default as LoadingMask } from './LoadingMask.vue'
export type { FeedbackAction } from './types'
export type {
  FeedbackError,
  FeedbackState,
  UseFeedbackOptions,
  UseFeedbackReturn,
} from '@/utils/useFeedback'
