/** 基础容器件用例（04_01_01）。 */

import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AspectRatioContainer, AutoHeightContainer, ScrollContainer, SectionContainer } from '../src'

const ElScrollbarStub = defineComponent({
  name: 'ElScrollbar',
  emits: ['scroll'],
  setup(_, { slots, expose }) {
    const wrapRef = { scrollTop: 0, scrollLeft: 0, clientHeight: 100, scrollHeight: 300 }
    expose({ wrapRef })
    return () => h('div', { class: 'el-scrollbar' }, slots.default?.())
  },
})

const stubs = { ElScrollbar: ElScrollbarStub }

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('ScrollContainer', () => {
  it('派发滚动事件并在触底时只触发一次', () => {
    const wrapper = mount(ScrollContainer, { global: { stubs }, slots: { default: '<div>内容</div>' } })
    const bar = wrapper.findComponent({ name: 'ElScrollbar' })

    bar.vm.$emit('scroll', { scrollTop: 10, scrollLeft: 0 })
    expect(wrapper.emitted('scroll')?.[0]).toEqual([{ top: 10, left: 0 }])
    expect(wrapper.emitted('reach-bottom')).toBeUndefined()

    bar.vm.$emit('scroll', { scrollTop: 250, scrollLeft: 0 })
    bar.vm.$emit('scroll', { scrollTop: 260, scrollLeft: 0 })
    expect(wrapper.emitted('reach-bottom')).toHaveLength(1)

    bar.vm.$emit('scroll', { scrollTop: 0, scrollLeft: 0 })
    bar.vm.$emit('scroll', { scrollTop: 250, scrollLeft: 0 })
    expect(wrapper.emitted('reach-bottom')).toHaveLength(2)
  })

  it('位置保持键写入会话存储', () => {
    const wrapper = mount(ScrollContainer, {
      props: { positionKey: 'list' },
      global: { stubs },
      slots: { default: '<div>内容</div>' },
    })
    const bar = wrapper.findComponent({ name: 'ElScrollbar' })
    ;(bar.vm as unknown as { wrapRef: { scrollTop: number } }).wrapRef.scrollTop = 120
    wrapper.unmount()
    expect(sessionStorage.getItem('scroll:list')).toBe('120')
  })

  it('原生模式不渲染 el-scrollbar', () => {
    const wrapper = mount(ScrollContainer, { props: { native: true }, slots: { default: '<div>内容</div>' } })
    expect(wrapper.find('.el-scrollbar').exists()).toBe(false)
  })
})

describe('AutoHeightContainer', () => {
  it('缺省占满父容器，offset 时按 calc 扣减', () => {
    const full = mount(AutoHeightContainer, { slots: { default: '<div>x</div>' } })
    expect(full.attributes('style')).toContain('height: 100%')

    const offset = mount(AutoHeightContainer, {
      props: { offset: 48, minHeight: '120px' },
      slots: { default: '<div>x</div>' },
    })
    expect(offset.attributes('style')).toContain('height: calc(100% - 48px)')
    expect(offset.attributes('style')).toContain('min-height: 120px')
  })

  it('offset 支持 CSS 长度', () => {
    const wrapper = mount(AutoHeightContainer, { props: { offset: '4rem' }, slots: { default: '<div>x</div>' } })
    expect(wrapper.attributes('style')).toContain('height: calc(100% - 4rem)')
  })
})

describe('SectionContainer', () => {
  it('渲染标题与工具区，可折叠切换', async () => {
    const wrapper = mount(SectionContainer, {
      props: { title: '分区', collapsible: true, collapsed: false },
      slots: { extra: '<button data-test="extra">编辑</button>', default: '<div data-test="body">内容</div>' },
    })
    expect(wrapper.text()).toContain('分区')
    expect(wrapper.find('[data-test="extra"]').exists()).toBe(true)

    await wrapper.find('[data-test="section-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([true])
    expect(wrapper.find('.bms-section-container__body').attributes('style')).toContain('display: none')
  })

  it('不可折叠时点击标题不切换', async () => {
    const wrapper = mount(SectionContainer, { props: { title: '分区' }, slots: { default: '<div>x</div>' } })
    await wrapper.find('.bms-section-container__header').trigger('click')
    expect(wrapper.emitted('update:collapsed')).toBeUndefined()
  })

  it('无标题且不可折叠时不渲染头部', () => {
    const wrapper = mount(SectionContainer, { slots: { default: '<div>x</div>' } })
    expect(wrapper.find('.bms-section-container__header').exists()).toBe(false)
  })
})

describe('AspectRatioContainer', () => {
  it('能力不可用时降级 padding-top 技巧', () => {
    vi.stubGlobal('CSS', { supports: () => false })
    const wrapper = mount(AspectRatioContainer, { props: { ratio: 16 / 9 }, slots: { default: '<div>x</div>' } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.attributes('style')).toContain('56.25%')
  })

  it('能力可用时使用 aspect-ratio', () => {
    vi.stubGlobal('CSS', { supports: () => true })
    const wrapper = mount(AspectRatioContainer, { props: { ratio: 4 / 3 }, slots: { default: '<div>x</div>' } })
    expect(wrapper.attributes('data-degraded')).toBe('false')
    expect(wrapper.attributes('style')).toContain('aspect-ratio')
  })

  it('非法比例回退 16/9', () => {
    vi.stubGlobal('CSS', { supports: () => false })
    const wrapper = mount(AspectRatioContainer, { props: { ratio: 0 }, slots: { default: '<div>x</div>' } })
    expect(wrapper.attributes('style')).toContain('56.25%')
  })
})

describe('组合可用', () => {
  it('分区 + 滚动 + 自适应可组合挂载', () => {
    const wrapper = mount(SectionContainer, {
      props: { title: '详情' },
      global: { stubs, components: { ScrollContainer, AutoHeightContainer } },
      slots: {
        default:
          '<auto-height-container :offset="40"><scroll-container position-key="combo"><div data-test="content">内容</div></scroll-container></auto-height-container>',
      },
    })
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
  })
})
