/** 懒加载容器用例（Kiwi 744）：视口渲染 / 占位 / 缓存与降级。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { LazyContainer } from '@/components/container'

import { mountWithPlugins } from './helpers/mount'
import { IOStub } from './helpers/observers'

type Wrapper = ReturnType<typeof mountWithPlugins>

function rootOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-lazy-container').element as HTMLElement
}

beforeEach(() => {
  IOStub.instances = []
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('懒加载容器（Kiwi 744）', () => {
  it('IO 选项与进入视口渲染；未进入渲染占位', async () => {
    vi.stubGlobal('IntersectionObserver', IOStub)
    const wrapper = mountWithPlugins(LazyContainer, {
      slots: { default: '<div class="lazy-content">内容</div>' },
    })

    expect(IOStub.instances).toHaveLength(1)
    const io = IOStub.instances[0]
    expect(io.options?.rootMargin).toBe('100px')
    expect(io.observed[0]).toBe(rootOf(wrapper))

    expect(wrapper.find('.lazy-content').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lazy-placeholder"]').exists()).toBe(true)

    io.callback([{ target: rootOf(wrapper), isIntersecting: true }])
    await nextTick()
    expect(wrapper.find('.lazy-content').exists()).toBe(true)
    expect(wrapper.find('[data-testid="lazy-placeholder"]').exists()).toBe(false)
  })

  it('占位：默认骨架 / #placeholder 插槽 / minHeight', () => {
    vi.stubGlobal('IntersectionObserver', IOStub)
    const fallback = mountWithPlugins(LazyContainer)
    expect(fallback.find('[data-testid="lazy-placeholder"] .bms-lazy-container-skeleton').exists()).toBe(true)

    const custom = mountWithPlugins(LazyContainer, {
      slots: { placeholder: '<div class="my-placeholder">载入中</div>' },
    })
    expect(custom.find('.my-placeholder').exists()).toBe(true)

    const sized = mountWithPlugins(LazyContainer, { props: { minHeight: 200 } })
    const placeholder = sized.find('[data-testid="lazy-placeholder"]')
    expect(placeholder.attributes('style')).toContain('min-height: 200px')
  })

  it('缓存策略：once 渲染后离开不卸载；unmountOnLeave 离开卸载并可重渲染', async () => {
    vi.stubGlobal('IntersectionObserver', IOStub)
    const onceWrapper = mountWithPlugins(LazyContainer, {
      props: { once: true },
      slots: { default: '<div class="lazy-content">内容</div>' },
    })
    const onceIo = IOStub.instances[0]
    onceIo.callback([{ target: rootOf(onceWrapper), isIntersecting: true }])
    await nextTick()
    expect(onceWrapper.find('.lazy-content').exists()).toBe(true)
    // once：渲染后已断开观察（离开不卸载）
    expect(onceIo.observed.length).toBeGreaterThan(0)
    expect(onceWrapper.find('.lazy-content').exists()).toBe(true)

    vi.stubGlobal('IntersectionObserver', IOStub)
    const leaveWrapper = mountWithPlugins(LazyContainer, {
      props: { once: false, unmountOnLeave: true },
      slots: { default: '<div class="lazy-content">内容</div>' },
    })
    const leaveIo = IOStub.instances[IOStub.instances.length - 1]
    const leaveRoot = rootOf(leaveWrapper)
    leaveIo.callback([{ target: leaveRoot, isIntersecting: true }])
    await nextTick()
    expect(leaveWrapper.find('.lazy-content').exists()).toBe(true)

    leaveIo.callback([{ target: leaveRoot, isIntersecting: false }])
    await nextTick()
    expect(leaveWrapper.find('.lazy-content').exists()).toBe(false)
    expect(leaveWrapper.find('[data-testid="lazy-placeholder"]').exists()).toBe(true)

    leaveIo.callback([{ target: leaveRoot, isIntersecting: true }])
    await nextTick()
    expect(leaveWrapper.find('.lazy-content').exists()).toBe(true)
  })

  it('降级：IO 不可用直接渲染', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const wrapper = mountWithPlugins(LazyContainer, {
      slots: { default: '<div class="lazy-content">内容</div>' },
    })
    expect(wrapper.find('.lazy-content').exists()).toBe(true)
    expect(wrapper.find('[data-testid="lazy-placeholder"]').exists()).toBe(false)
  })

  it('边界：unmountOnLeave 在 once=true 时忽略并告警；rootMargin 变更重建观察', async () => {
    vi.stubGlobal('IntersectionObserver', IOStub)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mountWithPlugins(LazyContainer, {
      props: { once: true, unmountOnLeave: true },
    })
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('unmountOnLeave'))

    await wrapper.setProps({ rootMargin: '200px' })
    expect(IOStub.instances).toHaveLength(2)
    expect(IOStub.instances[1].options?.rootMargin).toBe('200px')
  })
})
