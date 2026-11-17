// kiwi_id: 2524
/** 字典带版本重取（09_01）：展开 / 聚焦触发、版本一致零传输、版本变化替换条目、去重与占位零请求。 */

import { describe, expect, it } from 'vitest'

import { BaseDictStore, bindDictStoreSource } from '@bms/core'
import { createDictSourceStub } from '@bms/core/testing'

/** 具体字典缓存。 */
class DictStoreState extends BaseDictStore {}

/**
 * 造已就绪缓存（注入桩数据源）。
 *
 * @returns 缓存与桩。
 */
function makeStore(): { store: DictStoreState; stub: ReturnType<typeof createDictSourceStub> } {
  const store = new DictStoreState()
  const stub = createDictSourceStub()
  store.setReady(true)
  bindDictStoreSource(store, stub.source)
  return { store, stub }
}

describe('BaseDictStore · 带版本重取（09_01）', () => {
  it('版本一致：仍发一次带版本请求，后端回 items=null 时保留现有条目', async () => {
    const { store, stub } = makeStore()
    await store.ensureType('user_status')
    const before = store.itemsOf('user_status')
    expect(before.length).toBeGreaterThan(0)

    const callsBefore = stub.calls.length
    await store.revalidateType('user_status')

    expect(stub.calls.length).toBe(callsBefore + 1)
    const lastQuery = stub.queries[stub.queries.length - 1] as Record<string, unknown>
    expect(lastQuery.version).toBe(stub.version)
    expect(store.itemsOf('user_status')).toEqual(before)
  })

  it('版本变化：按新版本替换条目并推进全局版本号', async () => {
    const { store, stub } = makeStore()
    await store.ensureType('user_status')
    const firstVersion = store.entryOf('user_status')?.version ?? 0

    stub.version += 1
    await store.revalidateType('user_status')

    expect(store.entryOf('user_status')?.version).toBe(firstVersion + 1)
    expect(store.dictVersion).toBe(stub.version)
  })

  it('多类型重取去重；未就绪 / 未注入零请求', async () => {
    const { store, stub } = makeStore()
    await store.ensureType('user_status')
    const callsBefore = stub.calls.length
    await store.revalidateTypes(['user_status', 'user_status'])
    expect(stub.calls.length).toBe(callsBefore + 1)

    const idle = new DictStoreState()
    await idle.revalidateType('user_status')
    await idle.revalidateTypes(['user_status'])
    expect(idle.requestCount).toBe(0)
  })
})
