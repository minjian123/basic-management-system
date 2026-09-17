import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import { configureConfirm, FormFrameTabs } from '../src'

const confirmMock = vi.fn<(options: unknown) => Promise<boolean>>(async () => true)

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': { tabs: { refresh: '刷新', closeCurrent: '关闭当前', closeOthers: '关闭其他', closeRight: '关闭右侧', closeAll: '关闭全部', exceed: '打开的标签过多，已自动关闭最早打开的标签' } } },
})

beforeEach(() => {
  confirmMock.mockReset().mockResolvedValue(true)
  configureConfirm((options) => confirmMock(options))
})

afterEach(() => {
  configureConfirm(undefined)
})

const LIST_TAB = { key: 'user:list', title: '用户列表' }
const DETAIL_A = { key: 'user:1', title: '张三' }
const DETAIL_B = { key: 'user:2', title: '李四' }

function mountTabs(props: Record<string, unknown> = {}) {
  return mount(FormFrameTabs, {
    props: { listTab: LIST_TAB, detailTabs: [DETAIL_A, DETAIL_B], activeKey: 'user:1', ...props },
    global: { plugins: [i18n] },
  })
}

function itemByText(wrapper: ReturnType<typeof mountTabs>, text: string) {
  return wrapper.findAll('.bms-form-frame-tab').find((item) => item.text().includes(text))
}

describe('双层标签（Kiwi 732 · 移植）', () => {
  it('列表 Tab 固定（无关闭按钮）；详情 Tab 多开渲染与激活', () => {
    const wrapper = mountTabs()
    const items = wrapper.findAll('.bms-form-frame-tab')
    expect(items).toHaveLength(3)
    expect(itemByText(wrapper, '用户列表')?.find('.bms-form-frame-tab-close').exists()).toBe(false)
    expect(itemByText(wrapper, '用户列表')?.classes()).toContain('is-list')
    expect(itemByText(wrapper, '张三')?.classes()).toContain('is-active')
  })

  it('点击标签 emit select + update:activeKey', async () => {
    const wrapper = mountTabs()
    await itemByText(wrapper, '李四')?.trigger('click')
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['user:2'])
    expect(wrapper.emitted('update:activeKey')?.at(-1)).toEqual(['user:2'])
  })

  it('关闭激活详情：激活右邻；无右取左；无详情回列表', async () => {
    const wrapper = mountTabs()
    await itemByText(wrapper, '张三')?.find('.bms-form-frame-tab-close').trigger('click')
    expect(wrapper.emitted('close')?.at(-1)).toEqual(['user:1'])
    expect(wrapper.emitted('update:activeKey')?.at(-1)).toEqual(['user:2'])

    const single = mountTabs({ detailTabs: [DETAIL_A], activeKey: 'user:1' })
    await itemByText(single, '张三')?.find('.bms-form-frame-tab-close').trigger('click')
    expect(single.emitted('update:activeKey')?.at(-1)).toEqual(['user:list'])
  })

  it('dirty 详情关闭确认：继续编辑不关', async () => {
    confirmMock.mockResolvedValue(false)
    const wrapper = mountTabs({ detailTabs: [{ ...DETAIL_A, dirty: true }, DETAIL_B] })
    await itemByText(wrapper, '张三')?.find('.bms-form-frame-tab-close').trigger('click')
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
