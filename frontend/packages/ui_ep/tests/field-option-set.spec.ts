// kiwi_id: 2337
/** 选项集字段用例（06_10）：六形态 / 解析去重 / i18n 回退 / 禁用项 / 缺项回退 / 数量上下限 / 空态降级。 */

import type { OptionSetSnapshot } from '@bms/core'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  OPTION_SET_RESOLVER,
  OptionSetField,
  OptionSetMultiField,
  createOptionSetResolver,
  setOptionSetDevMode,
} from '../src'

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
  },
  emits: ['update:modelValue', 'clear'],
  template:
    '<div class="el-select" :data-multiple="multiple"><slot /><button data-test="select-mid" @click="$emit(\'update:modelValue\', \'mid\')" /><button data-test="select-array" @click="$emit(\'update:modelValue\', [\'mid\'])" /><button data-test="select-single" @click="$emit(\'update:modelValue\', \'high\')" /><button data-test="select-null" @click="$emit(\'update:modelValue\', null)" /><button data-test="select-undef" @click="$emit(\'update:modelValue\', undefined)" /><button data-test="select-multi" @click="$emit(\'update:modelValue\', [\'high\', \'low\'])" /><slot name="empty" /></div>',
})

const ElOptionStub = defineComponent({
  name: 'ElOption',
  props: {
    label: { type: String, default: '' },
    value: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
  },
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
  template: '<label class="el-radio" :data-disabled="disabled">{{ value }}<slot /></label>',
})

const ElRadioButtonStub = defineComponent({
  name: 'ElRadioButton',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-radio-button" :data-disabled="disabled">{{ value }}<slot /></label>',
})

const ElSegmentedStub = defineComponent({
  name: 'ElSegmented',
  props: { modelValue: { type: [String, Number], default: undefined }, options: { type: Array, default: () => [] } },
  emits: ['update:modelValue'],
  template: '<div class="el-segmented"><slot /></div>',
})

const stubs = {
  ElSegmented: ElSegmentedStub,
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
  ElOptionGroup: ElOptionGroupStub,
  ElRadioGroup: ElRadioGroupStub,
  ElRadio: ElRadioStub,
  ElRadioButton: ElRadioButtonStub,
}

/** 优先级别选项集（乱序 + 重复值 + 禁用项）。 */
const PRIORITY: OptionSetSnapshot = {
  optionSetKey: 'bms.demo.priority',
  items: [
    { value: 'high', label: '高', sort: 1, color: 'danger' },
    { value: 'mid', label: '中', sort: 3 },
    { value: 'low', label: '低', sort: 2, disabled: true },
    { value: 'mid', label: '中（重复）', sort: 4 },
  ],
}

/** i18n 选项集（labelKey 命中 / 未命中 / 空 label 回退 value）。 */
const I18N: OptionSetSnapshot = {
  optionSetKey: 'bms.demo.i18n',
  items: [
    { value: 'a', label: '甲', labelKey: 'opt.a', sort: 2 },
    { value: 'b', label: '', labelKey: 'opt.b', sort: 1 },
  ],
}

/** 解析器装配（模拟渲染器 provide）。 */
function provideOf(): Record<symbol, unknown> {
  return { [OPTION_SET_RESOLVER]: createOptionSetResolver(() => [PRIORITY, I18N]) }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe('OptionSetField（单选四形态）', () => {
  it('radio 默认形态：按 sort 升序、同值去重保留首个、禁用项保留', () => {
    const wrapper = mount(OptionSetField, {
      props: { modelValue: 'mid', optionSetKey: 'bms.demo.priority' },
      global: { stubs, provide: provideOf() },
    })
    expect(wrapper.attributes('data-form')).toBe('radio')
    expect(wrapper.attributes('data-empty')).toBe('false')
    const labels = wrapper.findAll('.el-radio').map((item) => item.text())
    // 顺序：高（sort 1）→ 低（sort 2）→ 中（sort 3；重复项丢弃）
    expect(labels).toEqual(['high高', 'low低', 'mid中'])
    expect(wrapper.findAll('.el-radio')[1]?.attributes('data-disabled')).toBe('true')
  })

  it('button / segmented 形态', () => {
    const button = mount(OptionSetField, {
      props: { modelValue: 'mid', optionSetKey: 'bms.demo.priority', form: 'button' },
      global: { stubs, provide: provideOf() },
    })
    expect(button.findAll('.el-radio-button')).toHaveLength(3)

    const segmented = mount(OptionSetField, {
      props: { modelValue: 'mid', optionSetKey: 'bms.demo.priority', form: 'segmented' },
      global: { stubs, provide: provideOf() },
    })
    expect(segmented.findComponent(ElSegmentedStub).exists()).toBe(true)
  })

  it('dropdown 形态：选项由注入解析（控件无取数）、值回传', async () => {
    const wrapper = mount(OptionSetField, {
      props: { modelValue: 'high', optionSetKey: 'bms.demo.priority', form: 'dropdown' },
      global: { stubs, provide: provideOf() },
    })
    const select = wrapper.findComponent(ElSelectStub)
    expect(select.exists()).toBe(true)
    expect(select.props('filterable')).toBe(true)
    expect(select.props('clearable')).toBe(true)
    expect(wrapper.findAll('.el-option')).toHaveLength(3)
    await wrapper.find('[data-test="select-mid"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['mid'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['mid'])

    // 下拉件宽类型回传（数组取首值）。
    await wrapper.find('[data-test="select-array"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['mid'])
  })

  it('校验：必填 / 值不在选项集 / 外部文案优先；默认值预填', async () => {
    const required = mount(OptionSetField, {
      props: { modelValue: undefined, optionSetKey: 'bms.demo.priority', required: true },
      global: { stubs, provide: provideOf() },
    })
    await required.vm.$nextTick()
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const invalid = mount(OptionSetField, {
      props: { modelValue: 'ghost', optionSetKey: 'bms.demo.priority' },
      global: { stubs, provide: provideOf() },
    })
    await invalid.vm.$nextTick()
    expect(invalid.find('[data-test="field-error"]').text()).toBe('选项不在选项集中')
    expect(invalid.attributes('data-missing')).toBe('true')

    const external = mount(OptionSetField, {
      props: { modelValue: 'ghost', optionSetKey: 'bms.demo.priority', errorMessage: '服务端校验失败' },
      global: { stubs, provide: provideOf() },
    })
    expect(external.find('[data-test="field-error"]').text()).toBe('服务端校验失败')

    const unset = mount(OptionSetField, {
      props: { modelValue: undefined, optionSetKey: 'bms.demo.priority' },
      global: { stubs, provide: provideOf() },
    })
    expect(unset.find('[data-test="field-error"]').exists()).toBe(false)

    const withDefault = mount(OptionSetField, {
      props: { modelValue: undefined, optionSetKey: 'bms.demo.priority', defaultValue: 'low' },
      global: { stubs, provide: provideOf() },
    })
    expect(withDefault.findComponent(ElRadioGroupStub).props('modelValue')).toBe('low')
  })

  it('只读回显：label / 缺项回退原值 + 开发态告警 / 未设置占位', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mount(OptionSetField, {
      props: { modelValue: 'low', optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(wrapper.find('[data-test="option-set-readonly"]').text()).toBe('低')

    const missing = mount(OptionSetField, {
      props: { modelValue: 'ghost', optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(missing.find('[data-test="option-set-readonly"]').text()).toBe('ghost')
    expect(missing.attributes('data-missing')).toBe('true')
    // 只读态不校验（存量脏值回退原值，不报错）。
    expect(missing.find('[data-test="field-error"]').exists()).toBe(false)
    expect(warn).toHaveBeenCalled()

    const empty = mount(OptionSetField, {
      props: { modelValue: undefined, optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(empty.find('[data-test="option-set-readonly"]').text()).toBe('—')
  })

  it('缺项告警仅开发态（生产静默）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    setOptionSetDevMode(false)
    try {
      const wrapper = mount(OptionSetField, {
        props: { modelValue: 'ghost', optionSetKey: 'bms.demo.priority' },
        global: { stubs, provide: provideOf() },
      })
      // 生产静默但标记仍在（可断言、不阻断）。
      expect(wrapper.attributes('data-missing')).toBe('true')
      expect(warn.mock.calls).toEqual([])
    } finally {
      setOptionSetDevMode(true)
    }
  })

  it('i18n：labelKey 命中翻译、未命中回退 label、空 label 回退 value', () => {
    const wrapper = mount(OptionSetField, {
      props: {
        modelValue: 'a',
        optionSetKey: 'bms.demo.i18n',
        form: 'dropdown',
        translate: (labelKey: string) => (labelKey === 'opt.a' ? '甲（译）' : undefined),
      },
      global: { stubs, provide: provideOf() },
    })
    expect(wrapper.findAll('.el-option').map((item) => item.text())).toEqual(['b', '甲（译）'])
  })

  it('空态降级：缺 key / 未登记标识 / 未注入解析器 → 禁用 + 占位，且不报错', () => {
    const noKey = mount(OptionSetField, {
      props: { modelValue: undefined, form: 'dropdown' },
      global: { stubs, provide: provideOf() },
    })
    expect(noKey.attributes('data-empty')).toBe('true')
    expect(noKey.findComponent(ElSelectStub).props('disabled')).toBe(true)
    expect(noKey.findComponent(ElSelectStub).props('placeholder')).toBe('暂无可选枚举')

    const absent = mount(OptionSetField, {
      props: { modelValue: 'ghost', optionSetKey: 'bms.demo.absent', form: 'dropdown' },
      global: { stubs, provide: provideOf() },
    })
    expect(absent.attributes('data-empty')).toBe('true')
    expect(absent.attributes('data-missing')).toBeUndefined()
    expect(absent.find('[data-test="field-error"]').exists()).toBe(false)

    const noResolver = mount(OptionSetField, {
      props: { modelValue: 'ghost', optionSetKey: 'bms.demo.priority' },
      global: { stubs },
    })
    expect(noResolver.attributes('data-empty')).toBe('true')
    expect(noResolver.findComponent(ElRadioGroupStub).props('disabled')).toBe(true)
  })
})

describe('OptionSetMultiField（多选三形态）', () => {
  it('checkbox 形态：受控去重保序（按选项集顺序输出）', () => {
    const wrapper = mount(OptionSetMultiField, {
      props: { modelValue: ['low', 'high', 'low'], optionSetKey: 'bms.demo.priority' },
      global: { stubs, provide: provideOf() },
    })
    const control = wrapper.findComponent({ name: 'CheckboxInput' })
    expect(wrapper.attributes('data-form')).toBe('checkbox')
    expect(control.props('modelValue')).toEqual(['high', 'low'])
    expect(control.props('form')).toBe('checkbox')
  })

  it('tag 形态与 dropdown-multi 形态（下拉多选注入 + 值回传）', async () => {
    const tag = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority', form: 'tag' },
      global: { stubs, provide: provideOf() },
    })
    expect(tag.findComponent({ name: 'CheckboxInput' }).props('form')).toBe('tag')

    const dropdown = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority', form: 'dropdown-multi' },
      global: { stubs, provide: provideOf() },
    })
    const select = dropdown.findComponent(ElSelectStub)
    expect(select.props('multiple')).toBe(true)
    expect(select.props('modelValue')).toEqual(['high'])
    await dropdown.find('[data-test="select-multi"]').trigger('click')
    expect(dropdown.emitted('update:modelValue')?.[0]).toEqual([['high', 'low']])

    // 下拉清空回传 `null` / `undefined` 归一为空数组；单值回传归一为单元素数组。
    await dropdown.find('[data-test="select-null"]').trigger('click')
    expect(dropdown.emitted('update:modelValue')?.at(-1)).toEqual([[]])
    await dropdown.find('[data-test="select-undef"]').trigger('click')
    expect(dropdown.emitted('update:modelValue')?.at(-1)).toEqual([[]])
    await dropdown.find('[data-test="select-single"]').trigger('click')
    expect(dropdown.emitted('update:modelValue')?.at(-1)).toEqual([['high']])
  })

  it('数量上下限：越限派发 exceed 且回退原值', async () => {
    const maxLimited = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority', maxItems: 1 },
      global: { stubs, provide: provideOf() },
    })
    maxLimited.findComponent({ name: 'CheckboxInput' }).vm.$emit('update:modelValue', ['high', 'low'])
    await maxLimited.vm.$nextTick()
    expect(maxLimited.emitted('exceed')?.[0]).toEqual([['high', 'low']])
    expect(maxLimited.emitted('update:modelValue')).toBeUndefined()

    const minLimited = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority', minItems: 2 },
      global: { stubs, provide: provideOf() },
    })
    await minLimited.vm.$nextTick()
    expect(minLimited.find('[data-test="field-error"]').text()).toBe('至少选择 2 项')
    minLimited.findComponent({ name: 'CheckboxInput' }).vm.$emit('update:modelValue', ['high'])
    await minLimited.vm.$nextTick()
    expect(minLimited.emitted('exceed')?.[0]).toEqual([['high']])
    expect(minLimited.find('[data-test="field-error"]').text()).toBe('至少选择 2 项')

    // 存量值超出上限（外部数据 / 配置调整）时内联提示，不阻断回显。
    const overMax = mount(OptionSetMultiField, {
      props: { modelValue: ['high', 'low'], optionSetKey: 'bms.demo.priority', maxItems: 1 },
      global: { stubs, provide: provideOf() },
    })
    await overMax.vm.$nextTick()
    expect(overMax.find('[data-test="field-error"]').text()).toBe('最多选择 1 项')
  })

  it('受控值变化：长度不同 / 同长不同值 / 完全一致 / 未设置均按选项集顺序归一', async () => {
    const wrapper = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority' },
      global: { stubs, provide: provideOf() },
    })
    const control = () => wrapper.findComponent({ name: 'CheckboxInput' })
    await wrapper.setProps({ modelValue: ['high', 'low'] })
    expect(control().props('modelValue')).toEqual(['high', 'low'])
    await wrapper.setProps({ modelValue: ['low'] })
    expect(control().props('modelValue')).toEqual(['low'])
    await wrapper.setProps({ modelValue: ['low'] })
    expect(control().props('modelValue')).toEqual(['low'])
    await wrapper.setProps({ modelValue: undefined })
    expect(control().props('modelValue')).toEqual([])
  })

  it('缺项告警仅开发态（生产静默）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    setOptionSetDevMode(false)
    try {
      const wrapper = mount(OptionSetMultiField, {
        props: { modelValue: ['ghost'], optionSetKey: 'bms.demo.priority' },
        global: { stubs, provide: provideOf() },
      })
      expect(wrapper.attributes('data-missing')).toBe('true')
      expect(warn.mock.calls).toEqual([])
    } finally {
      setOptionSetDevMode(true)
    }
  })

  it('只读顿号回显、缺项回退原值、必填与空态', () => {
    const wrapper = mount(OptionSetMultiField, {
      props: { modelValue: ['low', 'high'], optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(wrapper.find('[data-test="option-set-multi-readonly"]').text()).toBe('高、低')

    const missing = mount(OptionSetMultiField, {
      props: { modelValue: ['ghost', 'phantom', 'high'], optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(missing.find('[data-test="option-set-multi-readonly"]').text()).toBe('高、ghost、phantom')
    expect(missing.attributes('data-missing')).toBe('true')
    expect(missing.find('[data-test="field-error"]').exists()).toBe(false)

    const emptyReadonly = mount(OptionSetMultiField, {
      props: { modelValue: [], optionSetKey: 'bms.demo.priority', readonly: true },
      global: { stubs, provide: provideOf() },
    })
    expect(emptyReadonly.find('[data-test="option-set-multi-readonly"]').text()).toBe('—')

    const required = mount(OptionSetMultiField, {
      props: { modelValue: [], optionSetKey: 'bms.demo.priority', required: true },
      global: { stubs, provide: provideOf() },
    })
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const empty = mount(OptionSetMultiField, {
      props: { modelValue: [], optionSetKey: 'bms.demo.absent' },
      global: { stubs, provide: provideOf() },
    })
    expect(empty.attributes('data-empty')).toBe('true')
    expect(empty.findComponent({ name: 'CheckboxInput' }).props('disabled')).toBe(true)
    expect(empty.find('[data-test="field-error"]').exists()).toBe(false)

    // 下拉形态空态：占位提示无可选枚举且禁用。
    const emptyDropdown = mount(OptionSetMultiField, {
      props: { modelValue: [], optionSetKey: 'bms.demo.absent', form: 'dropdown-multi' },
      global: { stubs, provide: provideOf() },
    })
    expect(emptyDropdown.findComponent(ElSelectStub).props('placeholder')).toBe('暂无可选枚举')
    expect(emptyDropdown.findComponent(ElSelectStub).props('disabled')).toBe(true)

    // 外部错误文案优先。
    const external = mount(OptionSetMultiField, {
      props: { modelValue: ['high'], optionSetKey: 'bms.demo.priority', errorMessage: '服务端校验失败' },
      global: { stubs, provide: provideOf() },
    })
    expect(external.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })
})
