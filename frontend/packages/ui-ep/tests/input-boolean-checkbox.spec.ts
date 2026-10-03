// kiwi_id: 2234
/** 单布尔复选框件用例（05_05）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import { BooleanCheckbox } from '../src'

const ElCheckboxStub = defineComponent({
  name: 'ElCheckbox',
  props: {
    modelValue: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    indeterminate: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(props, { emit, slots }) {
    return () =>
      h('label', { class: 'el-checkbox' }, [
        h('input', {
          type: 'checkbox',
          checked: props.modelValue,
          disabled: props.disabled,
          onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
        }),
        slots.default?.(),
      ])
  },
})

const stubs = { ElCheckbox: ElCheckboxStub }

describe('BooleanCheckbox', () => {
  it('受控取值与变更事件（归一为布尔）', async () => {
    const wrapper = mount(BooleanCheckbox, { props: { modelValue: false, label: '记住我' }, global: { stubs } })
    expect(wrapper.text()).toContain('记住我')
    expect((wrapper.find('input').element as HTMLInputElement).checked).toBe(false)

    await wrapper.find('input').setValue(true)
    expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
    expect(wrapper.emitted('change')).toEqual([[true]])
  })

  it('缺省未设置按未勾选渲染；禁用透传', () => {
    const wrapper = mount(BooleanCheckbox, { props: { disabled: true }, global: { stubs } })
    expect((wrapper.find('input').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
  })

  it('根类名与 indeterminate 透传', () => {
    const wrapper = mount(BooleanCheckbox, { props: { modelValue: true, indeterminate: true }, global: { stubs } })
    expect(wrapper.classes()).toContain('bms-boolean-checkbox')
    const box = wrapper.findComponent(ElCheckboxStub)
    expect(box.props('modelValue')).toBe(true)
    expect(box.props('indeterminate')).toBe(true)
  })
})
