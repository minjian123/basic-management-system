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

const ElInputStub = defineComponent({
  name: 'ElInput',
  props: {
    modelValue: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    size: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'keydown', 'paste', 'blur'],
  template:
    '<input :value="modelValue" :disabled="disabled" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" @keydown="$emit(\'keydown\', $event)" @paste="$emit(\'paste\', $event)" @blur="$emit(\'blur\')" />',
})

const ElButtonStub = defineComponent({
  name: 'ElButton',
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

const stubs = { ElTag: ElTagStub, ElInput: ElInputStub, ElButton: ElButtonStub }

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

    await wrapper.find('[data-test="suggest-香蕉"]').trigger('click')
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

  it('只读回显为顿号纯文本（11_03 迁移：节点 §3/§4）', () => {
    const wrapper = mount(TagInputField, {
      props: { modelValue: ['高', '低'], readonly: true, colorMap: { 高: 'danger' } },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="tag-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="tag-readonly"]').text()).toBe('高、低')
    expect(wrapper.findAll('.el-tag')).toHaveLength(0)
  })

  it('编辑态颜色映射（11_03 迁移）', () => {
    const wrapper = mount(TagInputField, {
      props: { modelValue: ['高', '低'], colorMap: { 高: 'danger' } },
      global: { stubs },
    })
    const tags = wrapper.findAll('.el-tag')
    expect(tags).toHaveLength(2)
    expect(tags[0]?.attributes('data-type')).toBe('danger')
    expect(tags[1]?.attributes('data-type')).toBe('info')
  })

  it('分隔符触发创建（中英文逗号）与退格删除末尾（11_03 新增契约）', async () => {
    const wrapper = mount(TagInputField, { props: { ...base }, global: { stubs } })
    const input = wrapper.find('[data-test="tag-input"]')
    await input.setValue('前端')
    await input.trigger('keydown', { key: ',' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['前端']])

    await wrapper.setProps({ modelValue: ['前端', '后端'] })
    await input.setValue('')
    await input.trigger('keydown', { key: 'Backspace' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['前端']])
  })

  it('历史脏值归一（去空白 / 去空串 / 去重）与变化明细（11_03 新增契约）', async () => {
    const wrapper = mount(TagInputField, { props: { modelValue: [' 甲 ', '甲', '', '乙'] }, global: { stubs } })
    await wrapper.vm.$nextTick()
    const input = wrapper.find('[data-test="tag-input"]')
    await input.setValue('丙')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')?.[0]).toEqual([['甲', '乙', '丙'], { direction: 'add', changed: ['丙'] }])
  })

  it('粘贴含中文逗号自动拆分（11_03 新增契约）', async () => {
    const wrapper = mount(TagInputField, { props: { ...base }, global: { stubs } })
    await wrapper.find('[data-test="tag-input"]').trigger('paste', {
      clipboardData: { getData: () => '甲，乙' },
    })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['甲', '乙']])
  })

  it('内容操作暴露：add / remove / clear（11_03 新增契约）', async () => {
    const wrapper = mount(TagInputField, { props: { modelValue: ['甲'] }, global: { stubs } })
    const exposed = wrapper.vm as unknown as { clear: () => void; remove: (tag: string) => void }
    exposed.remove('甲')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[]])
  })

  it('必填校验与外部错误覆盖', async () => {
    const wrapper = mount(TagInputField, { props: { modelValue: [], required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })
})
