/** 滚动容器用例（Kiwi 742）：高度 / 滚动条 / 触底触顶 / 暴露方法。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { ScrollContainer } from '@/components/container'

import { mountWithPlugins } from './helpers/mount'
import { IOStub } from './helpers/observers'

type Wrapper = ReturnType<typeof mountWithPlugins>

function bodyOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-scroll-container-body').element as HTMLElement
}

function sizeBody(
  wrapper: Wrapper,
  options: { scrollHeight?: number; clientHeight?: number; scrollTop?: number } = {},
): HTMLElement {
  const { scrollHeight = 300, clientHeight = 100, scrollTop = 0 } = options
  const body = bodyOf(wrapper)
  Object.defineProperty(body, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(body, 'clientHeight', { value: clientHeight, configurable: true })
  body.scrollTop = scrollTop
  // jsdom 未实现 scrollTo：以同步赋值模拟
  body.scrollTo = ((input?: ScrollToOptions | number) => {
    const top = typeof input === 'number' ? input : (input?.top ?? 0)
    body.scrollTop = top
  }) as unknown as typeof body.scrollTo
  return body
}

function scrollEvent(wrapper: Wrapper): Promise<void> {
  return wrapper.find('.bms-scroll-container-body').trigger('scroll')
}

beforeEach(() => {
  IOStub.instances = []
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('滚动容器（Kiwi 742）', () => {
  it('高度解析与滚动条：height / maxHeight / auto / nativeScrollbar', async () => {
    const wrapper = mountWithPlugins(ScrollContainer, {
      props: { height: 200, maxHeight: '50vh' },
    })
    const body = bodyOf(wrapper)
    expect(body.style.height).toBe('200px')
    expect(body.style.maxHeight).toBe('50vh')
    expect(body.classList.contains('bms-scroll-container--styled')).toBe(true)

    const autoWrapper = mountWithPlugins(ScrollContainer, { props: { height: 'auto' } })
    expect(bodyOf(autoWrapper).style.height).toBe('auto')

    const nativeWrapper = mountWithPlugins(ScrollContainer, { props: { nativeScrollbar: true } })
    expect(bodyOf(nativeWrapper).classList.contains('bms-scroll-container--styled')).toBe(false)
  })

  it('插槽：header / footer 固定区与默认滚动区', () => {
    const wrapper = mountWithPlugins(ScrollContainer, {
      slots: {
        header: '<div class="my-header">头</div>',
        footer: '<div class="my-footer">底</div>',
        default: '<div class="my-content">内容</div>',
      },
    })
    expect(wrapper.find('.bms-scroll-container-header .my-header').exists()).toBe(true)
    expect(wrapper.find('.bms-scroll-container-footer .my-footer').exists()).toBe(true)
    expect(wrapper.find('.bms-scroll-container-body .my-content').exists()).toBe(true)
  })

  it('scroll 事件：节流（leading + trailing）与尺寸参数', async () => {
    vi.useFakeTimers()
    const wrapper = mountWithPlugins(ScrollContainer, { props: { throttle: 100 } })
    const body = sizeBody(wrapper, { scrollTop: 30 })

    await scrollEvent(wrapper)
    const events = wrapper.emitted('scroll') as unknown[][]
    expect(events).toHaveLength(1)
    expect(events[0][0]).toEqual({ scrollTop: 30, scrollHeight: 300, clientHeight: 100 })

    // 节流窗口内：不立即发，窗口结束补发一次（trailing）
    body.scrollTop = 60
    await scrollEvent(wrapper)
    expect((wrapper.emitted('scroll') as unknown[][]).length).toBe(1)
    vi.advanceTimersByTime(100)
    const trailing = wrapper.emitted('scroll') as unknown[][]
    expect(trailing).toHaveLength(2)
    expect(trailing[1][0]).toEqual({ scrollTop: 60, scrollHeight: 300, clientHeight: 100 })
  })

  it('scroll 事件：throttle=0 不节流', async () => {
    const wrapper = mountWithPlugins(ScrollContainer, { props: { throttle: 0 } })
    sizeBody(wrapper)
    await scrollEvent(wrapper)
    await scrollEvent(wrapper)
    expect((wrapper.emitted('scroll') as unknown[][]).length).toBe(2)
  })

  it('触底触顶（IO 哨兵）：进入触发一次、离开重置', async () => {
    vi.stubGlobal('IntersectionObserver', IOStub)
    const wrapper = mountWithPlugins(ScrollContainer, { props: { threshold: 20 } })
    await nextTick()
    expect(IOStub.instances).toHaveLength(1)
    const io = IOStub.instances[0]
    expect(io.observed).toHaveLength(2)
    expect(io.options?.root).toBe(bodyOf(wrapper))
    expect(io.options?.rootMargin).toBe('20px 0px 20px 0px')

    const bottom = io.observed[1]
    io.callback([{ target: bottom, isIntersecting: true }])
    io.callback([{ target: bottom, isIntersecting: true }])
    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(1)

    io.callback([{ target: bottom, isIntersecting: false }])
    io.callback([{ target: bottom, isIntersecting: true }])
    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(2)

    const top = io.observed[0]
    io.callback([{ target: top, isIntersecting: true }])
    expect((wrapper.emitted('reach-top') as unknown[][]).length).toBe(1)
  })

  it('触底触顶（IO 不可用降级）：scroll 计算与离开重置', async () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const wrapper = mountWithPlugins(ScrollContainer, { props: { threshold: 10 } })
    const body = sizeBody(wrapper)

    body.scrollTop = 100 // 余量 200 > 10
    await scrollEvent(wrapper)
    expect(wrapper.emitted('reach-bottom')).toBeUndefined()

    body.scrollTop = 195 // 余量 5 ≤ 10
    await scrollEvent(wrapper)
    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(1)

    body.scrollTop = 100
    await scrollEvent(wrapper)
    body.scrollTop = 200
    await scrollEvent(wrapper)
    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(2)

    body.scrollTop = 0
    await scrollEvent(wrapper)
    expect((wrapper.emitted('reach-top') as unknown[][]).length).toBe(1)
  })

  it('暴露方法：scrollTo / scrollToTop / scrollToBottom / scrollTop / el', async () => {
    const wrapper = mountWithPlugins(ScrollContainer)
    const body = sizeBody(wrapper)
    const vm = wrapper.vm as unknown as {
      scrollTo: (top: number, options?: ScrollToOptions) => void
      scrollToTop: () => void
      scrollToBottom: () => void
      scrollTop: number
      el: HTMLElement | null
    }

    expect(vm.el).toBe(body)
    vm.scrollTo(50)
    expect(body.scrollTop).toBe(50)
    expect(vm.scrollTop).toBe(50)
    vm.scrollToTop()
    expect(body.scrollTop).toBe(0)
    vm.scrollToBottom()
    expect(body.scrollTop).toBe(300)
  })
})
