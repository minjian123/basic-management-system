/**
 * @bms/vue：Vue 绑定插件（组合式投影）。
 *
 * 口径：核心能力（@bms/core）为单一来源；本包只做「实例化 + 响应式投影 + 生命周期桥接」，
 * 不重复实现能力逻辑，不依赖 Element Plus / Vant（UI 实现在 ui-ep / ui-vant 插件）。
 */

export { useValue, type UseValueReturn } from './bindings/useValue'
export { useField, type UseFieldReturn } from './bindings/useField'
