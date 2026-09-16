/** 滚动基建用例：滚动容器 / 位置存储 / 虚拟范围。 */

import { mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  ScrollContainer,
  useVirtualRange,
} from '../src'

function stubMetrics(el: Element, scrollHeight: number, clientHeight: number): void {
  Object.defineProperty(el, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: clientHeight, configurable: true })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ScrollContainer（迁移）', () => {
  it('渲染：插槽与尺寸解析', () => {
    const wrapper = mount(ScrollContainer, {
      props: { height: 240, maxHeight: '50vh' },
      slots: { header: '<div class="head">头</div>', default: '<div class="body">主体</div>', footer: '<div class="foot">脚</div>' },
    })
    expect(wrapper.find('.bms-scroll-container').exists()).toBe(true)
    expect(wrapper.find('.head').exists()).toBe(true)
    expect(wrapper.find('.body').exists()).toBe(true)
    expect(wrapper.find('.foot').exists()).toBe(true)
    const style = wrapper.find('.bms-scroll-container-body').attributes('style') ?? ''
    expect(style).toContain('height: 240px')
    expect(style).toContain('max-height: 50vh')
  })

  it('滚动事件与触底 / 触顶（IO 不可用降级 + 离开重置）', async () => {
    const wrapper = mount(ScrollContainer, {
      props: { throttle: 0, threshold: 10 },
      slots: { default: '<div style="height: 1000px" />' },
    })
    const body = wrapper.find('.bms-scroll-container-body').element as HTMLElement
    stubMetrics(body, 1000, 200)

    body.scrollTop = 500
    await wrapper.find('.bms-scroll-container-body').trigger('scroll')
    expect(wrapper.emitted('scroll')?.[0]?.[0]).toMatchObject({ scrollTop: 500, scrollHeight: 1000, clientHeight: 200 })
    expect(wrapper.emitted('reach-bottom')).toBeUndefined()

    body.scrollTop = 810
    await wrapper.find('.bms-scroll-container-body').trigger('scroll')
    expect(wrapper.emitted('reach-bottom')).toHaveLength(1)
    expect(wrapper.emitted('reach-top')).toBeUndefined()

    body.scrollTop = 500
    await wrapper.find('.bms-scroll-container-body').trigger('scroll')
    body.scrollTop = 0
    await wrapper.find('.bms-scroll-container-body').trigger('scroll')
    expect(wrapper.emitted('reach-top')).toHaveLength(1)
  })

  it('位置保持：卸载保存、重挂载恢复', async () => {
    const first = mount(ScrollContainer, {
      props: { keepPosition: true, positionKey: 'spec-keep-1' },
      slots: { default: '<div style="height: 800px" />' },
    })
    const body = first.find('.bms-scroll-container-body').element as HTMLElement
    body.scrollTop = 88
    await first.find('.bms-scroll-container-body').trigger('scroll')
    first.unmount()

    const second = mount(ScrollContainer, {
      props: { keepPosition: true, positionKey: 'spec-keep-1' },
      slots: { default: '<div style="height: 800px" />' },
    })
    await second.vm.$nextTick()
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    const restored = second.find('.bms-scroll-container-body').element as HTMLElement
    expect(restored.scrollTop).toBe(88)
  })

  it('暴露方法：scrollTo / scrollToTop / scrollToBottom', async () => {
    const scrollToMock = vi.fn()
    Element.prototype.scrollTo = scrollToMock
    const wrapper = mount(ScrollContainer, { slots: { default: '<div />' } })
    const vm = wrapper.vm as unknown as {
      scrollTo: (top: number, options?: ScrollToOptions) => void
      scrollToTop: () => void
      scrollToBottom: () => void
    }
    vm.scrollTo(120, { behavior: 'smooth' })
    expect(scrollToMock).toHaveBeenCalledWith({ top: 120, behavior: 'smooth' })
    vm.scrollToTop()
    expect(scrollToMock).toHaveBeenCalledWith({ top: 0 })
    vm.scrollToBottom()
    expect(scrollToMock).toHaveBeenCalled()
  })
})

describe('滚动位置存储（迁移）', () => {
  it('内存适配器与存储工厂', () => {
    const storage = createMemoryScrollStorage()
    const store = createScrollPositionStore(storage)
    store.set('a', 12.6)
    expect(store.get('a')).toBe(13)
    store.set('b', Number.NaN)
    expect(store.get('b')).toBeUndefined()
    store.remove('a')
    expect(store.get('a')).toBeUndefined()
  })

  it('sessionStorage 适配器（前缀隔离）', () => {
    const store = createScrollPositionStore(createSessionScrollStorage('spec:'))
    store.set('k', 5)
    expect(window.sessionStorage.getItem('spec:k')).toBe('5')
    expect(store.get('k')).toBe(5)
    store.remove('k')
    expect(window.sessionStorage.getItem('spec:k')).toBeNull()
  })
})

describe('useVirtualRange（迁移）', () => {
  it('定高：范围 / 偏移 / 总量 / 索引', () => {
    const range = effectScope(true).run(() =>
      useVirtualRange({ itemCount: 100, itemHeight: 20, buffer: 2 }),
    )!
    range.setViewport(200, 100)
    expect(range.startIndex.value).toBe(8)
    expect(range.endIndex.value).toBe(18)
    expect(range.offsetY.value).toBe(160)
    expect(range.totalHeight.value).toBe(2000)
    expect(range.offsetOf(50)).toBe(1000)
    expect(range.indexAt(999)).toBe(49)
  })

  it('动态高度：二分定位与估值回退', () => {
    const range = effectScope(true).run(() =>
      useVirtualRange({
        itemCount: 3,
        itemHeight: 10,
        buffer: 0,
        heights: [30, undefined, 50],
        estimated: 25,
      }),
    )!
    expect(range.totalHeight.value).toBe(105)
    expect(range.offsetOf(1)).toBe(30)
    expect(range.offsetOf(2)).toBe(55)
    expect(range.indexAt(56)).toBe(2)

    const empty = effectScope(true).run(() =>
      useVirtualRange({ itemCount: 0, itemHeight: 20, buffer: 0 }),
    )!
    expect(empty.totalHeight.value).toBe(0)
    expect(empty.indexAt(100)).toBe(0)
    empty.setViewport(50, 100)
    expect(empty.startIndex.value).toBe(0)
    expect(empty.endIndex.value).toBe(0)
  })
})
