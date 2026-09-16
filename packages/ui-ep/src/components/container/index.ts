/**
 * 组件域出口：通用容器（域 04 交付；滚动基建随迁，其余件分批迁移）。
 */

export { default as ScrollContainer } from './ScrollContainer.vue'
export { default as SectionContainer } from './SectionContainer.vue'
export { default as LoadingContainer } from './LoadingContainer.vue'
export { default as LazyContainer } from './LazyContainer.vue'
export { default as AutoHeight } from './AutoHeight.vue'
export { default as AspectRatio } from './AspectRatio.vue'
export {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
} from './scrollPosition'
export { resolveSize } from './size'
export { useVirtualRange, type VirtualRangeOptions, type VirtualRangeReturn } from './useVirtualRange'
export type {
  ScrollMetrics,
  ScrollPositionStore,
  ScrollStorage,
  VirtualScrollMetrics,
} from './types'
