/**
 * 契约测试（受控值能力 · 试点）：所有值实现（Null / 真实 / 引擎绑定）跑同一套断言。
 */

import { describe, expect, it, vi } from 'vitest'

import { BaseValue } from '../../src'

describe('受控值能力契约（BaseValue）', () => {
  it('受控读写与三态：set / get / isEmpty / hasValue', () => {
    const value = new BaseValue<string>({ key: 'value', initial: '' })
    expect(value.getValue()).toBe('')
    expect(value.isEmpty).toBe(true)

    value.setValue('abc')
    expect(value.getValue()).toBe('abc')
    expect(value.hasValue).toBe(true)

    value.setValue('')
    expect(value.isEmpty).toBe(true)

    const unwritten = new BaseValue<number>({ key: 'value' })
    expect(unwritten.isEmpty).toBe(true) // undefined
  })

  it('统一写入口门禁：disabled / readonly 拒绝写入', () => {
    const disabled = new BaseValue<string>({ key: 'value', initial: 'a', disabled: true })
    disabled.setValue('b')
    expect(disabled.getValue()).toBe('a')

    const readonly = new BaseValue<string>({ key: 'value', initial: 'a', readonly: true })
    readonly.setValue('b')
    expect(readonly.getValue()).toBe('a')
  })

  it('变更订阅：onChange 触发与取消；同值不触发', () => {
    const value = new BaseValue<number>({ key: 'value', initial: 1 })
    const listener = vi.fn()
    const unsubscribe = value.onChange(listener)

    value.setValue(2)
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(2)

    value.setValue(2) // 同值不触发
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    value.setValue(3)
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('reset：回到未设置（undefined）', () => {
    const value = new BaseValue<string>({ key: 'value', initial: 'x' })
    value.reset()
    expect(value.getValue()).toBeUndefined()
  })
})
