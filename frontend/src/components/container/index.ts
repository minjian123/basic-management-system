/**
 * 容器组件类出口（通用容器；滚动容器 / 懒加载容器 / 虚拟列表容器起步）。
 */

export { default as ScrollContainer } from './ScrollContainer.vue'
export { default as LazyContainer } from './LazyContainer.vue'
export { default as VirtualList } from './VirtualList.vue'
export { default as FullscreenContainer } from './FullscreenContainer.vue'
export { default as AutoHeight } from './AutoHeight.vue'
export { default as AspectRatio } from './AspectRatio.vue'
export {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
} from './scrollPosition'
export { resolveSize } from './size'
export { useVirtualRange } from './useVirtualRange'
export type { VirtualRangeOptions, VirtualRangeReturn } from './useVirtualRange'
export type {
  ScrollMetrics,
  ScrollPositionStore,
  ScrollStorage,
  VirtualScrollMetrics,
} from './types'
