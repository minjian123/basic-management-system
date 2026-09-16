/**
 * 字段编排片段（`field`）：字段的最终组合——值语义 + 字段壳 + 字段权限 + 校验触发。
 *
 * 契约见《组件设计 · 字段编排片段》：字段类组件的统一入口。**组合依赖**（单向、已登记）：
 * `value`（值语义）+ `field-shell`（壳）+ `field-perm`（权限）；本片段只做编排与校验触发，
 * 具体控件、选项源与渲染分发归消费方组件。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import { useFieldPerm, type FieldPermState, type UseFieldPermReturn } from '../field-perm/useFieldPerm'
import { useFieldShell, type UseFieldShellReturn } from '../field-shell/useFieldShell'
import { useValue, type UseValueReturn } from '../value/useValue'

/** 字段编排片段参数 */
export interface UseFieldOptions<T = unknown> {
  /** 字段标识（与表单元数据 `key` 对齐） */
  fieldKey: string
  label?: MaybeRefOrGetter<string>
  required?: MaybeRefOrGetter<boolean>
  help?: MaybeRefOrGetter<string>
  span?: MaybeRefOrGetter<number>
  modelValue?: MaybeRefOrGetter<T>
  emptyValue?: T
  formatter?: (value: T) => string
  threeState?: MaybeRefOrGetter<boolean>
  /** 字段权限入参（缺省：可见可编辑；由表单元数据下发） */
  perm?: {
    visible?: MaybeRefOrGetter<boolean>
    editable?: MaybeRefOrGetter<boolean>
    required?: MaybeRefOrGetter<boolean>
    masked?: MaybeRefOrGetter<boolean>
    codes?: MaybeRefOrGetter<string[]>
  }
  /** 自定义校验（返回错误文案表示不通过；必填与三态由本片段判定） */
  validator?: () => string | undefined
  /** 值变更上报 */
  onChange?: (value: T | undefined) => void
  /** 校验失败回调（渲染器据此滚动 / 提示） */
  onValidateFail?: (message: string) => void
}

/** 字段上下文（供渲染器与子控件取用） */
export interface FieldContext {
  readonly fieldKey: string
  readonly label: string
  readonly required: boolean
  readonly readonly: boolean
  readonly disabled: boolean
  readonly permState: FieldPermState
}

/** 字段编排片段返回值 */
export interface UseFieldReturn<T = unknown> {
  readonly value: T | undefined
  readonly display: string
  readonly isUnset: boolean
  readonly isCleared: boolean
  readonly shell: UseFieldShellReturn
  readonly perm: UseFieldPermReturn
  readonly valueFragment: UseValueReturn<T>
  /** 字段上下文（渲染器 / 子控件统一取用） */
  readonly fieldContext: FieldContext
  /** 字段根属性（壳与权限属性合并，供根元素透传） */
  readonly fieldAttrs: Record<string, unknown>
  setValue: (value: unknown) => void
  clear: () => void
  /** 校验（不可见 / 只读字段直接通过）；返回是否通过 */
  validate: () => boolean
  /** 清空校验错误 */
  resetValidation: () => void
}

/**
 * 获取字段编排能力。
 *
 * 用法：`const field = useField({ fieldKey: 'name', label, modelValue, onChange })`；
 * 模板里把 `field.fieldAttrs` 透传到字段根元素，错误经 `field.shell.errorText` 展示。
 */
export function useField<T = unknown>(options: UseFieldOptions<T>): UseFieldReturn<T> {
  declareFragment('field')

  const errorMessage = ref('')

  const perm = useFieldPerm({
    ...(options.perm?.visible !== undefined ? { visible: options.perm.visible } : {}),
    ...(options.perm?.editable !== undefined ? { editable: options.perm.editable } : {}),
    ...(options.perm?.required !== undefined ? { required: options.perm.required } : {}),
    ...(options.perm?.masked !== undefined ? { masked: options.perm.masked } : {}),
    ...(options.perm?.codes !== undefined ? { codes: options.perm.codes } : {}),
  })

  const required = computed(() =>
    options.perm?.required !== undefined ? perm.required : Boolean(toValue(options.required)) || perm.required,
  )

  const shell = useFieldShell({
    ...(options.label !== undefined ? { label: options.label } : {}),
    fieldKey: options.fieldKey,
    required,
    ...(options.help !== undefined ? { help: options.help } : {}),
    ...(options.span !== undefined ? { span: options.span } : {}),
    readonlyMode: computed(() => !perm.canEdit),
    visible: computed(() => perm.visible),
    error: computed(() => errorMessage.value),
  })

  const valueFragment = useValue<T>({
    ...(options.modelValue !== undefined ? { modelValue: options.modelValue } : {}),
    ...(options.emptyValue !== undefined ? { emptyValue: options.emptyValue } : {}),
    ...(options.formatter ? { formatter: options.formatter } : {}),
    ...(options.threeState !== undefined ? { threeState: options.threeState } : {}),
    ...(options.onChange ? { onChange: options.onChange } : {}),
  })

  const fieldContext = computed<FieldContext>(() => ({
    fieldKey: options.fieldKey,
    label: shell.labelText,
    required: required.value,
    readonly: !perm.canEdit,
    disabled: perm.disabled,
    permState: perm.state,
  }))

  const fieldAttrs = computed<Record<string, unknown>>(() => ({
    ...shell.shellAttrs,
    ...perm.permAttrs,
  }))

  const validate = (): boolean => {
    if (!perm.visible || !perm.canEdit) {
      errorMessage.value = ''
      return true
    }
    let message: string | undefined
    if (required.value && valueFragment.isUnset) {
      message = '该字段必填'
    }
    if (!message) {
      message = options.validator?.()
    }
    errorMessage.value = message ?? ''
    if (message) {
      options.onValidateFail?.(message)
      return false
    }
    return true
  }

  return {
    get value() {
      return valueFragment.value
    },
    get display() {
      return perm.masked && !valueFragment.isUnset ? perm.mask(valueFragment.display) : valueFragment.display
    },
    get isUnset() {
      return valueFragment.isUnset
    },
    get isCleared() {
      return valueFragment.isCleared
    },
    shell,
    perm,
    valueFragment,
    get fieldContext() {
      return fieldContext.value
    },
    get fieldAttrs() {
      return fieldAttrs.value
    },
    setValue: (value) => {
      valueFragment.setValue(value)
    },
    clear: () => {
      valueFragment.clear()
    },
    validate,
    resetValidation: () => {
      errorMessage.value = ''
    },
  }
}
