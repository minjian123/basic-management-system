/** 设计令牌文件校验（宿主权威源）：基础令牌 / 档位属性选择器 / 状态类 / 组件库映射。 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const scss = readFileSync(resolve(process.cwd(), 'src/styles/tokens.scss'), 'utf-8')

describe('设计令牌 tokens.scss', () => {
  it('基础令牌五组齐备', () => {
    for (const token of ['--bms-color-primary', '--bms-font-family', '--bms-spacing-md', '--bms-radius-md', '--bms-shadow-1']) {
      expect(scss).toContain(token)
    }
  })

  it('尺寸 / 密度档位与属性协议选择器', () => {
    expect(scss).toContain("[data-size='small']")
    expect(scss).toContain("[data-size='default']")
    expect(scss).toContain("[data-size='large']")
    expect(scss).toContain("[data-density='compact']")
    expect(scss).toContain("[data-density='loose']")
  })

  it('状态类与组件库主题映射', () => {
    expect(scss).toContain('.is-loading')
    expect(scss).toContain('.is-disabled')
    expect(scss).toContain('.is-hidden')
    expect(scss).toContain('--el-color-primary: var(--bms-color-primary)')
  })

  it('打印样式令牌组齐备（打印与屏幕样式解耦）', () => {
    for (const token of [
      '--bms-print-paper-bg',
      '--bms-print-text',
      '--bms-print-margin',
      '--bms-print-font-size',
      '--bms-print-line-height',
      '--bms-print-line-width',
      '--bms-print-watermark-color',
      '--bms-print-mono-filter',
    ]) {
      expect(scss).toContain(token)
    }
    expect(scss).toContain('@media print')
  })
})
