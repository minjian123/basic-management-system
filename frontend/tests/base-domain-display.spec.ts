/** 展示域基类用例（Kiwi 710）：格式化 / 空值占位 / 省略与复制（双端同款）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'

import { BaseDisplay, useDisplayBase } from '@/components/base'

import { mountWithPlugins } from './helpers/mount'

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'clipboard')
})

describe('展示域基类（Kiwi 710）', () => {
  it('① 格式化：函数 / 名义格式化器回退 / 空值占位', () => {
    expect(useDisplayBase({ value: 1234.5, formatter: (value) => `${String(value)}元` }).fullText).toBe('1234.5元')
    expect(useDisplayBase({ value: 5, formatter: 'amount' }).fullText).toBe('5')

    const empty = useDisplayBase({ value: null })
    expect(empty.isEmpty).toBe(true)
    expect(empty.fullText).toBe('')
    expect(empty.displayText).toBe('—')

    const customEmpty = useDisplayBase({ value: undefined, emptyText: '暂无' })
    expect(customEmpty.displayText).toBe('暂无')
  })

  it('② 空值判定：0 / false 非空', () => {
    expect(useDisplayBase({ value: 0 }).isEmpty).toBe(false)
    expect(useDisplayBase({ value: 0 }).displayText).toBe('0')
    expect(useDisplayBase({ value: false }).isEmpty).toBe(false)
    expect(useDisplayBase({ value: false }).displayText).toBe('false')
    expect(useDisplayBase({ value: '' }).isEmpty).toBe(true)
  })

  it('③ 省略与 tooltip', () => {
    const long = 'x'.repeat(40)
    const display = useDisplayBase({ value: long, ellipsis: true })
    expect(display.isEllipsis).toBe(true)
    expect(display.displayText).toBe(`${'x'.repeat(32)}…`)
    expect(display.tooltipText).toBe(long)

    const short = useDisplayBase({ value: 'ok', ellipsis: 10 })
    expect(short.isEllipsis).toBe(false)
    expect(short.displayText).toBe('ok')
    expect(short.tooltipText).toBe('')
  })

  it('④ 点击取值：可点击开关与空值空转', () => {
    const clicked: unknown[] = []
    const plain = useDisplayBase({ value: 'v' })
    expect(plain.isClickable).toBe(false)
    expect(plain.onClick()).toBe(false)

    const explicit = useDisplayBase({ value: 'v', clickable: false, onClickValue: (value) => clicked.push(value) })
    expect(explicit.isClickable).toBe(false)
    expect(explicit.onClick()).toBe(false)

    const clickable = useDisplayBase({ value: 'v', onClickValue: (value) => clicked.push(value) })
    expect(clickable.isClickable).toBe(true)
    expect(clickable.onClick()).toBe(true)
    expect(clicked).toEqual(['v'])

    const empty = useDisplayBase({ value: '', onClickValue: (value) => clicked.push(value) })
    expect(empty.onClick()).toBe(false)
    expect(clicked).toEqual(['v'])
  })

  it('⑤ 复制：clipboard 缺失回退与可用时回调', async () => {
    const copied: unknown[] = []
    const display = useDisplayBase({ value: 'abc', copyable: true, onCopy: (value) => copied.push(value) })
    expect(await display.copy()).toBe(false)

    const writeText = vi.fn().mockResolvedValue(undefined)
    stubClipboard(writeText)
    expect(await display.copy()).toBe(true)
    expect(writeText).toHaveBeenCalledWith('abc')
    expect(copied).toEqual(['abc'])
  })

  it('⑥ 脱敏 / 空值 / 未开启复制不复制', async () => {
    expect(useDisplayBase({ value: 'abc', copyable: true, masked: true }).canCopy).toBe(false)
    expect(useDisplayBase({ value: '', copyable: true }).canCopy).toBe(false)
    expect(useDisplayBase({ value: 'abc' }).canCopy).toBe(false)
    expect(await useDisplayBase({ value: 'abc', copyable: true, masked: true }).copy()).toBe(false)
  })

  it('⑦ BaseDisplay 渲染 / 事件 / 插槽 / 令牌属性', async () => {
    stubClipboard(vi.fn().mockResolvedValue(undefined))
    const wrapper = mountWithPlugins(BaseDisplay, {
      props: { value: 'hello', copyable: true, clickable: true, ellipsis: 3, size: 'small', dataTest: 'cell' },
    })
    expect(wrapper.text()).toContain('hel…')
    expect(wrapper.attributes('data-size')).toBe('small')
    expect(wrapper.attributes('data-test')).toBe('cell')
    await wrapper.find('.bms-display__copy').trigger('click')
    expect(wrapper.emitted('copy')?.[0]).toEqual(['hello'])
    await wrapper.trigger('click')
    expect(wrapper.emitted('click-value')?.[0]).toEqual(['hello'])

    const emptyWrapper = mountWithPlugins(BaseDisplay, {
      props: { value: null },
      slots: { empty: '<i class="none">无</i>' },
    })
    expect(emptyWrapper.find('.none').text()).toBe('无')

    const custom = mountWithPlugins(BaseDisplay, {
      props: { value: 'v' },
      slots: { default: ({ text }: { text: string }) => h('b', { class: 'custom-text' }, text) },
    })
    expect(custom.find('.custom-text').text()).toBe('v')

    const hidden = mountWithPlugins(BaseDisplay, { props: { visible: false } })
    expect(hidden.find('span').exists()).toBe(false)
  })

  it('⑧ 只读不校验：无 modelValue 面', () => {
    const propsDef = (BaseDisplay as unknown as { props?: Record<string, unknown> }).props ?? {}
    expect('modelValue' in propsDef).toBe(false)
    expect(useDisplayBase({ value: 'v' }).isEmpty).toBe(false)
  })
})
