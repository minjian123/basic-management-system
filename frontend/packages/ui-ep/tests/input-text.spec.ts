/** 文本类控件用例（05_01_01）。 */

import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it } from 'vitest'

import { NumberInput, PasswordInput, TextareaInput, TextInput, useBaseField, useBaseInput } from '../src'

const ElInputStub = defineComponent({
  name: 'ElInput',
  props: {
    modelValue: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    clearable: { type: Boolean, default: false },
    maxlength: { type: Number, default: undefined },
    showWordLimit: { type: Boolean, default: false },
    type: { type: String, default: 'text' },
    rows: { type: Number, default: 3 },
    autosize: { type: [Boolean, Object], default: false },
    showPassword: { type: Boolean, default: false },
    autocomplete: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'focus', 'blur', 'clear'],
  setup(props, { emit, slots }) {
    return () =>
      h('div', { class: 'el-input', 'data-autocomplete': props.autocomplete }, [
        h('input', {
          value: props.modelValue ?? '',
          disabled: props.disabled,
          readonly: props.readonly,
          onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
        }),
        h('button', { 'data-test': 'clear', onClick: () => emit('clear') }),
        slots.prefix?.(),
        slots.suffix?.(),
      ])
  },
})

const ElInputNumberStub = defineComponent({
  name: 'ElInputNumber',
  props: {
    modelValue: { type: Number, default: undefined },
    disabled: { type: Boolean, default: false },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    min: { type: Number, default: undefined },
    max: { type: Number, default: undefined },
    step: { type: Number, default: 1 },
    precision: { type: Number, default: undefined },
    formatter: { type: Function, default: undefined },
    parser: { type: Function, default: undefined },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('div', { class: 'el-input-number' }, [
        h('button', { 'data-test': 'inc', onClick: () => emit('update:modelValue', (Number(props.modelValue ?? 0) + 1)) }, '+'),
        h('span', { 'data-test': 'display' }, String(typeof props.formatter === 'function' ? props.formatter(props.modelValue) : props.modelValue ?? '')),
      ])
  },
})

const stubs = { ElInput: ElInputStub, ElInputNumber: ElInputNumberStub }

describe('useBaseInput', () => {
  it('受控值 / 三态 / 禁用合并 / 同值短路', () => {
    const base = useBaseInput<string>({ value: 'a', disabled: true })
    expect(base.value.value).toBe('a')
    expect(base.isEmpty.value).toBe(false)
    expect(base.disabled.value).toBe(true)

    const seen: (string | undefined)[] = []
    base.onValueChange((next) => seen.push(next))
    base.setValue('b')
    base.setValue('b')
    expect(seen).toEqual(['b'])

    base.setValue(undefined)
    expect(base.isEmpty.value).toBe(true)

    base.setDisabled(false)
    expect(base.disabled.value).toBe(true) // 基类 disabled 仍为真 → 合并为真

    const clearable = useBaseInput<string>({ value: 'x' })
    clearable.clear()
    expect(clearable.value.value).toBe('x') // 不可清空 → 无操作
  })
})

describe('useBaseField', () => {
  it('字段标识与校验触发', () => {
    const field = useBaseField<string>({ fieldName: 'name', trigger: 'blur' })
    expect(field.fieldName.value).toBe('name')
    expect(field.trigger.value).toBe('blur')
    field.setTrigger('submit')
    expect(field.trigger.value).toBe('submit')
  })
})

describe('TextInput', () => {
  it('输入派发 update:modelValue 与 change（同值不重复）', async () => {
    const wrapper = mount(TextInput, { props: { modelValue: '' }, global: { stubs } })
    await wrapper.find('input').setValue('abc')
    expect(wrapper.emitted('update:modelValue')).toEqual([['abc']])
    expect(wrapper.emitted('change')).toEqual([['abc']])

    await wrapper.find('input').setValue('abc')
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
  })

  it('清空仅可清空时生效并派发 clear', async () => {
    const wrapper = mount(TextInput, { props: { modelValue: 'a', clearable: true }, global: { stubs } })
    await wrapper.find('[data-test="clear"]').trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
  })

  it('禁用合并传给 el-input', () => {
    const wrapper = mount(TextInput, { props: { modelValue: '', disabled: true }, global: { stubs } })
    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
  })
})

describe('TextareaInput', () => {
  it('透传 rows 与 autosize', () => {
    const wrapper = mount(TextareaInput, {
      props: { modelValue: '', rows: 5, autosize: { minRows: 2, maxRows: 6 } },
      global: { stubs },
    })
    const input = wrapper.findComponent(ElInputStub)
    expect(input.props('rows')).toBe(5)
    expect(input.props('autosize')).toEqual({ minRows: 2, maxRows: 6 })
  })
})

describe('PasswordInput', () => {
  it('明文切换与不回填属性，强度随值变化', async () => {
    const wrapper = mount(PasswordInput, { props: { modelValue: '' }, global: { stubs } })
    const input = wrapper.findComponent(ElInputStub)
    expect(input.props('showPassword')).toBe(true)
    expect(input.attributes('data-autocomplete')).toBe('new-password')
    expect(wrapper.find('[data-test="password-strength"]').attributes('data-strength')).toBe('weak')

    await wrapper.setProps({ modelValue: 'Abcdef123456@x' })
    expect(wrapper.find('[data-test="password-strength"]').attributes('data-strength')).toBe('strong')
  })
})

describe('NumberInput', () => {
  it('值变更派发并支持千分位格式化', async () => {
    const wrapper = mount(NumberInput, { props: { modelValue: 1000, thousandSeparator: true }, global: { stubs } })
    expect(wrapper.find('[data-test="display"]').text()).toBe('1,000')
    await wrapper.find('[data-test="inc"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([1001])
    expect(wrapper.emitted('change')?.[0]).toEqual([1001])
  })

  it('透传范围与精度', () => {
    const wrapper = mount(NumberInput, { props: { modelValue: 1, min: 0, max: 10, step: 2, precision: 1 }, global: { stubs } })
    const input = wrapper.findComponent(ElInputNumberStub)
    expect([input.props('min'), input.props('max'), input.props('step'), input.props('precision')]).toEqual([0, 10, 2, 1])
  })
})
