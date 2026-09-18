/** 穿梭框用例（06_03_02）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { TransferField } from '../src'

const ElTransferStub = defineComponent({
  name: 'ElTransfer',
  props: {
    modelValue: { type: Array, default: () => [] },
    data: { type: Array, default: () => [] },
    titles: { type: Array, default: () => [] },
    filterable: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    renderContent: { type: Function, default: undefined },
    props: { type: Object, default: () => ({}) },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-transfer" :data-count="data.length"><button data-test="move-b" @click="$emit(\'update:modelValue\', [\'b\'])" /><button data-test="move-all" @click="$emit(\'update:modelValue\', [\'a\', \'b\', \'c\'])" /></div>',
})

const stubs = { ElTransfer: ElTransferStub }

const data = [
  { key: 'a', label: '甲', group: '组一' },
  { key: 'b', label: '乙', group: '组一' },
  { key: 'c', label: '丙' },
]

describe('TransferField', () => {
  it('值数组归一与变更派发', async () => {
    const wrapper = mount(TransferField, { props: { modelValue: [], data }, global: { stubs } })
    expect(wrapper.findComponent(ElTransferStub).props('modelValue')).toEqual([])
    await wrapper.find('[data-test="move-b"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['b']])
  })

  it('上限越界拒绝并派发 invalid', async () => {
    const wrapper = mount(TransferField, { props: { modelValue: [], data, limit: 2 }, global: { stubs } })
    await wrapper.find('[data-test="move-all"]').trigger('click')
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['最多选择 2 项'])
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('最多选择 2 项')
  })

  it('异步加载失败进入错误态并可重试', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(TransferField, { props: { modelValue: [], load }, global: { stubs } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('retry')).toBeUndefined()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('数据加载失败')
    await wrapper.find('[data-test="transfer-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('只读标签回显（含缺标签降级）与必填校验', async () => {
    const wrapper = mount(TransferField, {
      props: { modelValue: ['a', 'ghost'], data, readonly: true },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="transfer-readonly"]').text()).toContain('甲')
    expect(wrapper.find('[data-test="transfer-readonly"]').text()).toContain('ghost')

    const required = mount(TransferField, { props: { modelValue: [], data, required: true }, global: { stubs } })
    await required.vm.$nextTick()
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')
  })

  it('搜索与分组渲染函数透传', () => {
    const wrapper = mount(TransferField, { props: { modelValue: [], data, searchable: true }, global: { stubs } })
    const control = wrapper.findComponent(ElTransferStub)
    expect(control.props('filterable')).toBe(true)
    const options = control.props('data') as { label: string }[]
    expect(options[0]?.label).toBe('组一 · 甲')
  })
})
