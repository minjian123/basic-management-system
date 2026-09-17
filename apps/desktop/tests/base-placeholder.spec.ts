/** 占位基类用例（Kiwi 701）：三类原因 / 三类降级 / 不请求 / stub 抛错（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'

import { BaseComponent, resetMechanismWarnings } from '@/base/BaseComponent'
import { configureFrontendBase, resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import { BaseError, NOT_IMPLEMENTED_CODE } from '@/base/error'
import { BasePlaceholder, PLACEHOLDER_MECHANISM_KEY, usePlaceholderBase } from '@/base/placeholder'

/** 探针组件根：验证机制装配点 */
class ProbeRoot extends BaseComponent {}

const logRecords: LogRecord[] = []

/** 警告记录（断言未挂接告警） */
function warnings(): LogRecord[] {
  return logRecords.filter((record) => record.level === 'warn')
}

beforeEach(() => {
  resetFrontendBaseConfig()
  resetMechanismWarnings()
  logRecords.length = 0
  setFrontendSinks({
    log: (record) => logRecords.push(record),
    error: () => {},
  })
})

describe('占位基类（Kiwi 701）', () => {
  it('⑩ describe 含 reason 与 label', () => {
    const placeholder = new BasePlaceholder({ reason: 'pending', label: '选项源未接入' })
    expect(placeholder.reason).toBe('pending')
    expect(placeholder.label).toBe('选项源未接入')
    expect(placeholder.describe()).toBe('pending：选项源未接入')

    expect(new BasePlaceholder().describe()).toBe('pending')
    expect(new BasePlaceholder({ reason: 'null' }).reason).toBe('null')
    expect(new BasePlaceholder({ reason: 'stub' }).reason).toBe('stub')
  })

  it('⑪ mark 加 data-placeholder、placeholderAttrs 输出正确', () => {
    const placeholder = new BasePlaceholder({ reason: 'null', label: '空实现' })
    const el = document.createElement('div')
    placeholder.mark(el)
    expect(el.getAttribute('data-placeholder')).toBe('null')

    expect(placeholder.placeholderAttrs()).toEqual({
      'data-placeholder': 'null',
      'data-placeholder-label': '空实现',
    })

    // 无 label 时不输出 label 属性；传 null 不抛错
    expect(new BasePlaceholder({ reason: 'pending' }).placeholderAttrs()).toEqual({
      'data-placeholder': 'pending',
    })
    expect(() => placeholder.mark(null)).not.toThrow()
    const unknownElement = document.createElement('div')
    placeholder.mark(unknownElement)
    expect(unknownElement.getAttribute('data-placeholder')).toBe('null')
  })

  it('⑫ 三类降级语义（disabled ⇒ interactive=false）', () => {
    const placeholder = new BasePlaceholder({ degrade: 'empty' })
    expect(placeholder.degrade).toBe('empty')
    expect(placeholder.interactive).toBe(true)

    placeholder.setDegrade('disabled')
    expect(placeholder.degrade).toBe('disabled')
    expect(placeholder.interactive).toBe(false)

    placeholder.setDegrade('hidden')
    expect(placeholder.degrade).toBe('hidden')
    expect(placeholder.interactive).toBe(true)
  })

  it('⑬ 占位态不发起请求（allowRequest 恒 false）', () => {
    expect(new BasePlaceholder().allowRequest).toBe(false)
    expect(new BasePlaceholder({ reason: 'null' }).allowRequest).toBe(false)
    expect(new BasePlaceholder({ reason: 'stub' }).allowRequest).toBe(false)
  })

  it('⑭ stub 抛 BaseError（未实现码），其余原因不抛', () => {
    const stub = new BasePlaceholder({ reason: 'stub', label: '待实现' })
    let caught: unknown
    try {
      stub.assertImplemented('option-source')
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(BaseError)
    expect((caught as BaseError).code).toBe(NOT_IMPLEMENTED_CODE)
    expect((caught as BaseError).message).toContain('option-source')

    expect(() => new BasePlaceholder({ reason: 'pending' }).assertImplemented('x')).not.toThrow()
    expect(() => new BasePlaceholder({ reason: 'null' }).assertImplemented('x')).not.toThrow()
  })

  it('补：生产态静默与 owner 装配', () => {
    resetFrontendBaseConfig()
    configureFrontendBase({ env: 'prod' })
    resetMechanismWarnings()
    logRecords.length = 0

    const inProd = new BasePlaceholder({ reason: 'pending', label: '生产态' })
    expect(inProd.placeholderAttrs()).toEqual({})
    const el = document.createElement('div')
    inProd.mark(el)
    expect(el.hasAttribute('data-placeholder')).toBe(false)
    expect(logRecords).toHaveLength(0)

    // silentInProd=false 时生产态仍标记
    expect(new BasePlaceholder({ silentInProd: false }).placeholderAttrs()['data-placeholder']).toBe('pending')

    // owner 装配：进入组件根装配点，且不产生未挂接告警
    resetFrontendBaseConfig()
    resetMechanismWarnings()
    logRecords.length = 0
    const root = new ProbeRoot()
    const attached = new BasePlaceholder({ owner: root, label: '已挂接' })
    attached.describe()
    expect(root.mechanisms.get(PLACEHOLDER_MECHANISM_KEY)).toBe(attached)
    expect(warnings()).toHaveLength(0)

    root.dispose()
    expect(root.mechanisms.size).toBe(0)
  })

  it('补：组合式等价与 mechanism 装配入口', () => {
    const root = new ProbeRoot()
    const placeholder = usePlaceholderBase({ reason: 'stub', label: '组合式', owner: root })
    expect(placeholder.reason).toBe('stub')
    expect(placeholder.label).toBe('组合式')
    expect(placeholder.degrade).toBe('empty')
    expect(placeholder.silentInProd).toBe(true)
    expect(placeholder.describe()).toBe('stub：组合式')
    expect(placeholder.allowRequest).toBe(false)
    expect(placeholder.interactive).toBe(true)
    expect(placeholder.placeholderAttrs()).toEqual({
      'data-placeholder': 'stub',
      'data-placeholder-label': '组合式',
    })

    const el = document.createElement('div')
    placeholder.mark(el)
    expect(el.getAttribute('data-placeholder')).toBe('stub')

    placeholder.setDegrade('disabled')
    expect(placeholder.degrade).toBe('disabled')
    expect(placeholder.interactive).toBe(false)

    expect(() => placeholder.assertImplemented('composable')).toThrow(BaseError)

    expect(root.mechanisms.get(PLACEHOLDER_MECHANISM_KEY)).toBe(placeholder.mechanism)
    root.mechanisms.detach(placeholder.mechanism)
    expect(root.mechanisms.size).toBe(0)
    placeholder.dispose()
  })
})
