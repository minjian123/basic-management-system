/** 基础令牌落地与消费（Kiwi 723）：SCSS 编译产物断言——基础令牌五组 / 引用映射 / Element Plus 映射 / 属性协议保留。 */

import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { compile } from 'sass'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const css = compile(resolve(here, '../src/styles/tokens.scss')).css

const BASE_TOKENS = [
  '--bms-color-primary: #0969da',
  '--bms-color-success: #2da44e',
  '--bms-color-warning: #d4a72c',
  '--bms-color-danger: #cf222e',
  '--bms-color-info: #57606a',
  '--bms-color-bg-page: #f7f8fa',
  '--bms-color-bg: #ffffff',
  '--bms-color-border: #d0d7de',
  '--bms-color-text: #1f2328',
  '--bms-color-text-secondary: #57606a',
  '--bms-font-family:',
  '--bms-font-family-mono:',
  '--bms-font-size-xs: 12px',
  '--bms-font-size-sm: 13px',
  '--bms-font-size-base: 14px',
  '--bms-font-size-lg: 16px',
  '--bms-font-size-xl: 20px',
  '--bms-font-size-xxl: 24px',
  '--bms-font-weight-normal: 400',
  '--bms-font-weight-medium: 500',
  '--bms-font-weight-semibold: 600',
  '--bms-font-weight-bold: 700',
  '--bms-line-height-compact: 1.5',
  '--bms-line-height-base: 1.75',
  '--bms-line-height-loose: 2',
  '--bms-space-1: 4px',
  '--bms-space-2: 8px',
  '--bms-space-3: 12px',
  '--bms-space-4: 16px',
  '--bms-space-6: 24px',
  '--bms-space-8: 32px',
  '--bms-radius-sm: 4px',
  '--bms-radius-md: 6px',
  '--bms-radius-lg: 8px',
  '--bms-shadow-sm:',
  '--bms-shadow-md:',
  '--bms-shadow-lg:',
] as const

describe('基础令牌落地（Kiwi 723）', () => {
  it('基础令牌五组齐备（色彩 / 字体 / 间距 / 圆角 / 阴影）', () => {
    for (const token of BASE_TOKENS) {
      expect(css, token).toContain(token)
    }
  })

  it('size / density 引用基础令牌，属性协议选择器保留', () => {
    expect(css).toContain('--bms-size-font-small: var(--bms-font-size-xs)')
    expect(css).toContain('--bms-size-font-default: var(--bms-font-size-base)')
    expect(css).toContain('--bms-size-font-large: var(--bms-font-size-lg)')
    expect(css).toContain('--bms-density-gap-compact: var(--bms-space-1)')
    expect(css).toContain('--bms-density-gap-default: var(--bms-space-2)')
    expect(css).toContain('--bms-density-gap-loose: var(--bms-space-4)')
    expect(css).toContain('[data-size=small]')
    expect(css).toContain('[data-size=default]')
    expect(css).toContain('[data-size=large]')
    expect(css).toContain('[data-density=compact]')
    expect(css).toContain('[data-density=default]')
    expect(css).toContain('[data-density=loose]')
  })

  it('Element Plus 映射：五色 / 色阶派生 / 圆角 / 字体族与字号', () => {
    for (const color of ['primary', 'success', 'warning', 'danger', 'info']) {
      expect(css).toContain(`--el-color-${color}: var(--bms-color-${color})`)
      for (const level of ['light-3', 'light-5', 'light-7', 'light-8', 'light-9']) {
        expect(css).toContain(`--el-color-${color}-${level}: color-mix(`)
      }
      expect(css).toContain(`--el-color-${color}-dark-2: color-mix(`)
    }
    const rgb = {
      primary: '9, 105, 218',
      success: '45, 164, 78',
      warning: '212, 167, 44',
      danger: '207, 34, 46',
      info: '87, 96, 106',
    }
    for (const [name, value] of Object.entries(rgb)) {
      expect(css).toContain(`--el-color-${name}-rgb: ${value}`)
    }
    expect(css).toContain('--el-border-radius-small: var(--bms-radius-sm)')
    expect(css).toContain('--el-border-radius-base: var(--bms-radius-md)')
    expect(css).toContain('--el-font-family: var(--bms-font-family)')
    expect(css).toContain('--el-font-size-base: var(--bms-font-size-base)')
  })
})
