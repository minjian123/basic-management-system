/**
 * `@bms/ui-ep`：PC 渲染插件入口（Element Plus 组件实现）。
 *
 * 具体组件按族分目录（`src/components/<族>/`）；组合式落 `src/composables/`。
 */

export { default as ConfirmDialog } from './components/modal/ConfirmDialog.vue'
export { useConfirm, type ConfirmOptions, type ConfirmState } from './composables/useConfirm'
