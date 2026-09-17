/** 宽高比容器用例（Kiwi 748）：比例解析 / 填充 / 占位与限制。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { AspectRatio } from '../src'

import { mountWithPlugins } from './helpers/mount'

type Wrapper = ReturnType<typeof mountWithPlugins>

function styleOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-aspect-ratio').element as HTMLElement
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('宽高比容器（Kiwi 748）', () => {
  it('比例解析：数字 / 16:9 / 4:3 / 非法回退并告警', () => {
    const numeric = mountWithPlugins(AspectRatio, { props: { ratio: 2 } })
    // jsdom / 浏览器对 aspect-ratio 归一化为 `w / h`
    expect(styleOf(numeric).style.aspectRatio).toBe('2 / 1')
    expect(styleOf(numeric).style.getPropertyValue('--bms-aspect-ratio-number')).toBe('2')

    const colon = mountWithPlugins(AspectRatio, { props: { ratio: '4:3' } })
    expect(styleOf(colon).style.aspectRatio).toBe('4 / 3')
    expect(Number(styleOf(colon).style.getPropertyValue('--bms-aspect-ratio-number'))).toBeCloseTo(
      4 / 3,
    )

    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fallback = mountWithPlugins(AspectRatio, { props: { ratio: 'abc' } })
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('非法 ratio'))
    expect(styleOf(fallback).style.aspectRatio).toBe('16 / 9')
  })

  it('fit 映射：类与样式变量；媒体元素规则可用', () => {
    const wrapper = mountWithPlugins(AspectRatio, {
      props: { fit: 'contain' },
      slots: { default: '<img src="x.png" alt="" />' },
    })
    expect(wrapper.find('.bms-aspect-ratio--fit-contain').exists()).toBe(true)
    expect(styleOf(wrapper).style.getPropertyValue('--bms-aspect-ratio-fit')).toBe('contain')
    expect(wrapper.find('.bms-aspect-ratio-content img').exists()).toBe(true)

    const fill = mountWithPlugins(AspectRatio, { props: { fit: 'fill' } })
    expect(fill.find('.bms-aspect-ratio--fit-fill').exists()).toBe(true)
  })

  it('maxWidth / minHeight 解析输出', () => {
    const wrapper = mountWithPlugins(AspectRatio, {
      props: { maxWidth: 300, minHeight: 120 },
    })
    const style = styleOf(wrapper).style
    expect(style.maxWidth).toBe('300px')
    expect(style.minHeight).toBe('120px')

    const percent = mountWithPlugins(AspectRatio, { props: { maxWidth: '50%' } })
    expect(styleOf(percent).style.maxWidth).toBe('50%')
  })

  it('占位块与 #placeholder 插槽；内容层渲染', () => {
    const wrapper = mountWithPlugins(AspectRatio, {
      slots: {
        placeholder: '<div class="my-ph">载入中</div>',
        default: '<div class="my-content">内容</div>',
      },
    })
    expect(wrapper.find('[data-testid="aspect-placeholder"] .my-ph').exists()).toBe(true)
    expect(wrapper.find('.bms-aspect-ratio-content .my-content').exists()).toBe(true)

    const fallback = mountWithPlugins(AspectRatio)
    expect(fallback.find('[data-testid="aspect-placeholder"]').exists()).toBe(true)
  })
})
