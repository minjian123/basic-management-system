/** 注册表基座用例（Kiwi 706）：唯一性拒重 / 未命中 / 保序 / 只读快照（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { effectScope, nextTick } from 'vue'

import { BaseComponent, resetMechanismWarnings, type MechanismRegistry } from '@/base/BaseComponent'
import { resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import { BaseError } from '@/base/error'
import {
  BaseRegistry,
  BaseRegistryItem,
  REGISTRY_DUPLICATE_CODE,
  REGISTRY_MECHANISM_KEY,
  useRegistryBase,
} from '@/base/provider'

/** 探针组件根：验证机制装配点 */
class ProbeRoot extends BaseComponent {}

/** 探针注册项：字段渲染器式域扩展（key + describe + 域扩展字段） */
class ProbeItem extends BaseRegistryItem {
  readonly key: string
  readonly component: string

  constructor(key: string, component: string) {
    super()
    this.key = key
    this.component = component
  }

  describe(): string {
    return `${this.key} → ${this.component}`
  }
}

const logRecords: LogRecord[] = []

/** 告警记录 */
function warnings(): LogRecord[] {
  return logRecords.filter((record) => record.level === 'warn')
}

beforeEach(() => {
  resetFrontendBaseConfig()
  resetMechanismWarnings()
  logRecords.length = 0
  setFrontendSinks({ log: (record) => logRecords.push(record), error: () => {} })
})

describe('注册表基座（Kiwi 706）', () => {
  it('⑧ 同 key 重复登记：非严格模式告警并保留首个', () => {
    const registry = new BaseRegistry()
    const first = new ProbeItem('dict', 'DictSelect')
    const second = new ProbeItem('dict', 'OtherSelect')
    registry.register(first)
    registry.register(second)

    expect(registry.count).toBe(1)
    expect(registry.get('dict')).toBe(first)
    expect(warnings().some((record) => record.message.includes('已登记'))).toBe(true)
  })

  it('⑨ strict 下同 key 抛 BaseError（码 10002）', () => {
    const registry = new BaseRegistry({ strict: true })
    registry.register(new ProbeItem('dict', 'DictSelect'))
    let caught: unknown
    try {
      registry.register(new ProbeItem('dict', 'OtherSelect'))
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(BaseError)
    expect((caught as BaseError).code).toBe(REGISTRY_DUPLICATE_CODE)
    expect(registry.count).toBe(1)
  })

  it('⑩ get 未命中返回 undefined（不抛错）与 has 判定', () => {
    const registry = new BaseRegistry()
    expect(registry.get('missing')).toBeUndefined()
    expect(registry.has('missing')).toBe(false)

    registry.register(new ProbeItem('icon', 'IconDisplay'))
    expect(registry.has('icon')).toBe(true)
    expect(registry.get('icon')?.describe()).toBe('icon → IconDisplay')
  })

  it('⑪ keys / values / list 保序与 count', () => {
    const registry = new BaseRegistry()
    registry.register(new ProbeItem('dict', 'A'))
    registry.register(new ProbeItem('user', 'B'))
    registry.register(new ProbeItem('org', 'C'))

    expect(registry.keys()).toEqual(['dict', 'user', 'org'])
    expect(registry.values().map((item) => item.key)).toEqual(['dict', 'user', 'org'])
    expect(registry.list()).toHaveLength(3)
    expect(registry.count).toBe(3)
  })

  it('⑫ snapshot 为冻结副本，改写不生效', () => {
    const registry = new BaseRegistry()
    registry.register(new ProbeItem('dict', 'A'))
    const snapshot = registry.snapshot()

    expect(Object.isFrozen(snapshot)).toBe(true)
    expect(() => {
      ;(snapshot as ProbeItem[]).push(new ProbeItem('new', 'X'))
    }).toThrow()
    expect(snapshot).toHaveLength(1)
    expect(registry.count).toBe(1)
  })

  it('⑬ unregister 命中 / 未命中', () => {
    const registry = new BaseRegistry()
    registry.register(new ProbeItem('dict', 'A'))
    expect(registry.unregister('dict')).toBe(true)
    expect(registry.unregister('dict')).toBe(false)
    expect(registry.count).toBe(0)

    registry.register(new ProbeItem('dict', 'A'))
    registry.clear()
    expect(registry.count).toBe(0)
  })

  it('⑭ useRegistryBase 作用域释放自动注销；装配点与释放联动', async () => {
    const scope = effectScope()
    const registry = scope.run(() => useRegistryBase())
    expect(registry).toBeDefined()
    registry?.register(new ProbeItem('dict', 'A'))
    registry?.register(new ProbeItem('user', 'B'))
    expect(registry?.count).toBe(2)

    scope.stop()
    await nextTick()
    expect(registry?.count).toBe(0)

    // 装配点：owner 挂接 + 组件根释放联动（清空登记项）
    resetMechanismWarnings()
    logRecords.length = 0
    const root = new ProbeRoot()
    const attached = new BaseRegistry({ owner: root })
    const mechRegistry: MechanismRegistry = root.mechanisms
    attached.register(new ProbeItem('dict', 'A'))
    expect(mechRegistry.get(REGISTRY_MECHANISM_KEY)).toBe(attached)
    expect(warnings()).toHaveLength(0)

    root.dispose()
    expect(attached.count).toBe(0)
    expect(mechRegistry.size).toBe(0)
  })

  it('⑮ 注册项契约：BaseRegistryItem 子类补充域字段', () => {
    const registry = new BaseRegistry<ProbeItem>()
    registry.register(new ProbeItem('card', 'MetricCard'))
    const item = registry.get('card')
    expect(item).toBeInstanceOf(BaseRegistryItem)
    expect(item?.component).toBe('MetricCard')
    expect(item?.describe()).toBe('card → MetricCard')
  })
})
