/** 基础布局件一用例（Kiwi 735）：栅格 / 间距分割线 / 分栏。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import Divider from '@/components/layout/Divider.vue'
import GridCol from '@/components/layout/GridCol.vue'
import GridRow from '@/components/layout/GridRow.vue'
import Space from '@/components/layout/Space.vue'
import Split from '@/components/layout/Split.vue'

import { mountWithPlugins } from './helpers/mount'

type MatchMediaStub = {
  matches: boolean
  media: string
  addEventListener: () => void
  removeEventListener: () => void
}

let mediaMatches = false

beforeEach(() => {
  mediaMatches = false
  vi.stubGlobal('matchMedia', (query: string): MatchMediaStub => ({
    matches: mediaMatches,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function firePointer(target: Element, type: string, clientX: number, clientY = 0): void {
  const event = new MouseEvent(type, { clientX, clientY, bubbles: true })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  target.dispatchEvent(event)
}

describe('基础布局件一（Kiwi 735）', () => {
  it('栅格：span / offset / 断点与 gutter 透传', () => {
    const col = mountWithPlugins(GridCol, { props: { span: 12, offset: 4, md: 8 } })
    const colVm = col.findComponent({ name: 'ElCol' })
    expect(colVm.props('span')).toBe(12)
    expect(colVm.props('offset')).toBe(4)
    expect(colVm.props('md')).toBe(8)

    const row = mountWithPlugins(GridRow, {
      props: { gutter: 16, justify: 'space-between', align: 'middle' },
      slots: { default: '<div />' },
    })
    const rowVm = row.findComponent({ name: 'ElRow' })
    expect(rowVm.props('gutter')).toBe(16)
    expect(rowVm.props('justify')).toBe('space-between')
    expect(rowVm.props('align')).toBe('middle')
  })

  it('间距与分割线：尺寸档位映射令牌；方向 / 文案位置 / 虚线', () => {
    const spaceDefault = mountWithPlugins(Space, { slots: { default: '<span>a</span><span>b</span>' } })
    expect(spaceDefault.findComponent({ name: 'ElSpace' }).props('size')).toBe(8)

    const spaceSmall = mountWithPlugins(Space, {
      props: { size: 'small', direction: 'vertical' },
      slots: { default: '<span>a</span><span>b</span>' },
    })
    expect(spaceSmall.findComponent({ name: 'ElSpace' }).props('size')).toBe(4)
    expect(spaceSmall.findComponent({ name: 'ElSpace' }).props('direction')).toBe('vertical')

    const divider = mountWithPlugins(Divider, {
      props: { contentPosition: 'left', dashed: true },
      slots: { default: '分组' },
    })
    const dividerVm = divider.findComponent({ name: 'ElDivider' })
    expect(dividerVm.props('contentPosition')).toBe('left')
    expect(dividerVm.props('borderStyle')).toBe('dashed')
  })

  it('分栏：初始比例与拖拽（resize / resize-end / 持久化 / max 限位）', async () => {
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0,
        top: 0,
        width: 800,
        height: 600,
        right: 800,
        bottom: 600,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect)

    const wrapper = mountWithPlugins(Split, {
      props: { defaultRatio: 0.5, storageKey: 'test-split' },
      slots: { first: '<div class="first">左</div>', second: '<div class="second">右</div>' },
    })
    expect(wrapper.find('.bms-split-first').attributes('style')).toContain('width: 50%')

    const splitter = wrapper.find('.bms-split-splitter')
    firePointer(splitter.element, 'pointerdown', 0)
    firePointer(splitter.element, 'pointermove', 500)
    expect(wrapper.emitted('resize')?.at(-1)).toEqual([0.625])

    firePointer(splitter.element, 'pointermove', 790)
    expect(wrapper.emitted('resize')?.at(-1)).toEqual([0.7])

    firePointer(splitter.element, 'pointerup', 500)
    expect(wrapper.emitted('resize-end')?.at(-1)).toEqual([0.7])
    expect(localStorage.getItem('bms:pref:test-split:ratio')).toBe('0.7')

    rectSpy.mockRestore()
  })

  it('分栏：折叠与窄屏转单栏', async () => {
    const wrapper = mountWithPlugins(Split, {
      props: { collapsible: true },
      slots: { first: '<div>左</div>', second: '<div>右</div>' },
    })
    await wrapper.find('.bms-split-collapse').trigger('click')
    expect(wrapper.emitted('collapse-change')?.at(-1)).toEqual([true])
    expect(wrapper.find('.bms-split-first').attributes('style')).toContain('width: 0px')

    mediaMatches = true
    const narrow = mountWithPlugins(Split, {
      props: { direction: 'horizontal' },
      slots: { first: '<div>左</div>', second: '<div>右</div>' },
    })
    await nextTick()
    expect(narrow.find('.bms-split--vertical').exists()).toBe(true)
  })
})
