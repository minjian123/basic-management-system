/**
 * 组件域出口：通用容器（域 04 交付；S4a 起滚动基建与可视区计算单份在 `@bms/core` / `@bms/vue`）。
 */

export { default as ScrollContainer } from './ScrollContainer.vue'
export { default as SectionContainer } from './SectionContainer.vue'
export { default as LoadingContainer } from './LoadingContainer.vue'
export { default as LazyContainer } from './LazyContainer.vue'
export { default as AutoHeight } from './AutoHeight.vue'
export { default as AspectRatio } from './AspectRatio.vue'
export { default as VirtualList } from './VirtualList.vue'
export { default as FullscreenContainer } from './FullscreenContainer.vue'
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
