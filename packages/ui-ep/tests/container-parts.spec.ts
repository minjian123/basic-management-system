/** 容器件用例：分区容器 / 加载容器 / 懒渲染 / 自适应高度 / 宽高比。 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AspectRatio, AutoHeight, LazyContainer, LoadingContainer, SectionContainer } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': { common: { retry: '重试' }, container: { empty: '暂无内容' } } },
})
const withI18n = { plugins: [i18n] }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SectionContainer（迁移）', () => {
  it('标题 / 档位属性 / 非受控折叠', async () => {
    const wrapper = mount(SectionContainer, {
      props: { title: '基本信息', description: '资料', collapsible: true, padding: 'small' },
      slots: { default: '<div class="section-body">内容</div>' },
    })
    expect(wrapper.text()).toContain('基本信息')
    expect(wrapper.find('.bms-section-container--padding-small').exists()).toBe(true)
    expect(wrapper.attributes('data-padding')).toBe('compact')
    expect(wrapper.attributes('data-collapsed')).toBe('false')
    expect(wrapper.find('.section-body').exists()).toBe(true)

    await wrapper.find('[aria-expanded]').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.[0]?.[0]).toBe(true)
    expect(wrapper.emitted('collapse-change')?.[0]?.[0]).toBe(true)
    expect(wrapper.find('.is-collapsed').exists()).toBe(true)
    expect(wrapper.find('.section-body').exists()).toBe(false)
  })

  it('受控折叠：点击只回调不改内部状态', async () => {
    const wrapper = mount(SectionContainer, {
      props: { title: '受控', collapsible: true, collapsed: false },
      slots: { default: '<div class="section-body">内容</div>' },
    })
    await wrapper.find('[aria-expanded]').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.[0]?.[0]).toBe(true)
    expect(wrapper.find('.section-body').exists()).toBe(true)
  })
})

describe('LoadingContainer（迁移）', () => {
  it('状态切换：loading / content / empty / error 与 retry', async () => {
    const content = { default: '<div class="real-content">数据</div>' }
    const loading = mount(LoadingContainer, { props: { loading: true, delay: 0 }, slots: content, global: withI18n })
    expect((loading.vm as unknown as { state: string }).state).toBe('loading')
    expect(loading.find('[data-testid="loading-state"]').exists()).toBe(true)
    expect(loading.find('.real-content').exists()).toBe(false)

    const done = mount(LoadingContainer, { slots: content, global: withI18n })
    expect(done.find('.real-content').exists()).toBe(true)
    expect((done.vm as unknown as { state: string }).state).toBe('content')

    const empty = mount(LoadingContainer, { props: { empty: true }, slots: content, global: withI18n })
    expect(empty.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(empty.find('.real-content').exists()).toBe(false)

    const error = mount(LoadingContainer, { props: { error: '加载失败' }, global: withI18n })
    expect(error.text()).toContain('加载失败')
    await error.find('button').trigger('click')
    expect(error.emitted('retry')).toHaveLength(1)
  })
})

describe('LazyContainer（迁移）', () => {
  it('IO 不可用降级即时渲染；IO 可用时进入视口才渲染', async () => {
    const degraded = mount(LazyContainer, { slots: { default: '<div class="lazy-body">内容</div>' } })
    expect(degraded.find('.lazy-body').exists()).toBe(true)

    const holder: {
      callback: ((entries: { isIntersecting: boolean; target: Element }[]) => void) | null
    } = { callback: null }
    class MockIO {
      constructor(cb: (entries: { isIntersecting: boolean; target: Element }[]) => void) {
        holder.callback = cb
      }
      observe(): void {}
      disconnect(): void {}
      unobserve(): void {}
    }
    vi.stubGlobal('IntersectionObserver', MockIO as unknown as typeof IntersectionObserver)

    const wrapper = mount(LazyContainer, {
      props: { once: true },
      slots: { default: '<div class="lazy-body">内容</div>' },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.lazy-body').exists()).toBe(false)

    holder.callback?.([{ isIntersecting: true, target: wrapper.element }])
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.lazy-body').exists()).toBe(true)
  })
})

describe('AutoHeight / AspectRatio（迁移）', () => {
  it('AutoHeight：渲染与计算暴露', () => {
    const wrapper = mount(AutoHeight, {
      props: { offset: 8, minHeight: 100, scroll: false },
      slots: { default: '<div class="auto-body">内容</div>' },
    })
    expect(wrapper.find('.auto-body').exists()).toBe(true)
    const vm = wrapper.vm as unknown as { recalculate: () => void; height: number }
    vm.recalculate()
    // 无父容器回退视口高（jsdom innerHeight）减 offset；minHeight 裁剪在下方场景验证
    expect(vm.height).toBe(window.innerHeight - 8)
    expect(wrapper.find('.bms-auto-height--scroll').exists()).toBe(false)

    const clipped = mount(AutoHeight, { props: { minHeight: 9999 }, slots: { default: '<div />' } })
    ;(clipped.vm as unknown as { recalculate: () => void }).recalculate()
    expect((clipped.vm as unknown as { height: number }).height).toBe(9999)
  })

  it('AspectRatio：比例解析与 fit 类', () => {
    const wrapper = mount(AspectRatio, { props: { ratio: '16/9' }, slots: { default: '<div />' } })
    const style = wrapper.attributes('style') ?? ''
    expect(style).toContain('--bms-aspect-ratio-number')
    expect(wrapper.find('.bms-aspect-ratio--fit-cover').exists()).toBe(true)

    const fourThree = mount(AspectRatio, { props: { ratio: 4 / 3, fit: 'contain' }, slots: { default: '<div />' } })
    expect(fourThree.attributes('style')).toContain('1.333')
    expect(fourThree.find('.bms-aspect-ratio--fit-contain').exists()).toBe(true)
  })
})
