// kiwi_id: 2527
/** 结构化字段属性面板用例（10_02）：空态 / 类型分发 / 规则增删 / 只读。 */

import type { FormField } from '@bms/core'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FieldAttrPanel from '../src/components/form_design/FieldAttrPanel.vue'

/** 文本字段样例。 */
const textField: FormField = { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' }
/** 开关字段样例。 */
const switchField: FormField = { key: 'enabled', label: '启用', type: 'switch', group: 'platform', status: 'active' }
/** 枚举字段样例。 */
const optionField: FormField = { key: 'level', label: '等级', type: 'option', group: 'platform', status: 'active' }

describe('FieldAttrPanel', () => {
  it('未选中字段显示空态', () => {
    const wrapper = mount(FieldAttrPanel)
    expect(wrapper.find('[data-test="attr-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="attr-form"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('选中字段显示名称与键，必填勾选上抛补丁', async () => {
    const wrapper = mount(FieldAttrPanel, { props: { field: textField, attrs: { required: true } } })
    expect(wrapper.find('[data-test="attr-subject"]').text()).toContain('姓名')
    expect(wrapper.find('[data-test="attr-subject"]').text()).toContain('name')
    wrapper.findComponent({ name: 'ElCheckbox' }).vm.$emit('update:modelValue', false)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')?.[0]).toEqual([{ required: false }])
    wrapper.unmount()
  })

  it('提示文案与默认值走文本控件（开关类型走布尔控件）', async () => {
    const wrapper = mount(FieldAttrPanel, { props: { field: textField } })
    wrapper.findAllComponents({ name: 'ElInput' })[0]?.vm.$emit('update:modelValue', '请输入姓名')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')?.[0]).toEqual([{ placeholder: '请输入姓名' }])
    wrapper.findAllComponents({ name: 'ElInput' })[1]?.vm.$emit('update:modelValue', '张三')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')?.[1]).toEqual([{ defaultValue: '张三' }])
    wrapper.unmount()

    const boolWrapper = mount(FieldAttrPanel, { props: { field: switchField, attrs: { defaultValue: true } } })
    expect(boolWrapper.find('[data-test="attr-default-switch"]').exists()).toBe(true)
    boolWrapper.findComponent({ name: 'ElSwitch' }).vm.$emit('update:modelValue', false)
    await boolWrapper.vm.$nextTick()
    expect(boolWrapper.emitted('change')?.[0]).toEqual([{ defaultValue: false }])
    boolWrapper.unmount()
  })

  it('枚举字段提供选项集下拉，非枚举字段不出现', async () => {
    const wrapper = mount(FieldAttrPanel, {
      props: { field: optionField, optionSets: ['bms.demo.level', 'bms.demo.other'], attrs: {} },
    })
    expect(wrapper.find('[data-test="attr-option-set"]').exists()).toBe(true)
    const select = wrapper.findAllComponents({ name: 'ElSelect' })[0]
    select?.vm.$emit('update:modelValue', 'bms.demo.level')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')?.[0]).toEqual([{ optionSetKey: 'bms.demo.level' }])
    select?.vm.$emit('update:modelValue', '')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')?.[1]).toEqual([{ optionSetKey: undefined }])
    wrapper.unmount()

    const textWrapper = mount(FieldAttrPanel, { props: { field: textField } })
    expect(textWrapper.find('[data-test="attr-option-set"]').exists()).toBe(false)
    textWrapper.unmount()
  })

  it('规则为空时给空态，添加长度规则按种类替换', async () => {
    const wrapper = mount(FieldAttrPanel, {
      props: { field: textField, attrs: { rules: [{ kind: 'range', min: 1, max: 9 }] } },
    })
    expect(wrapper.find('[data-test="attr-rule-text"]').text()).toBe('1 ~ 9')

    const numbers = wrapper.findAllComponents({ name: 'ElInputNumber' })
    numbers[0]?.vm.$emit('update:modelValue', 2)
    numbers[1]?.vm.$emit('update:modelValue', 50)
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="attr-rule-add"]').trigger('click')
    expect(wrapper.emitted('change')?.[0]).toEqual([
      { rules: [{ kind: 'range', min: 1, max: 9 }, { kind: 'length', min: 2, max: 50 }] },
    ])

    await wrapper.find('[data-test="attr-rule-add"]').trigger('click')
    waitRules(wrapper, (rules) => expect(rules.filter((rule) => rule.kind === 'length')).toHaveLength(1))
    wrapper.unmount()
  })

  it('正则规则与下限单侧规则按摘要展示', async () => {
    const wrapper = mount(FieldAttrPanel, {
      props: { field: textField, attrs: { rules: [{ kind: 'pattern', pattern: '^\\d+$' }, { kind: 'length', min: 3 }] } },
    })
    const texts = wrapper.findAll('[data-test="attr-rule-text"]').map((node) => node.text())
    expect(texts).toEqual(['^\\d+$', '≥ 3'])

    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'pattern')
    await wrapper.vm.$nextTick()
    const patternInputs = wrapper.findAllComponents({ name: 'ElInput' })
    patternInputs[patternInputs.length - 1]?.vm.$emit('update:modelValue', '^[a-z]+$')
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="attr-rule-add"]').trigger('click')
    expect(wrapper.emitted('change')?.[0]).toEqual([
      { rules: [{ kind: 'length', min: 3 }, { kind: 'pattern', pattern: '^[a-z]+$' }] },
    ])
    wrapper.unmount()
  })

  it('删除规则上抛下标，只读态不动作', async () => {
    const wrapper = mount(FieldAttrPanel, { props: { field: textField, attrs: { rules: [{ kind: 'length', max: 9 }] } } })
    await wrapper.find('[data-test="attr-rule-remove"]').trigger('click')
    expect(wrapper.emitted('remove-rule')?.[0]).toEqual([0])
    wrapper.unmount()

    const locked = mount(FieldAttrPanel, {
      props: { field: textField, disabled: true, attrs: { rules: [{ kind: 'length', max: 9 }] } },
    })
    expect(locked.find('[data-test="attr-readonly"]').exists()).toBe(true)
    await locked.find('[data-test="attr-rule-remove"]').trigger('click')
    expect(locked.emitted('remove-rule')).toBeUndefined()
    locked.findComponent({ name: 'ElCheckbox' }).vm.$emit('update:modelValue', true)
    await locked.vm.$nextTick()
    expect(locked.emitted('change')).toBeUndefined()
    locked.unmount()
  })

  it('只读规则与隐藏开关上抛布尔补丁', async () => {
    const wrapper = mount(FieldAttrPanel, { props: { field: textField, attrs: {} } })
    const boxes = wrapper.findAllComponents({ name: 'ElCheckbox' })
    boxes[1]?.vm.$emit('update:modelValue', true)
    boxes[2]?.vm.$emit('update:modelValue', true)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')).toEqual([[{ readonly: true }], [{ hidden: true }]])
    wrapper.unmount()
  })
})

/**
 * 断言规则清单（从最近一次上抛结果取）。
 *
 * @param wrapper 组件包装器。
 * @param check 断言函数。
 */
function waitRules(
  wrapper: ReturnType<typeof mount>,
  check: (rules: { kind: string }[]) => void,
): void {
  const events = wrapper.emitted('change') ?? []
  const last = events[events.length - 1]?.[0] as { rules?: { kind: string }[] } | undefined
  check(last?.rules ?? [])
}
