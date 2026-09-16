/** 片段机制用例（Kiwi 705）：声明 / 依赖校验 / 循环检测 / 开发态告警（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'

import { BaseComponent, resetMechanismWarnings, type MechanismRegistry } from '@/base/BaseComponent'
import {
  CAPABILITY_MECHANISM_KEY,
  CAPABILITY_VIOLATION_CODE,
  BaseCapability,
  knownFragmentsView,
  registerKnownFragments,
  resetKnownFragments,
  useCapabilityBase,
} from '@/base/capability'
import { configureFrontendBase, resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import { BaseError } from '@/base/error'

/** 探针组件根：验证机制装配点 */
class ProbeRoot extends BaseComponent {}

const logRecords: LogRecord[] = []

/** 告警记录 */
function warnings(): LogRecord[] {
  return logRecords.filter((record) => record.level === 'warn')
}

beforeEach(() => {
  resetFrontendBaseConfig()
  resetMechanismWarnings()
  resetKnownFragments()
  logRecords.length = 0
  setFrontendSinks({ log: (record) => logRecords.push(record), error: () => {} })
})

describe('片段机制（Kiwi 705）', () => {
  it('① 声明返回描述符（key / depends / describe）', () => {
    registerKnownFragments({
      value: [],
      'field-shell': [],
      'field-perm': [],
      field: ['value', 'field-shell', 'field-perm'],
    })

    const capability = useCapabilityBase({ key: 'field' })
    expect(capability.key).toBe('field')
    expect(capability.depends).toEqual(['value', 'field-shell', 'field-perm'])
    expect(capability.describe()).toBe('field(depends: value,field-shell,field-perm)')
    expect(capability.enabled).toBe(true)
    expect(knownFragmentsView().field).toEqual(['value', 'field-shell', 'field-perm'])
    capability.dispose()

    // 显式 depends 优先于已知表
    const explicit = useCapabilityBase({ key: 'custom-thing', depends: [] })
    expect(explicit.depends).toEqual([])
    expect(explicit.describe()).toBe('custom-thing')
    explicit.dispose()
  })

  it('② 依赖未登记：开发态告警 / strict 抛错', () => {
    registerKnownFragments({ value: [] })
    const capability = useCapabilityBase({ key: 'field', depends: ['value', 'missing-fragment'] })
    expect(capability.assertDeps()).toBe(false)
    expect(warnings().some((record) => record.message.includes('未登记'))).toBe(true)
    capability.dispose()

    const strict = useCapabilityBase({ key: 'field', depends: ['missing-fragment'], strict: true })
    let caught: unknown
    try {
      strict.assertDeps()
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(BaseError)
    expect((caught as BaseError).code).toBe(CAPABILITY_VIOLATION_CODE)
    strict.dispose()
  })

  it('③ 循环依赖检测（A → B → A）', () => {
    registerKnownFragments({ alpha: ['beta'], beta: ['alpha'] })
    const capability = useCapabilityBase({ key: 'alpha' })
    expect(capability.assertDeps()).toBe(false)
    expect(warnings().some((record) => record.message.includes('循环'))).toBe(true)
    capability.dispose()
  })

  it('④ 非法 key（空 / 非 kebab-case）告警', () => {
    registerKnownFragments({ BadKey: [] })
    const capability = useCapabilityBase({ key: 'BadKey' })
    expect(capability.assertDeps()).toBe(false)
    expect(warnings().some((record) => record.message.includes('kebab-case'))).toBe(true)
    capability.dispose()
  })

  it('⑤ enabled=false 跳过校验与登记', () => {
    registerKnownFragments({ value: [] })
    const capability = useCapabilityBase({ key: 'field', depends: ['not-registered'], enabled: false })
    expect(capability.enabled).toBe(false)
    expect(capability.assertDeps()).toBe(true)
    expect(warnings()).toHaveLength(0)
    capability.register()
    expect(knownFragmentsView().field).toBeUndefined()
    capability.dispose()
  })

  it('⑥ onWarn 覆盖默认告警；register 写入已知表', () => {
    registerKnownFragments({ value: [] })
    const messages: string[] = []
    const capability = useCapabilityBase({
      key: 'field',
      depends: ['value'],
      onWarn: (message) => messages.push(message),
    })
    expect(messages).toHaveLength(0)
    capability.register()
    expect(knownFragmentsView().field).toEqual(['value'])

    const violating = useCapabilityBase({
      key: 'field-2',
      depends: ['nope'],
      onWarn: (message) => messages.push(message),
    })
    violating.assertDeps()
    expect(messages.some((message) => message.includes('nope'))).toBe(true)
    // onWarn 接管后，违规内容不走默认根系告警
    expect(warnings().some((record) => record.message.includes('nope'))).toBe(false)
    violating.dispose()
    capability.dispose()
  })

  it('⑦ 生产态零告警；装配点挂接与释放联动', () => {
    registerKnownFragments({ value: [] })
    resetFrontendBaseConfig()
    configureFrontendBase({ env: 'prod' })
    logRecords.length = 0
    const inProd = useCapabilityBase({ key: 'field', depends: ['missing'] })
    expect(inProd.assertDeps()).toBe(true)
    expect(logRecords).toHaveLength(0)
    inProd.dispose()

    // 装配点：owner 挂接 + 组件根释放联动
    resetFrontendBaseConfig()
    resetMechanismWarnings()
    logRecords.length = 0
    const root = new ProbeRoot()
    const attached = new BaseCapability({ key: 'field', depends: ['value'], owner: root })
    const registry: MechanismRegistry = root.mechanisms
    expect(registry.get(CAPABILITY_MECHANISM_KEY)).toBe(attached)
    expect(warnings()).toHaveLength(0)

    root.dispose()
    expect(registry.size).toBe(0)

    // 未挂接时开发态一次告警
    resetMechanismWarnings()
    logRecords.length = 0
    const orphan = useCapabilityBase({ key: 'field', depends: ['value'] })
    orphan.register()
    expect(warnings().some((record) => record.message.includes('未被组件根挂接'))).toBe(true)
    orphan.dispose()
  })
})
