/**
 * 选择三件（Kiwi 758）——PC / Element Plus 侧。
 *
 * 与 `ui-vant` 侧同名用例同号；跨端不变量见 `contracts-input.spec.ts`，
 * 本文件覆盖 EP 内核细节（三形态壳、`el-check-tag`、全选半选、`el-switch` 三态与危险确认）。
 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import { CheckboxField, RadioField, SwitchInput, configureConfirm } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      common: { confirm: '确定' },
      input: {
        required: '必填项',
        emptyText: '—',
        maxCount: '最多可选 {max} 项',
        minCount: '至少选择 {min} 项',
        selectAll: '全选',
        notSet: '未设置',
        switchOn: '是',
        switchOff: '否',
      },
    },
  },
})
const global = { plugins: [i18n] }

const OPTIONS = [
  { value: 'a', label: '数据 A' },
  { value: 'b', label: '数据 B' },
  { value: 'c', label: '数据 C' },
  { value: 'd', label: '数据 D', disabled: true },
]

describe('选择三件（Kiwi 758）', () => {
  it('RadioField：三形态内核渲染与点选', async () => {
    const radio = mount(RadioField, { props: { modelValue: null, options: OPTIONS }, global })
    expect(radio.find('.el-radio-group').exists()).toBe(true)
    expect(radio.findAll('.el-radio').length).toBe(4)
    await radio.findAll('input[type="radio"]')[1]?.setValue()
    await nextTick()
    expect(radio.emitted('update:modelValue')?.at(-1)?.[0]).toBe('b')

    const button = mount(RadioField, {
      props: { modelValue: null, options: OPTIONS, widget: 'button', optionType: 'danger' },
      global,
    })
    expect(button.findAll('.el-radio-button').length).toBe(4)
    expect(button.find('.is-danger').exists()).toBe(true)

    const segmented = mount(RadioField, {
      props: { modelValue: null, options: OPTIONS, widget: 'segmented' },
      global,
    })
    expect(segmented.find('.el-segmented').exists()).toBe(true)
  })

  it('RadioField：只读回显与禁用项', () => {
    const readonly = mount(RadioField, {
      props: { modelValue: 'c', options: OPTIONS, readonly: true },
      global,
    })
    expect(readonly.text()).toContain('数据 C')
    expect(readonly.find('.el-radio-group').exists(), '只读文本态不渲染控件').toBe(false)

    const disabled = mount(RadioField, { props: { modelValue: null, options: OPTIONS }, global })
    expect(disabled.findAll('.el-radio')[3]?.classes()).toContain('is-disabled')
  })

  it('CheckboxField：勾选 / 全选半选 / tag 形态', async () => {
    const checkbox = mount(CheckboxField, {
      props: { modelValue: ['a'], options: OPTIONS, selectAll: true },
      global,
    })
    expect(checkbox.find('.el-checkbox-group').exists()).toBe(true)
    expect(checkbox.find('.el-checkbox__input.is-indeterminate').exists(), '半选态').toBe(true)
    // 全选行为首个 checkbox，选项 A / B / C / D 依次在后
    await checkbox.findAll('input[type="checkbox"]')[2]?.setValue()
    await nextTick()
    expect(checkbox.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['a', 'b'])

    const tag = mount(CheckboxField, {
      props: { modelValue: ['a'], options: OPTIONS, widget: 'tag' },
      global,
    })
    expect(tag.findAll('.el-check-tag').length).toBe(4)
    expect(tag.findAll('.el-check-tag')[0]?.classes()).toContain('is-checked')
    await tag.findAll('.el-check-tag')[1]?.trigger('click')
    await nextTick()
    expect(tag.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['a', 'b'])
  })

  it('CheckboxField：数量上限禁选与下限提示', async () => {
    const limited = mount(CheckboxField, {
      props: { modelValue: ['a'], options: OPTIONS, max: 1 },
      global,
    })
    expect(limited.text(), '上限提示').toContain('最多可选 1 项')
    const limitedVm = limited.vm as unknown as { selectOption?: (value: string) => void }
    limitedVm.selectOption?.('b')
    await nextTick()
    expect(limited.emitted('update:modelValue') ?? []).toHaveLength(0)

    const short = mount(CheckboxField, {
      props: { modelValue: ['a'], options: OPTIONS, min: 2 },
      global,
    })
    const vm = short.vm as unknown as { validate?: () => boolean }
    expect(vm.validate?.()).toBe(false)
    expect(short.emitted('validate')?.at(-1)?.[0]).toBe(false)
  })

  it('SwitchInput：三态 / 清空入口 / 危险确认取消', async () => {
    const unset = mount(SwitchInput, {
      props: { modelValue: null, threeState: true, allowClear: false, readonly: true },
      global,
    })
    expect(unset.text()).toContain('未设置')

    const clearable = mount(SwitchInput, {
      props: { modelValue: true, threeState: true, allowClear: true },
      global,
    })
    expect(clearable.find('.el-switch').exists()).toBe(true)
    await clearable.find('[data-testid="switch-input-clear"]').trigger('click')
    await nextTick()
    expect(clearable.emitted('update:modelValue')?.at(-1)?.[0]).toBeNull()

    configureConfirm(async () => false)
    try {
      const guarded = mount(SwitchInput, {
        props: { modelValue: true, dangerConfirm: '停用后该配置不可用' },
        global,
      })
      const vm = guarded.vm as unknown as { toggle?: () => Promise<void> }
      await vm.toggle?.()
      expect(guarded.emitted('update:modelValue') ?? [], '确认取消不写值').toHaveLength(0)
    } finally {
      configureConfirm(undefined)
    }
  })

  it('SwitchInput：加载态禁止切换 / 布尔归一', async () => {
    const loading = mount(SwitchInput, {
      props: { modelValue: false, loading: true },
      global,
    })
    const vm = loading.vm as unknown as { toggle?: () => Promise<void> }
    await vm.toggle?.()
    expect(loading.emitted('update:modelValue') ?? []).toHaveLength(0)

    const normalized = mount(SwitchInput, {
      props: { modelValue: 1, readonly: true },
      global,
    })
    expect(normalized.text()).toContain('是')
  })
})
