/** 领域层用例：滚动位置存储 / 尺寸解析 / 虚拟区计算（自 ui-ep 迁入的共享逻辑）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  computeVirtualRange,
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
  resolveSize,
  type VirtualRangeInput,
} from '../src'

function range(input: Partial<VirtualRangeInput>): ReturnType<typeof computeVirtualRange> {
  return computeVirtualRange({
    itemCount: 0,
    itemHeight: 20,
    buffer: 0,
    scrollTop: 0,
    viewportHeight: 0,
    ...input,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('滚动位置存储（领域层）', () => {
  it('内存适配器与存储工厂', () => {
    const storage = createMemoryScrollStorage()
    const store = createScrollPositionStore(storage)
    store.set('a', 12.6)
    expect(store.get('a')).toBe(13)
    store.set('b', -5)
    expect(store.get('b')).toBe(0)
    store.set('c', Number.NaN)
    expect(store.get('c')).toBeUndefined()
    store.remove('a')
    expect(store.get('a')).toBeUndefined()
  })

  it('默认适配器单例与显式传入等价', () => {
    const store = createScrollPositionStore()
    store.set('default-singleton', 7)
    expect(defaultScrollStorage.getItem('default-singleton')).toBe('7')
    store.remove('default-singleton')
  })

  it('sessionStorage 适配器（前缀隔离 / 可写探测 / 不可用回落内存）', () => {
    const memory = new Map<string, string>()
    const fake = {
      getItem: (key: string) => (memory.has(key) ? (memory.get(key) as string) : null),
      setItem: (key: string, value: string) => {
        memory.set(key, value)
      },
      removeItem: (key: string) => {
        memory.delete(key)
      },
    }
    Object.defineProperty(globalThis, 'sessionStorage', { value: fake, configurable: true })
    try {
      const store = createScrollPositionStore(createSessionScrollStorage('spec:'))
      store.set('k', 5)
      expect(fake.getItem('spec:k')).toBe('5')
      expect(store.get('k')).toBe(5)
      store.remove('k')
      expect(fake.getItem('spec:k')).toBeNull()
      expect(fake.getItem('spec:__probe__')).toBeNull()
    } finally {
      delete (globalThis as { sessionStorage?: unknown }).sessionStorage
    }
  })

  it('sessionStorage 不可写时回落内存（读取不抛错）', () => {
    const broken = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
      removeItem: () => {
        throw new Error('denied')
      },
    }
    Object.defineProperty(globalThis, 'sessionStorage', { value: broken, configurable: true })
    try {
      const fallback = createSessionScrollStorage()
      fallback.setItem('y', '7')
      expect(fallback.getItem('y')).toBe('7')
    } finally {
      delete (globalThis as { sessionStorage?: unknown }).sessionStorage
    }
  })
})

describe('尺寸解析（领域层）', () => {
  it('数字按 px、字符串原样、undefined 原样', () => {
    expect(resolveSize(240)).toBe('240px')
    expect(resolveSize('50vh')).toBe('50vh')
    expect(resolveSize(undefined)).toBeUndefined()
  })
})

describe('虚拟区计算（领域层）', () => {
  it('定高：范围 / 偏移 / 总量 / 索引', () => {
    const result = range({ itemCount: 100, itemHeight: 20, buffer: 2, scrollTop: 200, viewportHeight: 100 })
    expect(result.startIndex).toBe(8)
    expect(result.endIndex).toBe(18)
    expect(result.offsetY).toBe(160)
    expect(result.totalHeight).toBe(2000)
    expect(result.offsetOf(50)).toBe(1000)
    expect(result.indexAt(999)).toBe(49)
  })

  it('动态高度：二分定位与估值回退', () => {
    const result = range({
      itemCount: 3,
      itemHeight: 10,
      heights: [30, undefined, 50],
      estimated: 25,
    })
    expect(result.totalHeight).toBe(105)
    expect(result.offsetOf(1)).toBe(30)
    expect(result.offsetOf(2)).toBe(55)
    expect(result.indexAt(56)).toBe(2)
  })

  it('空列表与边界夹取', () => {
    const empty = range({})
    expect(empty.totalHeight).toBe(0)
    expect(empty.indexAt(100)).toBe(0)
    expect(empty.startIndex).toBe(0)
    expect(empty.endIndex).toBe(0)
    expect(empty.offsetOf(9)).toBe(0)

    const clamped = range({ itemCount: 5.8, itemHeight: 0, buffer: -3 })
    expect(clamped.totalHeight).toBe(5)
    expect(clamped.offsetOf(-4)).toBe(0)
    expect(clamped.offsetOf(99)).toBe(5)
  })

  it('heights 为 null 走定高公式；动态路径末尾夹取到 count - 1', () => {
    const nullHeights = range({ itemCount: 10, itemHeight: 10, heights: null, scrollTop: 35, viewportHeight: 10 })
    expect(nullHeights.startIndex).toBe(3)
    const dynamic = range({ itemCount: 4, itemHeight: 10, heights: [10, 10, 10, 10], scrollTop: 1000, viewportHeight: 10 })
    expect(dynamic.indexAt(1000)).toBe(3)
  })
})
