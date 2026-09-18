/**
 * `@bms/ui-ep`：PC 渲染插件入口（Element Plus 组件实现）。
 *
 * 具体组件按族分目录（`src/components/<族>/`）；组合式落 `src/composables/`。
 */

export { default as ConfirmDialog } from './components/modal/ConfirmDialog.vue'
export { default as FormDialog } from './components/modal/FormDialog.vue'
export { default as FormDrawer } from './components/modal/FormDrawer.vue'
export { useConfirm, type ConfirmOptions, type ConfirmState } from './composables/useConfirm'
export { useModalShell, type UseModalShellResult } from './composables/useModalShell'
export {
  useFormModal,
  type FormMode,
  type UseFormModalOptions,
  type UseFormModalResult,
} from './composables/useFormModal'
