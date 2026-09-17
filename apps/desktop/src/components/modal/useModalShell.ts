/**
 * 弹窗容器共享壳（内部组合式，非能力片段）。
 *
 * FormDrawer / FormDialog 共用「三态标题 / 尺寸阶梯 / 关闭拦截链 / 页脚动作」口径，
 * 两个容器不各写一套（《组件设计 · 弹窗抽屉表单》§4 / §7）；渲染差异（el-drawer / el-dialog）
 * 与 EP 参数由各容器承担。
 */

import { computed, type ComputedRef } from 'vue'

import { i18n } from '@/i18n'
import { hasPerm } from '@/utils/perm'
import { useConfirm } from '@/utils/useConfirm'

/** 弹窗表单三态 */
export type FormModalMode = 'create' | 'edit' | 'view'

/** 尺寸档位 */
export type FormModalWidth = 'sm' | 'md' | 'lg' | 'xl'

/** 容器共用 props（FormDrawer / FormDialog 同款签名） */
export interface SharedModalProps {
  modelValue: boolean
  mode: FormModalMode
  title: string | null
  width: FormModalWidth | number | string
  submitLoading: boolean
  confirmOnClose: boolean
  closeOnClickModal: boolean
  closeOnPressEscape: boolean
  destroyOnClose: boolean
  lockScroll: boolean
  showFooter: boolean
  submitText: string
  cancelText: string
  submitPerm: string | null
  showDelete: boolean
  deleteText: string
  /** 脏状态（页面由 `useFormModal` 传入；容器据此拦截并转发 `dirty-change`） */
  dirty: boolean
  /** 自定义关闭前钩子（脏数据拦截之后串联；不调 `done` 视为拒绝关闭） */
  beforeClose: ((done: () => void) => void) | null
  /** 删除入口回调（`view` / `edit` 态且传入时显示；先经危险确认） */
  deleteHandler: ((mode: FormModalMode) => void) | null
}

/** 容器共用事件 */
export interface SharedModalEmits {
  'update:modelValue': [value: boolean]
  open: [mode: FormModalMode]
  opened: [mode: FormModalMode]
  submit: []
  success: [data: unknown]
  cancel: []
  close: []
  closed: []
  'dirty-change': [dirty: boolean]
  /** 查看态「编辑」入口（由使用方切换 mode） */
  edit: []
  'reset-fields': []
  'set-form-data': [data: Record<string, unknown>]
}

/** 共享壳参数 */
export interface UseModalShellOptions {
  /** 档位 → 像素宽度（各容器一套阶梯） */
  widthMap: Record<FormModalWidth, number>
}

/** 共享壳返回值 */
export interface UseModalShellReturn {
  /** 「动作词 + 对象名」标题 */
  titleText: ComputedRef<string>
  /** 宽度（档位 → 像素；数值 / 字符串原样） */
  widthValue: ComputedRef<string | number>
  submitVisible: ComputedRef<boolean>
  editVisible: ComputedRef<boolean>
  deleteVisible: ComputedRef<boolean>
  submitLabel: ComputedRef<string>
  cancelLabel: ComputedRef<string>
  deleteLabel: ComputedRef<string>
  /** 关闭拦截链（提交中 → 脏数据确认 → `beforeClose`）；返回是否放行 */
  runCloseChain: () => Promise<boolean>
  /** 删除入口（危险确认后调用 `deleteHandler`） */
  onDelete: () => Promise<void>
}

const TITLE_KEYS: Record<FormModalMode, string> = {
  create: 'modal.titleCreate',
  edit: 'modal.titleEdit',
  view: 'modal.titleView',
}

/** 权限码缺省放行（`null` / 空字符串不限制） */
function permitOk(code: string | null): boolean {
  return !code || hasPerm(code)
}

/**
 * 获取弹窗容器共享壳。
 *
 * 用法：容器内 `const shell = useModalShell(props, { widthMap })`，再绑定页脚 / 标题 / 拦截链。
 */
export function useModalShell(
  props: SharedModalProps,
  options: UseModalShellOptions,
): UseModalShellReturn {
  const { confirm } = useConfirm()
  const t = i18n.global.t as unknown as (key: string, named?: Record<string, unknown>) => string

  const titleText = computed(() => {
    const raw = t(TITLE_KEYS[props.mode] ?? 'modal.titleCreate', { name: props.title ?? '' })
    return raw.trim()
  })

  const widthValue = computed<string | number>(() => {
    const width = props.width
    if (typeof width === 'number') {
      return width
    }
    const mapped = (options.widthMap as Record<string, number | undefined>)[width]
    return mapped ?? width
  })

  const submitVisible = computed(() => props.mode !== 'view' && permitOk(props.submitPerm))
  const editVisible = computed(
    () => props.mode === 'view' && !!props.submitPerm && permitOk(props.submitPerm),
  )
  const deleteVisible = computed(
    () =>
      props.showDelete &&
      props.mode !== 'create' &&
      props.deleteHandler !== null &&
      hasPerm('business:delete'),
  )

  const submitLabel = computed(() => props.submitText || t('common.save'))
  const cancelLabel = computed(() => props.cancelText || t('common.cancel'))
  const deleteLabel = computed(() => props.deleteText || t('common.delete'))

  async function runCloseChain(): Promise<boolean> {
    if (props.submitLoading) {
      return false
    }
    if (props.dirty && props.confirmOnClose && props.mode !== 'view') {
      const allowed = await confirm({
        title: t('modal.unsavedTitle'),
        message: t('modal.unsavedMessage'),
        confirmText: t('modal.abandon'),
        cancelText: t('modal.continueEdit'),
      })
      if (!allowed) {
        return false
      }
    }
    if (props.beforeClose) {
      return await new Promise<boolean>((resolve) => {
        props.beforeClose!(() => resolve(true))
      })
    }
    return true
  }

  async function onDelete(): Promise<void> {
    const allowed = await confirm({ message: t('modal.deleteConfirm') })
    if (allowed) {
      props.deleteHandler?.(props.mode)
    }
  }

  return {
    titleText,
    widthValue,
    submitVisible,
    editVisible,
    deleteVisible,
    submitLabel,
    cancelLabel,
    deleteLabel,
    runCloseChain,
    onDelete,
  }
}
