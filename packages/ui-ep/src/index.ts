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
