// kiwi_id: 969
/** 开关与枚举字段用例（06_02_03）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { EnumField, EnumMultiField, InlineSwitchCell, SwitchField, TriStateSwitch, useConfirm } from '../src'

const ElSwitchStub = defineComponent({
  name: 'ElSwitch',
  props: {
    modelValue: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    activeText: { type: String, default: '' },
    inactiveText: { type: String, default: '' },
    indeterminate: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-switch" :data-indeterminate="indeterminate"><button data-test="switch" @click="$emit(\'update:modelValue\', !modelValue)" /></div>',
})

const ElSelectStub = defineComponent({
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    collapseTags: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    options: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue', 'clear'],
  template: '<div class="el-select"><slot /><button data-test="pick-b" @click="$emit(\'update:modelValue\', \'b\')" /><slot name="empty" /></div>',
})

const ElOptionStub = defineComponent({
  name: 'ElOption',
  props: { label: { type: String, default: '' }, value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<div class="el-option">{{ label }}</div>',
})

const ElOptionGroupStub = defineComponent({
  name: 'ElOptionGroup',
  props: { label: { type: String, default: '' } },
  template: '<div class="el-option-group">{{ label }}<slot /></div>',
})

const ElRadioGroupStub = defineComponent({
  name: 'ElRadioGroup',
  props: { modelValue: { type: [String, Number], default: undefined }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<div class="el-radio-group"><slot /></div>',
})

const ElRadioStub = defineComponent({
  name: 'ElRadio',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-radio"><slot /></label>',
})

const ElRadioButtonStub = defineComponent({
  name: 'ElRadioButton',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-radio-button"><slot /></label>',
})

const ElSegmentedStub = defineComponent({
  name: 'ElSegmented',
  props: { modelValue: { type: [String, Number], default: undefined }, options: { type: Array, default: () => [] } },
  emits: ['update:modelValue'],
  template: '<div class="el-segmented"><slot /></div>',
})

const stubs = {
  ElSwitch: ElSwitchStub,
  ElSegmented: ElSegmentedStub,
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
  ElOptionGroup: ElOptionGroupStub,
  ElRadioGroup: ElRadioGroupStub,
  ElRadio: ElRadioStub,
  ElRadioButton: ElRadioButtonStub,
}

describe('SwitchField', () => {
  it('三态与必填校验', async () => {
    const wrapper = mount(SwitchField, { props: { modelValue: undefined, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('data-set')).toBe('false')
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('外部错误覆盖与确认取消不改值', async () => {
    const confirm = useConfirm()
    const wrapper = mount(SwitchField, { props: { modelValue: false, confirm: '确认切换？' }, global: { stubs } })
    const pending = wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })

  it('切换前置判定不通过则撤销（11_03 新增契约）', async () => {
    const beforeChange = vi.fn().mockReturnValue(false)
    const wrapper = mount(SwitchField, { props: { modelValue: false, beforeChange }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(beforeChange).toHaveBeenCalledWith(true)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('三态清空入口与尺寸档位（11_03 新增契约）', async () => {
    const wrapper = mount(SwitchField, { props: { modelValue: true, clearable: true, size: 'compact' }, global: { stubs } })
    expect(wrapper.attributes('data-size')).toBe('compact')
    await wrapper.find('[data-test="switch-clear"]').trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })

  it('只读回显（是 / 否 / 未设置占位，11_03 新增契约）', () => {
    const on = mount(SwitchField, { props: { modelValue: true, readonly: true }, global: { stubs } })
    expect(on.find('[data-test="switch-readonly"]').text()).toBe('是')

    const off = mount(SwitchField, { props: { modelValue: false, readonly: true }, global: { stubs } })
    expect(off.find('[data-test="switch-readonly"]').text()).toBe('否')

    const unset = mount(SwitchField, { props: { modelValue: undefined, readonly: true }, global: { stubs } })
    expect(unset.find('[data-test="switch-readonly"]').text()).toBe('—')
  })
})

describe('InlineSwitchCell', () => {
  it('保存成功写值并派发 saved', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(save).toHaveBeenCalledWith(true)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
    expect(wrapper.emitted('saved')?.[0]).toEqual([true])
  })

  it('保存失败回滚原值并发 invalid', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['保存失败，已回滚'])
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('保存失败，已回滚')
  })

  it('乐观值：保存期间即按目标态展示（11_03 新增契约）', async () => {
    let release: () => void = () => {}
    const save = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          release = resolve
        }),
    )
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    // 保存未完成即展示目标态（乐观）
    expect(wrapper.find('[data-test="tri-state-switch"]').attributes('aria-checked')).toBe('true')
    release()
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('saved')?.[0]).toEqual([true])
  })

  it('版本冲突提示并派发 refresh（11_03 新增契约）', async () => {
    const save = vi.fn().mockRejectedValue(new Error('409 conflict'))
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('数据已被他人修改')
  })

  it('危险开关二次确认取消不改值（11_03 新增契约）', async () => {
    const confirm = useConfirm()
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save, confirm: '确认切换？' }, global: { stubs } })
    const pending = wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('TriStateSwitch', () => {
  it('三态：未设置 / 开 / 关（aria-checked mixed，11_03 新增件）', async () => {
    const wrapper = mount(TriStateSwitch, { props: { modelValue: undefined } })
    const control = wrapper.find('[data-test="tri-state-switch"]')
    expect(control.attributes('aria-checked')).toBe('mixed')
    expect(wrapper.attributes('data-state')).toBe('unset')

    await control.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])

    await wrapper.setProps({ modelValue: false })
    expect(wrapper.attributes('data-state')).toBe('off')
    expect(wrapper.find('[data-test="tri-state-switch"]').attributes('aria-checked')).toBe('false')
  })

  it('键盘 Enter / Space 触发与禁用不响应', async () => {
    const wrapper = mount(TriStateSwitch, { props: { modelValue: false } })
    const control = wrapper.find('[data-test="tri-state-switch"]')
    await control.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])

    const disabled = mount(TriStateSwitch, { props: { modelValue: false, disabled: true } })
    await disabled.find('[data-test="tri-state-switch"]').trigger('click')
    expect(disabled.emitted('update:modelValue')).toBeUndefined()
  })

  it('尺寸档位与文案变体', () => {
    const wrapper = mount(TriStateSwitch, {
      props: { modelValue: true, size: 'compact', activeText: '启用', inactiveText: '停用' },
    })
    expect(wrapper.attributes('data-size')).toBe('compact')
    expect(wrapper.text()).toContain('启用')
  })
})

describe('EnumMultiField', () => {
  const multiOptions = [
    { label: '高', value: 'high', sort: 1 },
    { label: '中', value: 'mid', sort: 2 },
    { label: '低', value: 'low', sort: 3 },
  ]

  it('多选受控与去重保序（按选项集顺序输出）', async () => {
    const wrapper = mount(EnumMultiField, { props: { modelValue: ['low', 'high', 'low'], options: multiOptions }, global: { stubs } })
    const control = wrapper.findComponent({ name: 'CheckboxInput' })
    expect(control.props('modelValue')).toEqual(['high', 'low'])
    expect(control.props('form')).toBe('checkbox')
  })

  it('tag 形态与数量上下限 exceed 事件', async () => {
    const tag = mount(EnumMultiField, { props: { modelValue: [], options: multiOptions, form: 'tag' }, global: { stubs } })
    expect(tag.findComponent({ name: 'CheckboxInput' }).props('form')).toBe('tag')

    const limited = mount(EnumMultiField, {
      props: { modelValue: [], options: multiOptions, maxItems: 1 },
      global: { stubs },
    })
    const checkbox = limited.findComponent({ name: 'CheckboxInput' })
    checkbox.vm.$emit('update:modelValue', ['high', 'mid'])
    await limited.vm.$nextTick()
    expect(limited.emitted('exceed')?.[0]).toEqual([['high', 'mid']])
    expect(limited.emitted('update:modelValue')).toBeUndefined()
  })

  it('只读顿号回显与必填校验', async () => {
    const wrapper = mount(EnumMultiField, {
      props: { modelValue: ['high', 'low'], options: multiOptions, readonly: true },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="enum-multi-readonly"]').text()).toBe('高、低')

    const empty = mount(EnumMultiField, { props: { modelValue: [], options: multiOptions, readonly: true }, global: { stubs } })
    expect(empty.find('[data-test="enum-multi-readonly"]').text()).toBe('—')

    const required = mount(EnumMultiField, { props: { modelValue: [], options: multiOptions, required: true }, global: { stubs } })
    await required.vm.$nextTick()
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')
  })
})

describe('EnumField', () => {
  const options = [
    { label: '甲', value: 'a' },
    { label: '乙', value: 'b' },
  ]

  it('下拉默认形态与值回传', async () => {
    const wrapper = mount(EnumField, { props: { modelValue: 'a', options }, global: { stubs } })
    expect(wrapper.findAll('.el-option')).toHaveLength(2)
    await wrapper.find('[data-test="pick-b"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['b'])
  })

  it('单选形态与选项集校验', async () => {
    const radio = mount(EnumField, { props: { modelValue: 'a', options, form: 'button' }, global: { stubs } })
    expect(radio.findAll('.el-radio-button')).toHaveLength(2)

    const invalid = mount(EnumField, { props: { modelValue: 'z' as never, options }, global: { stubs } })
    await invalid.vm.$nextTick()
    expect(invalid.find('[data-test="field-error"]').text()).toBe('选项不在选项集中')
  })

  it('segmented 形态与选项集解析（sort 升序 + value 去重；11_03 新增契约）', () => {
    const segmented = mount(EnumField, { props: { modelValue: 'a', options, form: 'segmented' }, global: { stubs } })
    expect(segmented.findComponent(ElSegmentedStub).exists()).toBe(true)

    const unsorted = mount(EnumField, {
      props: {
        modelValue: undefined,
        options: [
          { label: '丙', value: 'c', sort: 3 },
          { label: '甲', value: 'a', sort: 1 },
          { label: '甲重复', value: 'a', sort: 2 },
          { label: '乙', value: 'b', sort: 2 },
        ],
      },
      global: { stubs },
    })
    // `SelectInput` 以 `el-option` 子件渲染选项：断言解析后的顺序与去重结果。
    const labels = unsorted.findAll('.el-option').map((item) => item.text())
    expect(labels).toEqual(['甲', '乙', '丙'])
  })

  it('只读回显与默认值（11_03 新增契约）', () => {
    const wrapper = mount(EnumField, { props: { modelValue: 'b', options, readonly: true }, global: { stubs } })
    expect(wrapper.find('[data-test="enum-readonly"]').text()).toBe('乙')

    const missing = mount(EnumField, { props: { modelValue: 'ghost' as never, options, readonly: true }, global: { stubs } })
    expect(missing.find('[data-test="enum-readonly"]').text()).toBe('ghost')

    const empty = mount(EnumField, { props: { modelValue: undefined, options, readonly: true }, global: { stubs } })
    expect(empty.find('[data-test="enum-readonly"]').text()).toBe('—')

    const withDefault = mount(EnumField, { props: { modelValue: undefined, options, defaultValue: 'a' }, global: { stubs } })
    expect(withDefault.findComponent(ElSelectStub).props('modelValue')).toBe('a')
  })

  it('必填与空选项降级', async () => {
    const wrapper = mount(EnumField, { props: { modelValue: undefined, options, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const empty = mount(EnumField, { props: { modelValue: undefined, options: [] }, global: { stubs } })
    expect(empty.attributes('data-empty')).toBe('true')
    expect(empty.findComponent(ElSelectStub).props('disabled')).toBe(true)
  })
})
