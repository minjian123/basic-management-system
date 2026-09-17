/** 虚拟列表与全屏容器用例。 */

import { mount } from '@vue/test-utils'
import { h, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FullscreenContainer, VirtualList } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': { fullscreen: { enter: '全屏', exit: '退出全屏' } } },
})

const items = Array.from({ length: 100 }, (_, index) => ({ id: index, label: `item-${index}` }))

const itemSlot = {
  default: (params: { item: Record<string, unknown> }) =>
    h('span', { class: 'v-label' }, String(params.item.label ?? '')),
}

async function nextFrame(): Promise<void> {
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  await nextTick()
}

function stubMetrics(el: Element, scrollHeight: number, clientHeight: number): void {
  Object.defineProperty(el, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: clientHeight, configurable: true })
}

const originalRequestFullscreen = (Element.prototype as unknown as { requestFullscreen?: unknown })
  .requestFullscreen

afterEach(() => {
  const proto = Element.prototype as unknown as { requestFullscreen?: unknown }
  if (originalRequestFullscreen) {
    proto.requestFullscreen = originalRequestFullscreen
  } else {
    delete proto.requestFullscreen
  }
  vi.restoreAllMocks()
})

describe('VirtualList（迁移）', () => {
  it('渲染：仅可视范围切片', async () => {
    const wrapper = mount(VirtualList, {
      props: { items, itemHeight: 20, height: 100, buffer: 2 },
      slots: itemSlot,
    })
    stubMetrics(wrapper.element, 2000, 100)
    await wrapper.trigger('scroll')
    await nextFrame()
    const rendered = wrapper.findAll('.bms-virtual-list-item')
    expect(rendered.length).toBeGreaterThan(0)
    expect(rendered.length).toBeLessThan(items.length)
    expect(wrapper.text()).toContain('item-0')
    expect(wrapper.text()).not.toContain('item-50')
  })

  it('滚动：emit 度量（含可视索引）并更新渲染范围', async () => {
    const wrapper = mount(VirtualList, {
      props: { items, itemHeight: 20, height: 100, buffer: 2, throttle: 0 },
      slots: itemSlot,
    })
    const body = wrapper.element as HTMLElement
    stubMetrics(body, 4000, 100)
    body.scrollTop = 400
    await wrapper.trigger('scroll')
    await nextFrame()
    const metrics = wrapper.emitted('scroll')?.[0]?.[0] as { scrollTop: number; startIndex: number; endIndex: number }
    expect(metrics.scrollTop).toBe(400)
    expect(metrics.startIndex).toBe(18)
    expect(metrics.endIndex).toBe(28)
    expect(wrapper.text()).toContain('item-18')
    expect(wrapper.text()).not.toContain('item-0')
  })

  it('暴露：scrollToTop / scrollToBottom / scrollToIndex', async () => {
    const scrollToMock = vi.fn()
    Element.prototype.scrollTo = scrollToMock
    const wrapper = mount(VirtualList, {
      props: { items, itemHeight: 20, height: 100 },
      slots: itemSlot,
    })
    const vm = wrapper.vm as unknown as {
      scrollToTop: () => void
      scrollToBottom: () => void
      scrollToIndex: (index: number) => void
      scrollTop: number
    }
    vm.scrollToTop()
    expect(scrollToMock).toHaveBeenCalledWith({ top: 0 })
    vm.scrollToBottom()
    expect(scrollToMock).toHaveBeenCalled()
    vm.scrollToIndex(30)
    expect(scrollToMock).toHaveBeenLastCalledWith({ top: 600 })
    expect(vm.scrollTop).toBe(0)
  })
})

describe('FullscreenContainer（迁移）', () => {
  it('降级路径：无 Fullscreen API 时用 CSS 兜底，enter / exit / toggle 可切换', async () => {
    delete (Element.prototype as unknown as { requestFullscreen?: unknown }).requestFullscreen
    const wrapper = mount(FullscreenContainer, {
      slots: { default: '<div class="fs-body">内容</div>' },
      global: { plugins: [i18n] },
    })
    const vm = wrapper.vm as unknown as {
      enter: () => Promise<void>
      exit: () => Promise<void>
      toggle: () => void
      readonly isFullscreen: boolean
      readonly isFallback: boolean
    }
    expect(vm.isFallback).toBe(false)
    await vm.enter()
    await wrapper.vm.$nextTick()
    expect(vm.isFallback).toBe(true)
    expect(vm.isFullscreen).toBe(true)
    expect(wrapper.find('.bms-fullscreen-container--fallback').exists()).toBe(true)

    await vm.exit()
    await wrapper.vm.$nextTick()
    expect(vm.isFullscreen).toBe(false)

    vm.toggle()
    await wrapper.vm.$nextTick()
    expect(vm.isFullscreen).toBe(true)
    expect(wrapper.find('.fs-body').exists()).toBe(true)
  })

  it('原生路径：调用 requestFullscreen', async () => {
    const requestMock = vi.fn(async () => undefined)
    ;(Element.prototype as unknown as { requestFullscreen?: () => Promise<void> }).requestFullscreen = requestMock
    const wrapper = mount(FullscreenContainer, { global: { plugins: [i18n] } })
    const vm = wrapper.vm as unknown as { enter: () => Promise<void>; readonly isFallback: boolean }
    await vm.enter()
    expect(requestMock).toHaveBeenCalledTimes(1)
    expect(vm.isFallback).toBe(false)
  })
})
