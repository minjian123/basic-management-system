/** 双层标签用例（Kiwi 732）：列表固定 / 详情多开 / 关闭相邻。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import FormFrameTabs from '@/components/tabs/FormFrameTabs.vue'

import { mountWithPlugins } from './helpers/mount'

const confirmMock = vi.hoisted(() => vi.fn<(options: unknown) => Promise<boolean>>(async () => true))

vi.mock('@/utils/useConfirm', () => ({
  useConfirm: () => ({ confirm: (options: unknown) => confirmMock(options) }),
}))

beforeEach(() => {
  confirmMock.mockReset().mockResolvedValue(true)
})

const LIST_TAB = { key: 'user:list', title: '用户列表' }
const DETAIL_A = { key: 'user:1', title: '张三' }
const DETAIL_B = { key: 'user:2', title: '李四' }

function mountTabs(props: Record<string, unknown> = {}) {
  return mountWithPlugins(FormFrameTabs, {
    props: { listTab: LIST_TAB, detailTabs: [DETAIL_A, DETAIL_B], activeKey: 'user:1', ...props },
  })
}

function itemByText(wrapper: ReturnType<typeof mountTabs>, text: string) {
  return wrapper.findAll('.bms-form-frame-tab').find((item) => item.text().includes(text))
}

describe('双层标签（Kiwi 732）', () => {
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
