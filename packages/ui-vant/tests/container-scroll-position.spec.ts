/** 滚动位置存储与保持用例（Kiwi 743）：记录 / 恢复 / 键语义。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import {
  ScrollContainer,
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
} from '../src'

import { mountWithPlugins } from './helpers/mount'

type Wrapper = ReturnType<typeof mountWithPlugins>

function bodyOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-scroll-container-body').element as HTMLElement
}

function sizeBody(wrapper: Wrapper): HTMLElement {
  const body = bodyOf(wrapper)
  Object.defineProperty(body, 'scrollHeight', { value: 500, configurable: true })
  Object.defineProperty(body, 'clientHeight', { value: 100, configurable: true })
  return body
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('滚动位置存储与保持（Kiwi 743）', () => {
  it('内存适配器与存储：读写 / 取整 / 非法值', () => {
    const storage = createMemoryScrollStorage()
    expect(storage.getItem('k')).toBeNull()
    storage.setItem('k', '1')
    expect(storage.getItem('k')).toBe('1')
    storage.removeItem('k')
    expect(storage.getItem('k')).toBeNull()

    const store = createScrollPositionStore(storage)
    expect(store.get('a')).toBeUndefined()
    store.set('a', 12.4)
    expect(store.get('a')).toBe(12)
    store.set('b', -5)
    expect(store.get('b')).toBe(0)
    store.set('c', Number.NaN)
    expect(store.get('c')).toBeUndefined()
    store.remove('a')
    expect(store.get('a')).toBeUndefined()
  })

  it('sessionStorage 适配器：前缀 / 可写探测 / 不可用回落内存', () => {
    const storage = createSessionScrollStorage()
    storage.setItem('x', '42')
    expect(window.sessionStorage.getItem('bms:scroll:x')).toBe('42')
    expect(storage.getItem('x')).toBe('42')
    storage.removeItem('x')
    expect(window.sessionStorage.getItem('bms:scroll:x')).toBeNull()
    expect(window.sessionStorage.getItem('bms:scroll:__probe__')).toBeNull()

    vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    const fallback = createSessionScrollStorage()
    fallback.setItem('y', '7')
    // 回落内存：sessionStorage 未写入但可读回
    expect(fallback.getItem('y')).toBe('7')
  })

  it('keepPosition：卸载记录、重新挂载恢复（同 positionKey）', async () => {
    const key = 'spec-restore'
    const store = createScrollPositionStore()
    store.remove(key)

    const first = mountWithPlugins(ScrollContainer, {
      props: { keepPosition: true, positionKey: key },
    })
    const firstBody = sizeBody(first)
    firstBody.scrollTop = 120
    first.unmount()
    expect(store.get(key)).toBe(120)

    const second = mountWithPlugins(ScrollContainer, {
      props: { keepPosition: true, positionKey: key },
    })
    sizeBody(second)
    await nextTick()
    expect(bodyOf(second).scrollTop).toBe(120)
    second.unmount()
  })

  it('positionKey 变更：记录旧键、恢复新键', async () => {
    const store = createScrollPositionStore()
    store.remove('spec-a')
    store.remove('spec-b')

    // 变更前记录旧键
    const wrapper = mountWithPlugins(ScrollContainer, {
      props: { keepPosition: true, positionKey: 'spec-a' },
    })
    const body = sizeBody(wrapper)
    body.scrollTop = 80
    await wrapper.setProps({ positionKey: 'spec-b' })
    await nextTick()
    expect(store.get('spec-a')).toBe(80)
    wrapper.unmount()

    // 新键有值 → 挂载时恢复
    store.set('spec-b', 66)
    const second = mountWithPlugins(ScrollContainer, {
      props: { keepPosition: true, positionKey: 'spec-b' },
    })
    sizeBody(second)
    await nextTick()
    expect(bodyOf(second).scrollTop).toBe(66)
    second.unmount()
  })

  it('无 positionKey：按实例 uid 记账（不跨实例恢复）', async () => {
    const store = createScrollPositionStore()
    const first = mountWithPlugins(ScrollContainer, { props: { keepPosition: true } })
    const firstBody = sizeBody(first)
    firstBody.scrollTop = 50
    first.unmount()

    const second = mountWithPlugins(ScrollContainer, { props: { keepPosition: true } })
    sizeBody(second)
    await nextTick()
    expect(bodyOf(second).scrollTop).toBe(0)
    second.unmount()
    expect(store).toBeDefined()
  })
})
