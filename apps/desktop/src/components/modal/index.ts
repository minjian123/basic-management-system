/**
 * 组件域出口：弹窗抽屉表单（`src/components/modal/`）。
 *
 * 契约见《组件设计 · 弹窗抽屉表单》：`FormDrawer` / `FormDialog` / `ConfirmDialog`
 * 三容器 + 组合式 `useFormModal` / `useConfirm`（`src/utils/`，不经本出口）。
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
