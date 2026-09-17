/**
 * 组件域出口：弹窗抽屉表单（`ui-ep/src/components/modal/`）。
 *
 * 三容器（`FormDrawer` / `FormDialog` / `ConfirmDialog`）+ 组合式 `useModalShell`；
 * 应用级 `useFormModal` / `useConfirm` 归宿主装配（S5）。
 */

export { default as FormDrawer } from './FormDrawer.vue'
export { default as FormDialog } from './FormDialog.vue'
export { default as ConfirmDialog } from './ConfirmDialog.vue'
export type {
  FormModalMode,
  FormModalWidth,
  SharedModalEmits,
  SharedModalProps,
  UseModalShellOptions,
  UseModalShellReturn,
} from './useModalShell'
