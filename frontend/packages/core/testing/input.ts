/**
 * 输入控件契约用例工厂（框架无关）：基础控件类文本三件的跨实现不变量。
 *
 * `ui-ep`（Element Plus）与 `ui-vant`（Vant）跑同一套断言；细粒度行为（内核属性、
 * `rows` 透传等）仍保留在各插件自有 spec。
 *
 * 断言面：类名钩子与字段壳、受控写入与事件、长度与计数、失焦归一（trim / 空值）、
 * 多行与换行、密码掩码与明文切换、密码强度与最小长度、只读两种呈现、禁用写门禁、栅格变量。
 */

import { describe, expect, it, vi } from 'vitest'

import type { ComponentContractKit, ComponentViewHandle } from './components'

const INPUT_SLUGS: readonly (readonly [string, string])[] = [
  ['TextField', 'bms-text-field'],
  ['TextareaField', 'bms-textarea-field'],
  ['PasswordField', 'bms-password-field'],
]

function requireSetValue(view: ComponentViewHandle): (selector: string, value: string) => Promise<void> {
  if (!view.setValue) {
    throw new Error('契约套件：当前实现未提供 setValue 适配（输入控件契约需要）')
  }
  return view.setValue.bind(view)
}

function lastEmitted(view: ComponentViewHandle, event: string): unknown {
  const events = view.emitted(event)
  return events.length > 0 ? events[events.length - 1]?.[0] : undefined
}

export function describeInputControlsContract(kit: ComponentContractKit): void {
  describe('输入控件契约（同一套断言）', () => {
    it('三件共同不变量：根类名钩子 + 字段壳 + 标签', () => {
      for (const [name, slug] of INPUT_SLUGS) {
        const view = kit.mount(name, { props: { modelValue: null, label: '标题' } })
        expect(view.has(`.${slug}`), `${name} 根类名钩子`).toBe(true)
        expect(view.has('.bms-input'), `${name} 字段壳`).toBe(true)
        expect(view.has('.bms-input-label'), `${name} 标签元素`).toBe(true)
        expect(view.text()).toContain('标题')
        view.unmount()
      }
    })

    it('TextField：受控写入 / 长度计数 / 失焦归一（trim 与空值）', async () => {
      const view = kit.mount('TextField', {
        props: { modelValue: null, maxlength: 5, showWordLimit: true },
      })
      const setValue = requireSetValue(view)

      await setValue('input', 'abc')
      expect(lastEmitted(view, 'update:modelValue')).toBe('abc')
      expect(view.text().replace(/\s/g, '')).toContain('3/5')

      await setValue('input', '  x  ')
      await view.trigger('input', 'blur')
      expect(lastEmitted(view, 'change'), '失焦 trim').toBe('x')

      await setValue('input', '   ')
      await view.trigger('input', 'blur')
      expect(lastEmitted(view, 'change'), '空串 → null').toBeNull()

      view.unmount()
    })

    it('TextareaField：多行元素与换行保留', async () => {
      const view = kit.mount('TextareaField', { props: { modelValue: null } })
      const setValue = requireSetValue(view)
      expect(view.has('textarea'), '多行元素').toBe(true)

      await setValue('textarea', 'a\nb')
      expect(lastEmitted(view, 'update:modelValue')).toBe('a\nb')
      view.unmount()
    })

    it('PasswordField：掩码 / 明文切换 / 禁自动填充 / 不落日志', async () => {
      const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
      const view = kit.mount('PasswordField', { props: { modelValue: null } })
      const setValue = requireSetValue(view)

      expect(view.attr('input', 'type'), '默认掩码').toBe('password')
      expect(view.attr('input', 'autocomplete'), '禁自动填充').toBe('new-password')

      await setValue('input', 'Abc12345')
      await view.trigger('.bms-input-password-toggle', 'click')
      expect(view.attr('input', 'type'), '明文切换').toBe('text')
      expect(logSpy, '密码不落日志').not.toHaveBeenCalled()

      logSpy.mockRestore()
      view.unmount()
    })

    it('PasswordField：强度提示与最小长度校验', async () => {
      const view = kit.mount('PasswordField', {
        props: { modelValue: null, strength: true, minLength: 8 },
      })
      const setValue = requireSetValue(view)

      await setValue('input', 'abc')
      expect(view.has('.bms-input-strength'), '强度提示').toBe(true)
      expect(view.has('.bms-input-strength--weak'), '弱强度档位').toBe(true)

      await view.trigger('input', 'blur')
      expect(lastEmitted(view, 'validate'), '长度不足校验失败').toBe(false)

      await setValue('input', 'Abcd1234!')
      await view.trigger('input', 'blur')
      expect(lastEmitted(view, 'validate'), '合法密码校验通过').toBe(true)

      view.unmount()
    })

    it('字段壳：必填 / 外部错误 / 只读两种呈现', async () => {
      const required = kit.mount('TextField', {
        props: { modelValue: null, label: '字段', required: true },
      })
      expect(required.has('.bms-input-required'), '必填星号').toBe(true)
      required.unmount()

      const invalid = kit.mount('TextField', { props: { modelValue: 'x', error: '格式不正确' } })
      expect(invalid.has('.bms-input-error'), '错误区渲染').toBe(true)
      expect(invalid.text()).toContain('格式不正确')
      invalid.unmount()

      const text = kit.mount('TextField', { props: { modelValue: '只读值', readonly: true } })
      expect(text.has('input'), '只读文本态不渲染输入元素').toBe(false)
      expect(text.text()).toContain('只读值')
      text.unmount()

      const disabled = kit.mount('TextField', {
        props: { modelValue: '只读值', readonly: true, readonlyMode: 'disabled' },
      })
      expect(disabled.attr('input', 'disabled'), '只读禁用态').toBeDefined()
      disabled.unmount()
    })

    it('禁用合并：写值被能力拒绝（不外发 update:modelValue）', async () => {
      const view = kit.mount('TextField', { props: { modelValue: null, disabled: true } })
      const setValue = requireSetValue(view)
      await setValue('input', 'blocked')
      expect(view.emitted('update:modelValue') ?? [], '禁用不写入').toHaveLength(0)
      view.unmount()
    })

    it('栅格：span 写入 --bms-input-span', () => {
      const view = kit.mount('TextField', { props: { modelValue: null, span: 12 } })
      const style = view.attr('.bms-text-field', 'style') ?? ''
      expect(style.replace(/\s/g, '')).toContain('--bms-input-span:12')
      expect(view.has('.is-inline'), '半宽类').toBe(true)
      view.unmount()
    })

    it('NumberInput：数值写入 / 空值 / 精度 / 越界钳制与校验 / `0` 与 `null` 区分', async () => {
      const view = kit.mount('NumberInput', { props: { modelValue: null } })
      const setValue = requireSetValue(view)
      expect(view.has('.bms-number-input'), '根类名钩子').toBe(true)

      await setValue('input', '12')
      expect(lastEmitted(view, 'update:modelValue'), '数值写入').toBe(12)

      await setValue('input', '')
      await view.trigger('input', 'blur')
      expect(lastEmitted(view, 'change'), '空值 → null').toBeNull()
      view.unmount()

      const precision = kit.mount('NumberInput', { props: { modelValue: null, precision: 1 } })
      await requireSetValue(precision)('input', '1.2')
      await precision.trigger('input', 'blur')
      expect(lastEmitted(precision, 'change'), '精度保留一位').toBe(1.2)
      precision.unmount()

      const rounded = kit.mount('NumberInput', { props: { modelValue: null, precision: 0 } })
      await requireSetValue(rounded)('input', '1.6')
      await rounded.trigger('input', 'blur')
      expect(lastEmitted(rounded, 'change'), '四舍五入到整数').toBe(2)
      rounded.unmount()

      const clamped = kit.mount('NumberInput', { props: { modelValue: null, min: 0, max: 10 } })
      await requireSetValue(clamped)('input', '20')
      await clamped.trigger('input', 'blur')
      expect(lastEmitted(clamped, 'change'), '越界钳制').toBe(10)
      clamped.unmount()

      const loose = kit.mount('NumberInput', {
        props: { modelValue: null, min: 0, max: 10, clamp: false },
      })
      await requireSetValue(loose)('input', '20')
      await loose.trigger('input', 'blur')
      expect(lastEmitted(loose, 'validate'), 'clamp=false 报越界').toBe(false)
      loose.unmount()

      const zero = kit.mount('NumberInput', { props: { modelValue: 0, readonly: true } })
      expect(zero.text(), '`0` 视为已填').toContain('0')
      zero.unmount()
    })

    it('SelectInput：只读文本 / 多选顺序 / 无效值剔除 / 上限拒绝再选', () => {
      const options = [
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
        { value: 'c', label: 'C' },
      ]

      const single = kit.mount('SelectInput', { props: { modelValue: 'a', options, readonly: true } })
      expect(single.has('.bms-select-input'), '根类名钩子').toBe(true)
      expect(single.text()).toContain('A')
      single.unmount()

      const multi = kit.mount('SelectInput', {
        props: { modelValue: ['b', 'a'], options, multiple: true, readonly: true },
      })
      expect(multi.text().replace(/\s/g, ''), '多选按选项顺序').toContain('A、B')
      multi.unmount()

      const ghost = kit.mount('SelectInput', {
        props: { modelValue: 'ghost', options, readonly: true },
      })
      expect(ghost.text(), '无效值剔除').not.toContain('ghost')
      ghost.unmount()

      const limited = kit.mount('SelectInput', {
        props: { modelValue: ['a'], options, multiple: true, maxCount: 1 },
      })
      const vm = limited.exposed<{ selectOption?: (value: string | number) => void }>()
      vm.selectOption?.('b')
      const last = lastEmitted(limited, 'update:modelValue')
      expect(
        last === undefined || (Array.isArray(last) && !(last as unknown[]).includes('b')),
        '达上限拒绝再选',
      ).toBe(true)
      limited.unmount()
    })
  })
}
