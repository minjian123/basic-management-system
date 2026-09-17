/** 表单框架壳用例（Kiwi 740）：列表固定 / 详情多开 / 组件映射 / 刷新。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import FormFrame from '@/components/layout/FormFrame.vue'

import { mountWithPlugins } from './helpers/mount'

const confirmMock = vi.hoisted(() => vi.fn<(options: unknown) => Promise<boolean>>(async () => true))

vi.mock('@/utils/useConfirm', () => ({
  useConfirm: () => ({ confirm: (options: unknown) => confirmMock(options) }),
}))

beforeEach(() => {
  confirmMock.mockReset().mockResolvedValue(true)
})

let fetchCount = 0

const DemoList = {
  name: 'DemoList',
  emits: ['open-detail'],
  methods: {
    fetchList() {
      fetchCount += 1
    },
  },
  template: `<div class="demo-list">
    <button class="open-a" @click="$emit('open-detail', 1)">open-1</button>
    <button class="open-b" @click="$emit('open-detail', 2)">open-2</button>
  </div>`,
}

const DemoDetail = {
  name: 'DemoDetail',
  emits: ['saved', 'deleted', 'dirty-change'],
  template: '<div class="demo-detail">详情</div>',
}

function mountFrame(props: Record<string, unknown> = {}) {
  return mountWithPlugins(FormFrame, {
    props: { title: '用户', listComponent: DemoList, detailComponent: DemoDetail, ...props },
  })
}

describe('表单框架壳（Kiwi 740）', () => {
  it('列表固定 + openDetail 多开 / 已开激活 / 关闭相邻', async () => {
    const wrapper = mountFrame()
    const frame = wrapper.vm as unknown as {
      openDetail: (id: number) => string
      closeDetail: (key: string) => void
      activeKey: string
    }
    expect(wrapper.find('.demo-list').exists()).toBe(true)
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(1)

    frame.openDetail(1)
    await nextTick()
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(2)
    expect(wrapper.find('.demo-detail').exists()).toBe(true)

    frame.openDetail(2)
    await nextTick()
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(3)
    // 已开激活不重复
    frame.openDetail(1)
    await nextTick()
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(3)
    expect(frame.activeKey).toBe('detail:1')

    frame.closeDetail('detail:1')
    await nextTick()
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(2)
    expect(frame.activeKey).toBe('detail:2')
  })

  it('列表事件 open-detail 开详情；saved 关闭并刷新列表', async () => {
    fetchCount = 0
    const wrapper = mountFrame()
    await wrapper.find('.open-a').trigger('click')
    await nextTick()
    expect(wrapper.emitted('open-detail')?.at(-1)).toEqual([1])
    expect(wrapper.find('.demo-detail').exists()).toBe(true)

    wrapper.findComponent({ name: 'detail:1' }).vm.$emit('saved', 1)
    await nextTick()
    expect(wrapper.emitted('saved')?.at(-1)).toEqual([1])
    expect(fetchCount).toBe(1)
    expect(wrapper.find('.demo-detail').exists()).toBe(false)
    expect(wrapper.find('.demo-list').exists()).toBe(true)
  })

  it('组件映射：未注册渲染空态 + 警告；详情未注册同理', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mountFrame({ listComponent: 'NopeView' })
    await nextTick()
    expect(wrapper.text()).toContain('未注册的组件')
    expect(warn).toHaveBeenCalled()

    const detail = mountFrame({ detailComponent: 'NopeDetailView' })
    ;(detail.vm as unknown as { openDetail: (id: number) => void }).openDetail(1)
    await nextTick()
    expect(detail.text()).toContain('未注册的组件')
    warn.mockRestore()
  })

  it('setDetailDirty → 关闭确认；cacheLimit 上限释放', async () => {
    confirmMock.mockResolvedValue(false)
    const wrapper = mountFrame({ cacheLimit: 2 })
    const frame = wrapper.vm as unknown as {
      openDetail: (id: number) => void
      setDetailDirty: (key: string, dirty: boolean) => void
    }
    frame.openDetail(1)
    await nextTick()
    frame.setDetailDirty('detail:1', true)
    await nextTick()

    await wrapper
      .findAll('.bms-form-frame-tab')
      .find((tab) => tab.text().includes('1'))
      ?.find('.bms-form-frame-tab-close')
      .trigger('click')
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(2)

    // cacheLimit=2：开第 3 个详情时释放最久未激活
    confirmMock.mockResolvedValue(true)
    frame.openDetail(2)
    await nextTick()
    frame.openDetail(3)
    await nextTick()
    expect(wrapper.findAll('.bms-form-frame-tab')).toHaveLength(3) // 列表 + 2 详情
  })
})
