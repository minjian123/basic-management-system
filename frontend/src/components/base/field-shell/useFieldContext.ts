/**
 * 字段上下文机制（字段壳 ↔ 控件的 `provide` / `inject` 通道，**非片段**）。
 *
 * 口径（《组件设计 · 输入域基类》）：字段壳下发 label / required / error / readonly / disabled，
 * 控件回传值变化与校验结果、注册 / 注销自身（供壳错误定位）。
 *
 * 登记口径：作为**上下文机制**——不声明片段 `key`、不占《前端基类清单》§5 片段表，
 * 落档见清单 §5 注记与组件设计输入域节点实现口径；输入域 `useInputBase` 消费本机制。
 */

import { inject, provide, type InjectionKey } from 'vue'

/** 控件注册信息（供壳定位焦点） */
export interface FieldContextControl {
  readonly fieldKey: string
  focus?: () => void
}

/** 字段上下文值（提供方按 getter / computed 保证响应性） */
export interface FieldContextValue {
  readonly fieldKey: string
  readonly label: string
  readonly required: boolean
  readonly readonly: boolean
  readonly disabled: boolean
  readonly visible: boolean
  readonly errorText: string
  /** 控件注册（挂载时调用） */
  registerControl?: (control: FieldContextControl) => void
  /** 控件注销（卸载时调用） */
  unregisterControl?: (fieldKey: string) => void
  /** 控件回传值变化 */
  emitValueChange?: (value: unknown) => void
  /** 控件回传校验结果 */
  emitValidate?: (passed: boolean, message?: string) => void
}

/** 字段上下文注入键 */
export const FIELD_CONTEXT_KEY: InjectionKey<FieldContextValue> = Symbol('bms-field-context')

/** 提供字段上下文（字段壳 / 字段类使用；同组件重复提供以最后一次为准） */
export function provideFieldContext(value: FieldContextValue): void {
  provide(FIELD_CONTEXT_KEY, value)
}

/** 取用字段上下文（控件使用；缺省返回 `undefined`，控件脱离字段壳可独立工作） */
export function useFieldContext(): FieldContextValue | undefined {
  return inject(FIELD_CONTEXT_KEY, undefined)
}
