/** 虚拟列表容器用例（Kiwi 745）：可视区 / 动态高度 / 触底 / 定位。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { VirtualList } from '@/components/container'

import { mountWithPlugins } from './helpers/mount'
import { ROStub } from './helpers/observers'

type Wrapper = ReturnType<typeof mountWithPlugins>

interface Row {
  id: number
}

function makeItems(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({ id: index + 1 }))
}

function bodyOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-virtual-list').element as HTMLElement
}

function spacer(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-virtual-list-spacer').element as HTMLElement
}

function sizeBody(
  wrapper: Wrapper,
  options: { scrollHeight: number; clientHeight: number; scrollTop?: number },
): HTMLElement {
  const body = bodyOf(wrapper)
  Object.defineProperty(body, 'scrollHeight', { value: options.scrollHeight, configurable: true })
  Object.defineProperty(body, 'clientHeight', { value: options.clientHeight, configurable: true })
  body.scrollTop = options.scrollTop ?? 0
  body.scrollTo = ((input?: ScrollToOptions | number) => {
    const top = typeof input === 'number' ? input : (input?.top ?? 0)
    body.scrollTop = top
  }) as unknown as typeof body.scrollTo
  return body
}

/** 等 rAF（滚动合并）与渲染副作用 */
async function flushScroll(): Promise<void> {
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  await nextTick()
}

function itemCount(wrapper: Wrapper): number {
  return wrapper.findAll('[data-testid="virtual-item"]').length
}

beforeEach(() => {
  ROStub.instances = []
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('虚拟列表容器（Kiwi 745）', () => {
  it('定高可视区：缓冲索引 / 撑高 / 偏移 / DOM 数量', async () => {
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(20), itemHeight: 40, height: 200, buffer: 5 },
    })
    // 未设视口（clientHeight 0）：仅估值一项 + 1 + buffer = 7 项
    expect(itemCount(wrapper)).toBe(7)
    expect(spacer(wrapper).style.height).toBe('800px')

    sizeBody(wrapper, { scrollHeight: 800, clientHeight: 200, scrollTop: 400 })
    await wrapper.find('.bms-virtual-list').trigger('scroll')
    await flushScroll()

    // start = indexAt(400) - 5 = 5；end = min(20, indexAt(600) + 1 + 5) = 20
    expect(itemCount(wrapper)).toBe(15)
    const viewport = wrapper.find('.bms-virtual-list-viewport')
    expect(viewport.attributes('style')).toContain('translateY(200px)')
  })

  it('scroll 事件参数（尺寸 + 可视区索引）与触底（进入一次 / 离开重置）', async () => {
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(20), itemHeight: 40, height: 200, buffer: 5, threshold: 0 },
    })
    sizeBody(wrapper, { scrollHeight: 800, clientHeight: 200, scrollTop: 600 })
    await wrapper.find('.bms-virtual-list').trigger('scroll')
    await flushScroll()

    const events = wrapper.emitted('scroll') as unknown[][]
    expect(events.length).toBeGreaterThan(0)
    const payload = events[events.length - 1][0] as {
      scrollTop: number
      scrollHeight: number
      clientHeight: number
      startIndex: number
      endIndex: number
    }
    expect(payload.scrollTop).toBe(600)
    expect(payload.scrollHeight).toBe(800)
    expect(payload.clientHeight).toBe(200)
    expect(payload.startIndex).toBe(10)
    expect(payload.endIndex).toBe(20)

    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(1)

    // 离开底部 → 重置；再触底 → 再次触发
    bodyOf(wrapper).scrollTop = 400
    await wrapper.find('.bms-virtual-list').trigger('scroll')
    await flushScroll()
    bodyOf(wrapper).scrollTop = 600
    await wrapper.find('.bms-virtual-list').trigger('scroll')
    await flushScroll()
    expect((wrapper.emitted('reach-bottom') as unknown[][]).length).toBe(2)
  })

  it('动态高度：RO 测量 → 前缀和重算；可视区上方变化补偿 scrollTop；resetMeasurement 重建', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(10), itemHeight: 40, estimatedHeight: 50, height: 200, buffer: 2 },
    })
    expect(spacer(wrapper).style.height).toBe('500px')

    const ro = ROStub.instances[0]
    expect(ro).toBeDefined()
    // 第 0 项实测 100（估值 50 → 增量 50，但索引 0 在可视区内不补偿）
    ro.callback([{ target: ro.observed[0], borderBoxSize: [{ blockSize: 100 }] }])
    await nextTick()
    expect(spacer(wrapper).style.height).toBe('550px')

    wrapper.vm.resetMeasurement()
    await nextTick()
    expect(spacer(wrapper).style.height).toBe('500px')
  })

  it('动态高度：缓冲项（可视区上方）测量变化补偿 scrollTop', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(20), itemHeight: 40, estimatedHeight: 50, height: 200, buffer: 5 },
    })
    const body = sizeBody(wrapper, { scrollHeight: 1000, clientHeight: 200, scrollTop: 400 })
    await wrapper.find('.bms-virtual-list').trigger('scroll')
    await flushScroll()

    // startIndex = 8 - 5 = 3；第 3 项（缓冲首项，位于可视区上方）实测 100（+50）
    const ro = ROStub.instances[0]
    const first = wrapper.find('[data-testid="virtual-item"]').element
    ro.callback([{ target: first, borderBoxSize: [{ blockSize: 100 }] }])
    await nextTick()
    expect(body.scrollTop).toBe(450)
  })

  it('scrollToIndex（定高 / 越界 pending）/ scrollToTop / scrollToBottom', async () => {
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(20), itemHeight: 40, height: 200, buffer: 5 },
    })
    const body = sizeBody(wrapper, { scrollHeight: 800, clientHeight: 200 })
    const vm = wrapper.vm as unknown as {
      scrollToIndex: (index: number) => void
      scrollToTop: () => void
      scrollToBottom: () => void
      scrollTop: number
      el: HTMLElement | null
    }

    vm.scrollToIndex(5)
    expect(body.scrollTop).toBe(200)

    // 越界 → pending；数据到达后定位一次
    vm.scrollToIndex(25)
    expect(body.scrollTop).toBe(200)
    await wrapper.setProps({ items: makeItems(30) })
    await nextTick()
    await nextTick()
    expect(body.scrollTop).toBe(1000)

    vm.scrollToTop()
    expect(body.scrollTop).toBe(0)
    vm.scrollToBottom()
    expect(body.scrollTop).toBe(800)
    expect(vm.el).toBe(body)
  })

  it('边界：keyField 重复告警 / 空数据 #empty 插槽 / height=auto 退化渲染与告警', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mountWithPlugins(VirtualList, {
      props: { items: makeItems(3), itemHeight: 40, height: 200 },
    })
    await wrapper.setProps({ items: [{ id: 1 }, { id: 1 }, { id: 2 }] })
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('重复值'))
    expect(itemCount(wrapper)).toBe(3)

    const empty = mountWithPlugins(VirtualList, {
      props: { items: [], height: 200 },
      slots: { empty: '<div class="my-empty">暂无数据</div>' },
    })
    expect(empty.find('[data-testid="virtual-empty"] .my-empty').exists()).toBe(true)

    const auto = mountWithPlugins(VirtualList, {
      props: { items: makeItems(20), height: 'auto' },
    })
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('height="auto"'))
    expect(itemCount(auto)).toBe(20)
  })
})
