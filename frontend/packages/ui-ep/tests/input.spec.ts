/**
 * 输入域口径包装与文本三件（Kiwi 756）——PC / Element Plus 侧。
 *
 * 与 `ui-vant` 侧同名用例同号（双端同号）；跨端不变量见 `contracts-input.spec.ts`，
 * 本文件覆盖 EP 内核细节（元素与属性、计数区、清空）。
 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it, vi } from 'vitest'

import { BaseInput, PasswordField, TextareaField, TextField } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      input: {
        required: '必填项',
        emptyText: '—',
        password: { weak: '弱', medium: '中', strong: '强', show: '显示', hide: '隐藏' },
      },
    },
  },
})
const global = { plugins: [i18n] }

describe('输入域口径包装与文本三件（Kiwi 756）', () => {
  it('BaseInput：字段壳装配（label / 必填 / 帮助 / 错误 / 栅格）', () => {
    const wrapper = mount(BaseInput, {
      props: { modelValue: 'x', label: '名称', required: true, help: '请输入名称', span: 12 },
      global,
    })
    expect(wrapper.find('.bms-input').exists()).toBe(true)
    expect(wrapper.find('.bms-input-label').text()).toContain('名称')
    expect(wrapper.find('.bms-input-required').exists()).toBe(true)
    expect(wrapper.find('.bms-input-help').text()).toContain('请输入名称')
    expect(wrapper.classes()).toContain('is-inline')
    expect((wrapper.attributes('style') ?? '').replace(/\s/g, '')).toContain('--bms-input-span:12')
    expect(wrapper.attributes('data-size')).toBe('default')
  })

  it('BaseInput：只读文本回显 / 空值占位 / 脱敏 / 只读 disabled 模式', () => {
    const masked = mount(BaseInput, {
      props: { modelValue: '13800001111', label: '手机号', readonly: true, mask: true },
      global,
    })
    expect(masked.find('input').exists()).toBe(false)
    expect(masked.find('.bms-input-text').text()).toBe('1*********1')

    const plain = mount(BaseInput, {
      props: { modelValue: '13800001111', readonly: true, mask: true, plain: true },
      global,
    })
    expect(plain.find('.bms-input-text').text()).toBe('13800001111')

    const empty = mount(BaseInput, { props: { modelValue: null, readonly: true }, global })
    expect(empty.find('.bms-input-text').text()).toBe('—')

    const disabled = mount(BaseInput, {
      props: { modelValue: 'x', readonly: true, readonlyMode: 'disabled' },
      slots: { default: '<input class="probe-input" />' },
      global,
    })
    expect(disabled.find('.bms-input-text').exists()).toBe(false)
    expect(disabled.find('.probe-input').exists()).toBe(true)
  })

  it('TextField：单行内核 / 长度属性与计数 / 失焦归一与 change', async () => {
    const wrapper = mount(TextField, {
      props: { modelValue: '', maxlength: 5, showWordLimit: true },
      global,
    })
    const input = wrapper.find('input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('maxlength')).toBe('5')

    await input.setValue('abc')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('abc')
    expect(wrapper.text().replace(/\s/g, '')).toContain('3/5')

    await input.setValue('  x  ')
    await input.trigger('blur')
    expect(wrapper.emitted('change')?.at(-1)?.[0]).toBe('x')

    await input.setValue('   ')
    await input.trigger('blur')
    expect(wrapper.emitted('change')?.at(-1)?.[0]).toBeNull()
  })

  it('TextareaField：多行内核 / rows / 换行统一为 \\n', async () => {
    const wrapper = mount(TextareaField, { props: { modelValue: '', rows: 5 }, global })
    const textarea = wrapper.find('textarea')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('rows')).toBe('5')

    await textarea.setValue('a\r\nb')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('a\nb')
  })

  it('PasswordField：明文切换 / 强度提示 / 不回填 / 不落日志', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    const wrapper = mount(PasswordField, {
      props: { modelValue: '', strength: true, minLength: 8 },
      global,
    })
    const input = wrapper.find('input')
    expect(input.attributes('type')).toBe('password')
    expect(input.attributes('autocomplete')).toBe('new-password')

    await input.setValue('abc')
    expect(wrapper.find('.bms-input-strength--weak').exists()).toBe(true)
    expect(wrapper.text()).toContain('弱')

    await wrapper.find('.bms-input-password-toggle').trigger('click')
    expect(wrapper.find('input').attributes('type')).toBe('text')
    expect(logSpy).not.toHaveBeenCalled()

    await input.trigger('blur')
    expect(wrapper.emitted('validate')?.at(-1)?.[0]).toBe(false)

    logSpy.mockRestore()
  })

  it('BaseInput：禁用写门禁（不外发 update:modelValue）', async () => {
    const wrapper = mount(TextField, { props: { modelValue: '', disabled: true }, global })
    await wrapper.find('input').setValue('blocked')
    expect(wrapper.emitted('update:modelValue') ?? []).toHaveLength(0)
  })
})
