/**
 * 表单容器片段（`form-container`）：表单 / 分区 / 校验汇总的公共形态。
 *
 * 契约见《组件设计 · 表单容器片段》：label 位置与宽度、栅格、规则汇总、`validate` / `reset`、
 * 错误定位、只读态。片段不绑定具体控件（控件校验由渲染器或字段链提供），只做**规则汇总与调度**。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 校验规则（对齐后端表单校验口径：必填 / 长度 / 正则 / 自定义） */
export interface FormRule {
  required?: boolean
  min?: number
  max?: number
  pattern?: RegExp
  message?: string
  validator?: (value: unknown) => boolean | string
}

/** 表单元数据（片段只消费摘要信息） */
export interface FormFieldMeta {
  /** 字段标识（错误定位用） */
  key: string
  label?: string
  rules?: FormRule[]
}

/** 表单容器片段参数 */
export interface UseFormContainerOptions {
  /** 字段元数据清单（规则汇总与校验调度的依据） */
  fields?: MaybeRefOrGetter<FormFieldMeta[]>
  labelPosition?: MaybeRefOrGetter<'top' | 'left' | 'right'>
  labelWidth?: MaybeRefOrGetter<string | number>
  columns?: MaybeRefOrGetter<number>
  readonly?: MaybeRefOrGetter<boolean>
  disabled?: MaybeRefOrGetter<boolean>
  /** 值读取器（默认从传入 model 里取） */
  model?: MaybeRefOrGetter<Record<string, unknown>>
  onValidateFail?: (errors: Record<string, string>) => void
}

/** 表单容器片段返回值 */
export interface UseFormContainerReturn {
  readonly labelPosition: string
  readonly labelWidth: string
  readonly columns: number
  readonly readonly: boolean
  readonly disabled: boolean
  /** 规则汇总（字段 → 规则），供渲染器分发 */
  readonly ruleSummary: Record<string, FormRule[]>
  readonly errors: Record<string, string>
  readonly hasError: boolean
  /** 校验（返回是否通过；不通过时回调 `onValidateFail`） */
  validate: () => boolean
  /** 单字段校验 */
  validateField: (key: string) => string | undefined
  /** 重置错误与（可选）值变更标记 */
  reset: () => void
  /** 错误定位：返回首个错误字段 key（供滚动 / 聚焦） */
  locateError: () => string | undefined
  /** 容器属性（根元素透传） */
  readonly containerAttrs: Record<string, string>
}

/** 单规则校验：返回错误文案或 `undefined` */
export function runRule(rule: FormRule, value: unknown): string | undefined {
  const empty = value === undefined || value === null || value === ''
  if (rule.required && empty) {
    return rule.message ?? '该字段必填'
  }
  if (empty) {
    return undefined
  }
  if (typeof rule.validator === 'function') {
    const result = rule.validator(value)
    if (result === true || result === undefined) {
      return undefined
    }
    return typeof result === 'string' ? result : (rule.message ?? '校验未通过')
  }
  const text = String(value)
  if (rule.min !== undefined && text.length < rule.min) {
    return rule.message ?? `长度不小于 ${rule.min}`
  }
  if (rule.max !== undefined && text.length > rule.max) {
    return rule.message ?? `长度不大于 ${rule.max}`
  }
  if (rule.pattern && !rule.pattern.test(text)) {
    return rule.message ?? '格式不正确'
  }
  return undefined
}

/**
 * 获取表单容器能力。
 *
 * 用法：`const form = useFormContainer({ fields, model })`；`validate()` 前把 `ruleSummary` 分发给渲染器。
 */
export function useFormContainer(options: UseFormContainerOptions = {}): UseFormContainerReturn {
  declareFragment('form-container')

  const errors = ref<Record<string, string>>({})

  const fields = computed(() => toValue(options.fields) ?? [])
  const labelPosition = computed(() => String(toValue(options.labelPosition) ?? 'top'))
  const labelWidth = computed(() => {
    const width = toValue(options.labelWidth)
    return typeof width === 'number' ? `${width}px` : String(width ?? '')
  })
  const columns = computed(() => Math.max(1, Number(toValue(options.columns) ?? 1)))
  const readonly = computed(() => Boolean(toValue(options.readonly)))
  const disabled = computed(() => Boolean(toValue(options.disabled)))

  const ruleSummary = computed<Record<string, FormRule[]>>(() => {
    const summary: Record<string, FormRule[]> = {}
    for (const field of fields.value) {
      summary[field.key] = field.rules ?? []
    }
    return summary
  })

  const validateField = (key: string): string | undefined => {
    const rules = ruleSummary.value[key] ?? []
    const model = toValue(options.model) ?? {}
    for (const rule of rules) {
      const message = runRule(rule, model[key])
      if (message) {
        errors.value = { ...errors.value, [key]: message }
        return message
      }
    }
    const next = { ...errors.value }
    delete next[key]
    errors.value = next
    return undefined
  }

  const validate = (): boolean => {
    const next: Record<string, string> = {}
    for (const field of fields.value) {
      for (const rule of field.rules ?? []) {
        const message = runRule(rule, (toValue(options.model) ?? {})[field.key])
        if (message) {
          next[field.key] = message
          break
        }
      }
    }
    errors.value = next
    const passed = Object.keys(next).length === 0
    if (!passed) {
      options.onValidateFail?.(next)
    }
    return passed
  }

  const reset = (): void => {
    errors.value = {}
  }

  const containerAttrs = computed<Record<string, string>>(() => ({
    'data-label-position': labelPosition.value,
    'data-columns': String(columns.value),
    'data-readonly': readonly.value ? 'true' : 'false',
  }))

  return {
    get labelPosition() {
      return labelPosition.value
    },
    get labelWidth() {
      return labelWidth.value
    },
    get columns() {
      return columns.value
    },
    get readonly() {
      return readonly.value
    },
    get disabled() {
      return disabled.value
    },
    get ruleSummary() {
      return ruleSummary.value
    },
    get errors() {
      return errors.value
    },
    get hasError() {
      return Object.keys(errors.value).length > 0
    },
    validate,
    validateField,
    reset,
    locateError: () => fields.value.find((field) => errors.value[field.key] !== undefined)?.key,
    get containerAttrs() {
      return containerAttrs.value
    },
  }
}
