/**
 * 输入域领域工厂（框架无关核心）：基础控件类与字段类共用的输入域口径。
 *
 * 组合「字段编排 `field`」与「输入形态 `input-control`」两能力，单点提供：
 * 受控读写、归一（trim / 空值）、清空、只读与禁用判定、composition 桥接。
 * 门禁不重复实现——禁用 / 只读一律由能力统一写入口拒绝（`BaseField.setValue` / `BaseValue.setValue`）。
 */

import type { BaseField, FieldOptions } from '../capabilities/field'
import type { BaseInputControl, InputControlOptions } from '../capabilities/input-control'
import { createCapability } from '../capabilities/registry'

/** 输入域展示态：编辑 / 只读文本 / 禁用 */
export type InputMode = 'edit' | 'text' | 'disabled'

/** 只读呈现方式：纯文本回显 / 禁用态输入元素 */
export type ReadonlyMode = 'text' | 'disabled'

export interface InputContextOptions<T = unknown> {
  /** 字段能力实例（缺省经注册表创建——「不注册不可用」） */
  field?: BaseField<T>
  /** 输入形态能力实例（缺省经注册表创建） */
  control?: BaseInputControl
  /** 字段能力参数（`field` 缺省创建时生效） */
  fieldOptions?: FieldOptions<T>
  /** 输入形态能力参数（`control` 缺省创建时生效） */
  controlOptions?: Omit<InputControlOptions, 'key'>
  /** 归一时去首尾空格（默认 `true`；密码类传 `false`） */
  trim?: boolean
  /** 只读呈现方式（默认 `text`） */
  readonlyMode?: ReadonlyMode
  /** 空值归一目标（默认 `null`） */
  emptyValue?: unknown
  /** 归一钩子（如文本域换行统一、数值精度；缺省恒等） */
  normalize?: (value: T) => T
  /** 空值判定覆盖（缺省 `undefined` / `null` / `''` 视为空） */
  isEmpty?: (value: T) => boolean
}

export interface InputContext<T = unknown> {
  readonly field: BaseField<T>
  readonly control: BaseInputControl
  /** 受控值（读） */
  read(): T
  /** 受控值（写）：经能力统一写入口（禁用 / 只读被拒），触发校验 */
  write(value: T): void
  /** 归一出「提交值」（trim → 空值 → 自定义钩子），不写回 */
  normalizeValue(): T
  /** 提交：归一 + 写回 + 失焦（壳层失焦 / 提交前调用） */
  commit(): T
  /** 清空（`clearable` 为真时写空值） */
  clear(): void
  /** 展示态（禁用 > 只读 > 编辑） */
  mode(): InputMode
  /** 只读回显文本（空值返回 `''`；`0` / `false` 保留） */
  displayText(): string
  focus(): void
  blur(): void
  compositionStart(): void
  compositionEnd(): void
  dispose(): void
}

export function createInputContext<T = unknown>(options: InputContextOptions<T> = {}): InputContext<T> {
  const trim = options.trim ?? true
  const readonlyMode: ReadonlyMode = options.readonlyMode ?? 'text'
  const emptyValue = (options.emptyValue ?? null) as T
  const normalizeHook = options.normalize
  const blank =
    options.isEmpty ?? ((value: T) => value === undefined || value === null || (value as unknown) === '')

  const field = options.field ?? createCapability<BaseField<T>>('field', { ...(options.fieldOptions ?? {}) })
  const control =
    options.control ?? createCapability<BaseInputControl>('input-control', { ...(options.controlOptions ?? {}) })

  const read = (): T => field.getValue()

  const normalizeValue = (): T => {
    let next = read() as unknown
    if (trim && typeof next === 'string') {
      next = next.trim()
    }
    if (blank(next as T)) {
      next = emptyValue as unknown
    }
    return normalizeHook ? normalizeHook(next as T) : (next as T)
  }

  return {
    field,
    control,
    read,
    write: (value: T) => {
      field.setValue(value)
    },
    normalizeValue,
    commit: () => {
      const normalized = normalizeValue()
      field.setValue(normalized)
      control.onBlur()
      return normalized
    },
    clear: () => {
      if (!control.clearable) {
        return
      }
      field.setValue(emptyValue)
    },
    mode: () => {
      if (field.effectiveDisabled) {
        return 'disabled'
      }
      if (field.value.readonly) {
        return readonlyMode
      }
      return 'edit'
    },
    displayText: () => {
      const value = read() as unknown
      if (blank(value as T)) {
        return ''
      }
      return String(value)
    },
    focus: () => control.onFocus(),
    blur: () => control.onBlur(),
    compositionStart: () => control.onCompositionStart(),
    compositionEnd: () => control.onCompositionEnd(),
    dispose: () => {
      field.dispose()
      control.dispose()
    },
  }
}
