/** 输入域工厂（`createInputContext`）与密码强度纯函数契约用例（05_01）。 */

import { describe, expect, it } from 'vitest'

import { createInputContext, evaluatePasswordStrength } from '../../src'

describe('输入域工厂契约（createInputContext）', () => {
  it('受控读写与三态：`0` / `false` 视为已填，空串 / `null` 视为空', () => {
    const number = createInputContext<number>({ fieldOptions: { value: { initial: 0 } } })
    expect(number.read()).toBe(0)
    expect(number.displayText()).toBe('0')
    number.write(12)
    expect(number.read()).toBe(12)
    number.dispose()

    const bool = createInputContext<boolean>({ fieldOptions: { value: { initial: false } } })
    expect(bool.read()).toBe(false)
    expect(bool.displayText()).toBe('false')
    expect(bool.normalizeValue()).toBe(false)
    bool.dispose()

    const blank = createInputContext<string>({ fieldOptions: { value: { initial: '' } } })
    expect(blank.displayText()).toBe('')
    expect(blank.normalizeValue()).toBeNull()
    blank.dispose()
  })

  it('归一：trim → 空值 → 自定义钩子（顺序固定）', () => {
    const ctx = createInputContext<string>()
    ctx.write('  abc  ')
    expect(ctx.normalizeValue()).toBe('abc')

    ctx.write('   ')
    expect(ctx.normalizeValue()).toBeNull()

    const hooked = createInputContext<string>({
      trim: false,
      normalize: (value) => (typeof value === 'string' ? value.replace(/\r\n?/g, '\n') : value),
    })
    hooked.write('a\r\nb')
    expect(hooked.normalizeValue()).toBe('a\nb')
    hooked.dispose()
    ctx.dispose()
  })

  it('清空：`clearable` 为真时写空值（可关）', () => {
    const ctx = createInputContext<string>({ fieldOptions: { value: { initial: 'x' } } })
    ctx.clear()
    expect(ctx.read()).toBeNull()
    ctx.dispose()

    const locked = createInputContext<string>({
      fieldOptions: { value: { initial: 'x' } },
      controlOptions: { clearable: false },
    })
    locked.clear()
    expect(locked.read()).toBe('x')
    locked.dispose()
  })

  it('模式判定：禁用 > 只读 > 编辑（只读呈现可配）', () => {
    const editable = createInputContext<string>()
    expect(editable.mode()).toBe('edit')
    editable.dispose()

    const disabled = createInputContext<string>({ fieldOptions: { disabled: true } })
    expect(disabled.mode()).toBe('disabled')
    disabled.dispose()

    const readonlyText = createInputContext<string>({ fieldOptions: { value: { readonly: true } } })
    expect(readonlyText.mode()).toBe('text')
    readonlyText.dispose()

    const readonlyDisabled = createInputContext<string>({
      fieldOptions: { value: { readonly: true } },
      readonlyMode: 'disabled',
    })
    expect(readonlyDisabled.mode()).toBe('disabled')
    readonlyDisabled.dispose()
  })

  it('写门禁：禁用 / 只读拒绝写入（值不变，不重复实现）', () => {
    const disabled = createInputContext<string>({
      fieldOptions: { disabled: true, value: { initial: 'keep' } },
    })
    disabled.write('blocked')
    expect(disabled.read()).toBe('keep')
    disabled.dispose()

    const readonly = createInputContext<string>({ fieldOptions: { value: { initial: 'keep', readonly: true } } })
    readonly.write('blocked')
    expect(readonly.read()).toBe('keep')
    readonly.dispose()
  })

  it('提交：归一写回 + 失焦（`commit` 返回提交值）', () => {
    const ctx = createInputContext<string>()
    ctx.focus()
    expect(ctx.control.focused.get()).toBe(true)
    ctx.write('  x  ')
    expect(ctx.commit()).toBe('x')
    expect(ctx.read()).toBe('x')
    expect(ctx.control.focused.get()).toBe(false)
    ctx.dispose()
  })

  it('composition 桥接：输入法组合期间标志翻转', () => {
    const ctx = createInputContext<string>()
    ctx.compositionStart()
    expect(ctx.control.composing.get()).toBe(true)
    ctx.compositionEnd()
    expect(ctx.control.composing.get()).toBe(false)
    ctx.dispose()
  })

  it('释放：`dispose` 联动释放两个能力', () => {
    const ctx = createInputContext<string>()
    ctx.dispose()
    expect(ctx.field.isDisposed).toBe(true)
    expect(ctx.control.isDisposed).toBe(true)
  })
})

describe('密码强度契约（evaluatePasswordStrength）', () => {
  it('空值 → 弱 / 0 分 / 缺失项全列', () => {
    for (const value of [null, undefined, '']) {
      const result = evaluatePasswordStrength(value)
      expect(result.level).toBe('weak')
      expect(result.score).toBe(0)
      expect(result.missing).toEqual(['length', 'lower', 'upper', 'digit', 'symbol'])
    }
  })

  it('档位判定：长度与字符类别共同决定（弱 / 中 / 强）', () => {
    expect(evaluatePasswordStrength('abc').level).toBe('weak')
    expect(evaluatePasswordStrength('abcdefgh').level, '仅长度达标、类别不足').toBe('weak')
    expect(evaluatePasswordStrength('abcdefg1').level).toBe('medium')
    expect(evaluatePasswordStrength('Abcdefgh1234').level).toBe('strong')
  })

  it('缺失项与分数：逐项列出并封顶 4 分', () => {
    const short = evaluatePasswordStrength('ab1')
    expect(short.missing).toContain('length')
    expect(short.missing).toContain('upper')
    expect(short.missing).not.toContain('lower')
    expect(short.missing).not.toContain('digit')

    const strong = evaluatePasswordStrength('Abcdefgh1234!')
    expect(strong.missing).toEqual([])
    expect(strong.score).toBe(4)
  })

  it('规则可配：自定义最小长度与档位阈值', () => {
    const result = evaluatePasswordStrength('abcd1', { minLength: 4, strongLength: 6, mediumClasses: 2 })
    expect(result.level).toBe('medium')
    const strong = evaluatePasswordStrength('abcd1A', { minLength: 4, strongLength: 6, strongClasses: 3 })
    expect(strong.level).toBe('strong')
  })
})
