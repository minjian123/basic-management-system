// kiwi_id: 970
/** 标签输入用例（06_03_03）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { TagInputField } from '../src'

const ElTagStub = defineComponent({
  name: 'ElTag',
  props: { type: { type: String, default: 'info' }, closable: { type: Boolean, default: false } },
  emits: ['close'],
  template: '<span class="el-tag" :data-type="type"><slot /></span>',
})

const stubs = { ElTag: ElTagStub }

const base = { modelValue: [] as string[] }

describe('TagInputField', () => {
  it('回车添加、去重与空白忽略', async () => {
    const wrapper = mount(TagInputField, { props: { ...base }, global: { stubs } })
    const input = wrapper.find('[data-test="tag-input"]')
    await input.setValue('前端')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['前端']])

    await wrapper.setProps({ modelValue: ['前端'] })
    await input.setValue('前端')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)

    await input.setValue('   ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
  })

  it('数量与长度上限发 invalid 且不添加', async () => {
    const wrapper = mount(TagInputField, { props: { modelValue: ['a'], max: 1 }, global: { stubs } })
    const input = wrapper.find('[data-test="tag-input"]')
    await input.setValue('b')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['最多 1 个标签'])
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    const length = mount(TagInputField, { props: { modelValue: [], maxLength: 2 }, global: { stubs } })
    const input2 = length.find('[data-test="tag-input"]')
    await input2.setValue('abc')
    await input2.trigger('keydown', { key: 'Enter' })
    expect(length.emitted('invalid')?.[0]).toEqual(['单个标签最多 2 字'])
  })

  it('建议过滤、点击添加与 allowCreate 限制', async () => {
    const wrapper = mount(TagInputField, {
      props: { modelValue: [], suggestions: ['苹果', '香蕉', '橙子'], allowCreate: false },
      global: { stubs },
    })
    const input = wrapper.find('[data-test="tag-input"]')
    await input.setValue('香')
    expect(wrapper.find('[data-test="tag-suggestions"]').text()).toContain('香蕉')

    await wrapper.find('[data-test="suggest-香蕉"]').trigger('mousedown')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['香蕉']])

    await wrapper.setProps({ modelValue: [] })
    await input.setValue('自定义')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
  })

  it('粘贴批量解析', async () => {
    const wrapper = mount(TagInputField, { props: { ...base }, global: { stubs } })
    const input = wrapper.find('[data-test="tag-input"]')
    await input.trigger('paste', {
      clipboardData: { getData: () => '甲,乙;丙\n丁' },
    })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['甲', '乙', '丙', '丁']])
  })

  it('只读回显与颜色映射', () => {
    const wrapper = mount(TagInputField, {
      props: { modelValue: ['高', '低'], readonly: true, colorMap: { 高: 'danger' } },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="tag-input"]').exists()).toBe(false)
    const tags = wrapper.findAll('.el-tag')
    expect(tags).toHaveLength(2)
    expect(tags[0]?.attributes('data-type')).toBe('danger')
    expect(tags[1]?.attributes('data-type')).toBe('info')
  })

  it('必填校验与外部错误覆盖', async () => {
    const wrapper = mount(TagInputField, { props: { modelValue: [], required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })
})
