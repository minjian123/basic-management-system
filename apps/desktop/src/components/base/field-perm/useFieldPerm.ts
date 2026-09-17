/**
 * 字段权限片段（`field-perm`）：字段级 `visible` / `editable` / `required` 三态与脱敏标注。
 *
 * 契约见《组件设计 · 字段权限片段》（本篇为该口径的权威定义）：依据**表单元数据下发的字段权限**
 * 返回可见 / 可编辑 / 必填，并提供脱敏判定（明文切换由 `v-plain` 指令协作，指令归 `02_06`）。
 * **占位先行**：权限码集合由后端权限上下文接入前为空集 → 判定回落到元数据入参（不请求、不报错）。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 字段权限三态 */
export type FieldPermState = 'hidden' | 'readonly' | 'editable'

/** 字段权限片段参数（缺省 = 可见可编辑，便于无权限体系时直用） */
export interface UseFieldPermOptions {
  visible?: MaybeRefOrGetter<boolean>
  editable?: MaybeRefOrGetter<boolean>
  required?: MaybeRefOrGetter<boolean>
  /** 是否脱敏（配合 `v-plain` 明文切换） */
  masked?: MaybeRefOrGetter<boolean>
  /** 权限码集合（后端权限上下文接入后注入；未接入时为空集 → 占位） */
  codes?: MaybeRefOrGetter<string[]>
}

/** 字段权限片段返回值 */
export interface UseFieldPermReturn {
  readonly visible: boolean
  readonly editable: boolean
  readonly required: boolean
  readonly masked: boolean
  /** 三态：隐藏 / 只读 / 可编辑 */
  readonly state: FieldPermState
  readonly canEdit: boolean
  readonly disabled: boolean
  /** 权限码是否已接入（未接入 = 占位：判定只依据元数据入参） */
  readonly isPlaceholder: boolean
  /** 脱敏文本（保留首尾各 1 字符，短文本全遮） */
  mask: (text: string) => string
  /** 字段属性（供壳与控件透传：`data-perm` 三态、`data-plain-capable` 明文协作） */
  readonly permAttrs: Record<string, string>
}

/**
 * 获取字段权限能力。
 *
 * 用法：`const perm = useFieldPerm({ visible, editable, required })`；渲染器据此决定整壳不渲染 / 置 disabled。
 */
export function useFieldPerm(options: UseFieldPermOptions = {}): UseFieldPermReturn {
  declareFragment('field-perm')

  const codes = computed(() => toValue(options.codes))
  const visible = computed(() => (options.visible === undefined ? true : Boolean(toValue(options.visible))))
  const editable = computed(() => (options.editable === undefined ? true : Boolean(toValue(options.editable))))
  const required = computed(() => Boolean(toValue(options.required)))
  const masked = computed(() => Boolean(toValue(options.masked)))

  const state = computed<FieldPermState>(() => {
    if (!visible.value) {
      return 'hidden'
    }
    return editable.value ? 'editable' : 'readonly'
  })

  const permAttrs = computed<Record<string, string>>(() => ({
    'data-perm': state.value,
    'data-plain-capable': masked.value ? 'true' : 'false',
  }))

  const mask = (text: string): string => {
    if (!masked.value) {
      return text
    }
    if (text.length <= 2) {
      return '*'.repeat(text.length)
    }
    return `${text.slice(0, 1)}${'*'.repeat(text.length - 2)}${text.slice(-1)}`
  }

  return {
    get visible() {
      return visible.value
    },
    get editable() {
      return editable.value
    },
    get required() {
      return required.value
    },
    get masked() {
      return masked.value
    },
    get state() {
      return state.value
    },
    get canEdit() {
      return state.value === 'editable'
    },
    get disabled() {
      return state.value !== 'editable'
    },
    get isPlaceholder() {
      return codes.value === undefined
    },
    mask,
    get permAttrs() {
      return permAttrs.value
    },
  }
}
