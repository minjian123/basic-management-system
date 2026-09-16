/**
 * 受控值能力（核心试点）：值语义——受控读写、三态（空 / 有值）、统一写入门禁、变更订阅。
 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable, type MutableObservable } from '../base/observable'

export interface ValueOptions<T = unknown> extends Omit<CapabilityOptions, 'key'> {
  key?: string
  initial?: T
  /** 空值判定（缺省 undefined / null / ''） */
  isEmpty?: (value: T) => boolean
  disabled?: boolean
  readonly?: boolean
}

export class BaseValue<T = unknown> extends BaseCapability {
  readonly state: MutableObservable<T>
  readonly disabled: boolean
  readonly readonly: boolean

  private readonly isEmptyCheck: (value: T) => boolean

  constructor(options: ValueOptions<T>) {
    super({ ...options, key: options.key ?? 'value' })
    this.state = observable(options.initial as T)
    this.disabled = options.disabled ?? false
    this.readonly = options.readonly ?? false
    this.isEmptyCheck =
      options.isEmpty ?? ((value: T) => value === undefined || value === null || (value as unknown) === '')
  }

  getValue(): T {
    return this.state.get()
  }

  /** 统一写入口：禁用 / 只读拒绝写入（唯一出口，防旁路） */
  setValue(value: T): void {
    if (this.disabled || this.readonly) {
      return
    }
    this.state.set(value)
  }

  /** 三态：空（`isEmpty`）/ 有值 /（未设置以 `undefined` 表达） */
  get isEmpty(): boolean {
    return this.isEmptyCheck(this.state.get())
  }

  get hasValue(): boolean {
    return !this.isEmpty
  }

  /** 变更订阅（返回取消函数） */
  onChange(listener: (value: T) => void): () => void {
    return this.state.subscribe(listener)
  }

  reset(): void {
    this.state.set(undefined as T)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), disabled: this.disabled, readonly: this.readonly }
  }
}
