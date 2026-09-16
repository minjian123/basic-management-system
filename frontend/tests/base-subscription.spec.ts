/** 订阅基类用例（Kiwi 704）：订阅 / 取消 / 占位总线 / 来源切换 / 事件名校验（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { effectScope, nextTick } from 'vue'

import { BaseComponent, resetMechanismWarnings } from '@/base/BaseComponent'
import { resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import {
  BaseSubscription,
  DEFAULT_TOPIC_PATTERN,
  SUBSCRIPTION_MECHANISM_KEY,
  useSubscriptionBase,
} from '@/base/subscription'

/** 探针组件根：验证机制装配点 */
class ProbeRoot extends BaseComponent {}

const logRecords: LogRecord[] = []

/** 警告记录（断言来源回落 / 事件名 / 未挂接告警） */
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

describe('订阅基类（Kiwi 704）', () => {
  it('㉗ subscribe / once / unsubscribe / has / topics 语义与多 handler 分发', () => {
    const subscription = new BaseSubscription({ ns: 'probe' })
    const received: string[] = []
    const offFirst = subscription.subscribe('notification.new', (payload) => received.push(`first:${String(payload)}`))
    subscription.subscribe('notification.new', (payload) => received.push(`second:${String(payload)}`))
    subscription.subscribe('approval.todo', () => received.push('approval'))

    expect(subscription.has('notification.new')).toBe(true)
    expect(subscription.topics).toEqual(['notification.new', 'approval.todo'])

    subscription.publish('notification.new', 1)
    expect(received).toEqual(['first:1', 'second:1'])

    // 单次订阅：收到即取消
    subscription.once('session.revoked', () => received.push('once'))
    subscription.publish('session.revoked')
    subscription.publish('session.revoked')
    expect(received.filter((item) => item === 'once')).toHaveLength(1)

    offFirst()
    subscription.publish('notification.new', 2)
    expect(received).toContain('second:2')

    subscription.unsubscribe()
    expect(subscription.topics).toEqual([])
    expect(subscription.has('notification.new')).toBe(false)

    subscription.unsubscribe('approval.todo')
    subscription.dispose()
  })

  it('㉘ publish 仅本地分发（占位总线，不连 socket）', () => {
    const subscription = new BaseSubscription({ ns: 'probe' })
    expect(subscription.source).toBe('placeholder')
    subscription.publish('notification.new', 'no-subscriber')

    const received: unknown[] = []
    subscription.subscribe('notification.new', (payload) => received.push(payload))
    subscription.publish('notification.new', { id: 1 })
    expect(received).toEqual([{ id: 1 }])
    subscription.dispose()
  })

  it('㉙ 取消函数幂等，dispose 取消全部订阅', () => {
    const subscription = new BaseSubscription({ ns: 'probe' })
    const received: string[] = []
    const off = subscription.subscribe('approval.todo', () => received.push('hit'))
    off()
    off()
    subscription.publish('approval.todo')
    expect(received).toHaveLength(0)
    expect(subscription.has('approval.todo')).toBe(false)

    subscription.subscribe('approval.todo', () => received.push('again'))
    subscription.subscribe('notification.new', () => received.push('other'))
    subscription.dispose()
    expect(subscription.topics).toEqual([])
    subscription.publish('approval.todo')
    subscription.publish('notification.new')
    expect(received).toHaveLength(0)
  })

  it('㉚ setSource：placeholder / local 生效，realtime 未接入告警并回落', () => {
    const subscription = new BaseSubscription({ ns: 'probe' })
    subscription.setSource('local')
    expect(subscription.source).toBe('local')

    subscription.setSource('realtime')
    expect(subscription.source).toBe('placeholder')
    expect(warnings().some((record) => record.message.includes('实时推送未接入'))).toBe(true)

    // 构造时指定 realtime 同样回落
    expect(new BaseSubscription({ ns: 'probe', source: 'realtime' }).source).toBe('placeholder')
    subscription.dispose()
  })

  it('㉛ 非法 topic 告警但不阻断；挂接后不产生未挂接告警', () => {
    const subscription = new BaseSubscription({ ns: 'probe' })
    subscription.subscribe('NotificationNew', () => {})
    expect(subscription.has('NotificationNew')).toBe(true)
    expect(warnings().some((record) => record.message.includes('不符合点分小写口径'))).toBe(true)
    expect(DEFAULT_TOPIC_PATTERN.test('notification.new')).toBe(true)
    expect(DEFAULT_TOPIC_PATTERN.test('approval.todo')).toBe(true)
    expect(DEFAULT_TOPIC_PATTERN.test('NotificationNew')).toBe(false)
    subscription.dispose()

    // owner 装配：进入组件根装配点，订阅句柄随组件根释放取消
    resetMechanismWarnings()
    logRecords.length = 0
    const root = new ProbeRoot()
    const attached = new BaseSubscription({ ns: 'probe', owner: root })
    const received: string[] = []
    attached.subscribe('approval.todo', () => received.push('hit'))
    expect(root.mechanisms.get(SUBSCRIPTION_MECHANISM_KEY)).toBe(attached)
    attached.publish('approval.todo')
    expect(received).toHaveLength(1)

    root.dispose()
    expect(root.mechanisms.size).toBe(0)
    attached.publish('approval.todo')
    expect(received).toHaveLength(1)
  })

  it('补：组合式随作用域释放，取消全部订阅', async () => {
    const scope = effectScope()
    const received: string[] = []
    const subscription = scope.run(() => useSubscriptionBase({ ns: 'probe' }))
    subscription?.subscribe('notification.new', () => received.push('hit'))
    expect(subscription?.topics).toEqual(['notification.new'])

    scope.stop()
    await nextTick()
    subscription?.publish('notification.new')
    expect(received).toHaveLength(0)
  })
})
