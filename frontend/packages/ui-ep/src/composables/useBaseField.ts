/** 字段件投影：把核心字段能力基类 `BaseField` 投影为组合式（字段标识 / 校验触发）。 */

import { BaseField, type FieldTrigger } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体字段件（可实例化）。 */
class FieldState<T> extends BaseField<T> {}

/** 选项。 */
export interface UseBaseFieldOptions {
  /** 字段标识。 */
  fieldName?: string
  /** 校验触发时机。 */
  trigger?: FieldTrigger
  /** 初始值。 */
  value?: unknown
}

/** `useBaseField` 返回面。 */
export interface UseBaseFieldResult<T = unknown> {
  /** 字段基类实例。 */
  field: BaseField<T>
  /** 当前值（响应式）。 */
  value: Ref<T | undefined>
  /** 是否空态（响应式）。 */
  isEmpty: Ref<boolean>
  /** 字段标识（响应式）。 */
  fieldName: Ref<string>
  /** 校验触发时机（响应式）。 */
  trigger: Ref<FieldTrigger>
  /** 设置字段标识。 */
  setFieldName: (name: string) => void
  /** 设置校验触发时机。 */
  setTrigger: (trigger: FieldTrigger) => void
  /** 设置值。 */
  setValue: (value: T | undefined) => void
}

/**
 * 使用字段件投影。
 *
 * @param options 选项。
 * @returns 字段基类实例与响应式面。
 */
export function useBaseField<T = unknown>(options: UseBaseFieldOptions = {}): UseBaseFieldResult<T> {
  const field = new FieldState<T>()
  if (options.fieldName !== undefined) {
    field.fieldName = options.fieldName
  }
  if (options.trigger !== undefined) {
    field.trigger = options.trigger
  }
  if (options.value !== undefined) {
    field.setValue(options.value as T)
  }

  const value = ref<T | undefined>(field.value) as Ref<T | undefined>
  const isEmpty = ref(field.isEmpty)
  const fieldName = ref(field.fieldName)
  const trigger = ref<FieldTrigger>(field.trigger)
  field.onChange((next) => {
    value.value = next
  })
  const off = field.onLifecycle((event) => {
    if (event === 'update') {
      value.value = field.value
      isEmpty.value = field.isEmpty
      fieldName.value = field.fieldName
      trigger.value = field.trigger
    }
  })
  onScopeDispose(off)

  return {
    field,
    value,
    isEmpty,
    fieldName,
    trigger,
    setFieldName: (name) => {
      field.fieldName = name
      field.notifyLifecycle('update')
    },
    setTrigger: (next) => {
      field.trigger = next
      field.notifyLifecycle('update')
    },
    setValue: (next) => field.setValue(next),
  }
}
