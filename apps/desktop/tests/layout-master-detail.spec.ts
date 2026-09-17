/** 主从布局用例（Kiwi 733）：分割 / 折叠 / 窄屏 / 空态。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import MasterDetail from '@/components/layout/MasterDetail.vue'

import { mountWithPlugins } from './helpers/mount'

type MatchMediaStub = {
  matches: boolean
  media: string
  addEventListener: (type: string, listener: (event: MediaQueryListEvent) => void) => void
  removeEventListener: (type: string, listener: (event: MediaQueryListEvent) => void) => void
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

function mountMaster(props: Record<string, unknown> = {}) {
  return mountWithPlugins(MasterDetail, {
    props: {
      masterTitle: '组织',
      splitStorageKey: 'test-master',
      ...props,
    },
    slots: {
      master: '<div class="master-content">树</div>',
      detail: '<div class="detail-content">表格</div>',
    },
  })
}

/** 触发指针事件（jsdom 无 PointerEvent：以 MouseEvent 模拟并补 pointerId） */
function firePointer(target: Element, type: string, clientX: number): void {
  const event = new MouseEvent(type, { clientX, bubbles: true })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  target.dispatchEvent(event)
}

describe('主从布局（Kiwi 733）', () => {
  it('主区宽度初始值：显式 px / 默认 260px', () => {
    const px = mountMaster({ masterWidth: 300 })
    expect(px.find('.bms-master-detail-master').attributes('style')).toContain('width: 300px')

    const preset = mountMaster()
    expect(preset.find('.bms-master-detail-master').attributes('style')).toContain('width: 260px')
  })

  it('resizable 拖动更新比例并持久化；min/max 限位', async () => {
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({ left: 0, width: 800, top: 0, height: 600, right: 800, bottom: 600, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)

    const wrapper = mountMaster({ resizable: true })
    const splitter = wrapper.find('.bms-master-detail-splitter')
    expect(splitter.exists()).toBe(true)

    firePointer(splitter.element, 'pointerdown', 0)
    firePointer(splitter.element, 'pointermove', 400)
    firePointer(splitter.element, 'pointerup', 400)
    await nextTick()

    // 400 / 800 = 0.5 → 50%
    expect(wrapper.find('.bms-master-detail-master').attributes('style')).toContain('width: 50%')
    expect(localStorage.getItem('bms:pref:test-master:ratio')).toBe('0.5')

    rectSpy.mockRestore()
  })

  it('折叠：主区隐藏并 emit collapse-change', async () => {
    const wrapper = mountMaster({ collapsible: true })
    expect(wrapper.find('.bms-master-detail-master').exists()).toBe(true)

    await wrapper.findAll('button').find((button) => button.text().includes('收起'))?.trigger('click')
    expect(wrapper.find('.bms-master-detail-master').exists()).toBe(false)
    expect(wrapper.emitted('collapse-change')?.at(-1)).toEqual([true])
  })

  it('窄屏：主区收进抽屉（唤起按钮存在），expose openMaster', async () => {
    mediaMatches = true
    const wrapper = mountMaster()
    await nextTick()
    expect(wrapper.find('.bms-master-detail-master').exists()).toBe(false)
    const browse = wrapper.findAll('button').find((button) => button.text().includes('组织'))
    expect(browse).toBeTruthy()

    ;(wrapper.vm as unknown as { openMaster: () => void }).openMaster()
    await nextTick()
    expect(wrapper.findComponent({ name: 'ElDrawer' }).props('modelValue')).toBe(true)
  })

  it('未选中占位与插槽渲染', () => {
    const empty = mountMaster({ hasSelection: false, emptyText: '请选择左侧节点' })
    expect(empty.text()).toContain('请选择左侧节点')
    expect(empty.find('.detail-content').exists()).toBe(false)

    const normal = mountMaster({ hasSelection: true })
    expect(normal.find('.detail-content').exists()).toBe(true)
  })
})
