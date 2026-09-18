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
})
