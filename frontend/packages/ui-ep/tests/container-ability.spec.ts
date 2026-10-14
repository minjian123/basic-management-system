/** 能力容器件用例（04_01_02）。 */

import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FullscreenContainer, LazyContainer, VirtualListContainer } from '../src'

const ElScrollbarStub = defineComponent({
  name: 'ElScrollbar',
  emits: ['scroll'],
  setup(_, { slots, expose }) {
    const wrapRef = { scrollTop: 0, scrollLeft: 0, clientHeight: 100, scrollHeight: 2000 }
    expose({ wrapRef })
    return () => h('div', { class: 'el-scrollbar' }, slots.default?.())
  },
})

/** 可手动触发的 IntersectionObserver 替身。 */
class ObserverStub {
  static instances: ObserverStub[] = []
  callback: IntersectionObserverCallback
  disconnected = false
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    ObserverStub.instances.push(this)
  }
  observe(): void {}
  disconnect(): void {
    this.disconnected = true
  }
  trigger(isIntersecting: boolean): void {
    this.callback([{ isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
  }
}

afterEach(() => {
  ObserverStub.instances = []
  vi.unstubAllGlobals()
})

describe('FullscreenContainer', () => {
  it('能力缺失时降级视口铺满并回传 unsupported', async () => {
    const wrapper = mount(FullscreenContainer, { props: { modelValue: false }, slots: { default: '<div>x</div>' } })
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.emitted('error')?.[0]).toEqual(['unsupported'])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
    expect(wrapper.classes()).toContain('is-degraded')
  })

  it('进入全屏显示退出提示，点击提示可提前关闭', async () => {
    vi.useFakeTimers()
    const wrapper = mount(FullscreenContainer, { props: { modelValue: false }, slots: { default: '<div>x</div>' } })
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="fullscreen-hint"]').text()).toContain('Esc')

    await wrapper.find('[data-test="fullscreen-hint"]').trigger('click')
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(false)
    vi.useRealTimers()
  })

  it('提示超过时长后自动隐藏；退出全屏时提示消失', async () => {
    vi.useFakeTimers()
    const wrapper = mount(FullscreenContainer, { props: { modelValue: false }, slots: { default: '<div>x</div>' } })
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(true)

    vi.advanceTimersByTime(3100)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(false)

    // 再次进入后退出，提示不应残留
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(true)
    await wrapper.setProps({ modelValue: false })
    expect(wrapper.find('[data-test="fullscreen-hint"]').exists()).toBe(false)
    vi.useRealTimers()
  })

  it('showHint 为假时不渲染提示，hint 文案可配', async () => {
    const noHint = mount(FullscreenContainer, {
      props: { modelValue: false, showHint: false },
      slots: { default: '<div>x</div>' },
    })
    await noHint.setProps({ modelValue: true })
    expect(noHint.find('[data-test="fullscreen-hint"]').exists()).toBe(false)

    const custom = mount(FullscreenContainer, {
      props: { modelValue: false, hint: '自定义提示' },
      slots: { default: '<div>x</div>' },
    })
    await custom.setProps({ modelValue: true })
    expect(custom.find('[data-test="fullscreen-hint"]').text()).toBe('自定义提示')
  })

  it('降级态按 Esc 退出', async () => {
    const wrapper = mount(FullscreenContainer, { props: { modelValue: true }, slots: { default: '<div>x</div>' } })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('能力可用时调用 requestFullscreen / exitFullscreen', async () => {
    const request = vi.fn().mockResolvedValue(undefined)
    const exit = vi.fn().mockResolvedValue(undefined)
    ;(HTMLElement.prototype as unknown as { requestFullscreen: () => Promise<void> }).requestFullscreen = request
    ;(document as unknown as { exitFullscreen: () => Promise<void> }).exitFullscreen = exit
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => (request.mock.calls.length > 0 ? wrapperElement : null) })

    const wrapper = mount(FullscreenContainer, { props: { modelValue: false }, slots: { default: '<div>x</div>' } })
    const wrapperElement = wrapper.element
    await wrapper.setProps({ modelValue: true })
    expect(request).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ modelValue: false })
    expect(exit).toHaveBeenCalledTimes(1)
    expect(wrapper.classes()).not.toContain('is-degraded')
  })
})

describe('LazyContainer', () => {
  it('进入视口才渲染并派发 visible（once 断开观察）', async () => {
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    const wrapper = mount(LazyContainer, { slots: { default: '<div data-test="content">内容</div>' } })
    expect(wrapper.find('[data-test="content"]').exists()).toBe(false)

    ObserverStub.instances[0]?.trigger(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.emitted('visible')).toHaveLength(1)
    expect(ObserverStub.instances[0]?.disconnected).toBe(true)
  })

  it('once 为假时离开视口卸载', async () => {
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    const wrapper = mount(LazyContainer, { props: { once: false }, slots: { default: '<div data-test="content">内容</div>' } })
    ObserverStub.instances[0]?.trigger(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)

    ObserverStub.instances[0]?.trigger(false)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="content"]').exists()).toBe(false)
  })

  it('能力缺失时直接渲染', async () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const wrapper = mount(LazyContainer, { slots: { default: '<div data-test="content">内容</div>' } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
  })

  it('占位内容插槽可覆盖内置骨架', () => {
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    const custom = mount(LazyContainer, {
      slots: { default: '<div data-test="content">内容</div>', placeholder: '<div data-test="ph">自定义占位</div>' },
    })
    expect(custom.find('[data-test="lazy-placeholder"]').exists()).toBe(true)
    expect(custom.find('[data-test="ph"]').text()).toBe('自定义占位')
    expect(custom.find('[data-test="content"]').exists()).toBe(false)
  })
})

const items = Array.from({ length: 100 }, (_, index) => ({ id: index }))

describe('VirtualListContainer', () => {
  it('定高快路径只渲染可视区并派发可视区变化', async () => {
    const wrapper = mount(VirtualListContainer, {
      props: { items, itemHeight: 20 },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    const first = wrapper.findAll('[data-test="row"]')
    expect(first).toHaveLength(9)
    expect(first[0]?.text()).toBe('0')

    wrapper.findComponent({ name: 'ElScrollbar' }).vm.$emit('scroll', { scrollTop: 200, scrollLeft: 0 })
    await wrapper.vm.$nextTick()
    const scrolled = wrapper.findAll('[data-test="row"]')
    expect(scrolled).toHaveLength(13)
    expect(scrolled[0]?.text()).toBe('6')
    expect(wrapper.emitted('visible-change')?.at(-1)).toEqual([{ start: 6, end: 19 }])
  })

  it('空数据渲染零高且不派发行', () => {
    const wrapper = mount(VirtualListContainer, {
      props: { items: [] },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    expect(wrapper.findAll('[data-test="row"]')).toHaveLength(0)
    expect(wrapper.find('.bms-virtual-list-container__spacer').attributes('style')).toContain('height: 0px')
  })

  it('触底派发 reach-bottom，回滚后重置', async () => {
    const wrapper = mount(VirtualListContainer, {
      props: { items, itemHeight: 20 },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    await wrapper.vm.$nextTick()
    const bar = wrapper.findComponent({ name: 'ElScrollbar' })
    // wrap 替身：clientHeight 100 / scrollHeight 2000
    bar.vm.$emit('scroll', { scrollTop: 1900, scrollLeft: 0 })
    bar.vm.$emit('scroll', { scrollTop: 1905, scrollLeft: 0 })
    expect(wrapper.emitted('reach-bottom')).toHaveLength(1)

    bar.vm.$emit('scroll', { scrollTop: 10, scrollLeft: 0 })
    bar.vm.$emit('scroll', { scrollTop: 1900, scrollLeft: 0 })
    expect(wrapper.emitted('reach-bottom')).toHaveLength(2)
  })

  it('scrollToIndex 暴露并滚动到指定项（定高与动态高度）', async () => {
    const fixed = mount(VirtualListContainer, {
      props: { items, itemHeight: 20 },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    const exposed = fixed.vm as unknown as { scrollToIndex: (index: number) => Promise<void> }
    await exposed.scrollToIndex(50)
    const instance = fixed.findComponent({ name: 'ElScrollbar' }).vm as unknown as {
      wrapRef: { scrollTop: number }
    }
    expect(instance.wrapRef.scrollTop).toBe(1000)

    // 动态高度：按估算值累计
    const dynamic = mount(VirtualListContainer, {
      props: { items, estimatedHeight: 30 },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    const dynamicExposed = dynamic.vm as unknown as { scrollToIndex: (index: number) => Promise<void> }
    await dynamicExposed.scrollToIndex(10)
    const dynamicInstance = dynamic.findComponent({ name: 'ElScrollbar' }).vm as unknown as {
      wrapRef: { scrollTop: number }
    }
    expect(dynamicInstance.wrapRef.scrollTop).toBe(300)
  })

  it('itemKey 指定项唯一键字段', () => {
    const wrapper = mount(VirtualListContainer, {
      props: { items: [{ code: 'a' }, { code: 'b' }], itemHeight: 20, itemKey: 'code' },
      global: { stubs: { ElScrollbar: ElScrollbarStub } },
      slots: { default: '<span data-test="row">{{ index }}</span>' },
    })
    expect(wrapper.findAll('.bms-virtual-list-container__item')).toHaveLength(2)
  })
})
