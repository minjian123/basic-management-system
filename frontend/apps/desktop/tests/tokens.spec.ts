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

  it('间距阶梯 / 字号阶梯 / 布局结构令牌齐备（2026-10-04 登记）', () => {
    for (const token of [
      '--bms-space-1',
      '--bms-space-2',
      '--bms-space-3',
      '--bms-space-4',
      '--bms-space-6',
      '--bms-space-8',
      '--bms-radius-lg',
      '--bms-font-size-xs',
      '--bms-font-size-sm',
      '--bms-font-size-lg',
      '--bms-color-bg-page',
      '--bms-layout-sidebar-width',
      '--bms-layout-sidebar-collapsed-width',
      '--bms-layout-header-height',
      '--bms-layout-content-padding',
    ]) {
      expect(scss).toContain(token)
    }
    expect(scss).toContain('@media (max-width: 992px)')
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

  it('布局族内嵌件所需 EP 变量已映射到令牌（2026-10-04 补全）', () => {
    for (const pair of [
      '--el-bg-color: var(--bms-color-bg)',
      '--el-bg-color-page: var(--bms-color-bg-page)',
      '--el-fill-color-blank: var(--bms-color-bg)',
      '--el-fill-color-light: var(--bms-color-fill)',
      '--el-text-color-regular: var(--bms-color-text)',
      '--el-text-color-secondary: var(--bms-color-text-secondary)',
      '--el-border-color-lighter: var(--bms-color-border)',
    ]) {
      expect(scss).toContain(pair)
    }
  })

  it('权限配置域令牌齐备（2026-10-14 登记，前端组件库 11_01）', () => {
    for (const token of ['--bms-perm-detached-color', '--bms-perm-readonly-bg', '--bms-perm-invalid-color']) {
      // 亮 / 暗两套各一处 → 至少两处定义
      expect(scss.split(token).length - 1).toBeGreaterThanOrEqual(2)
    }
  })

  it('容器与展示反馈族令牌齐备（2026-10-14 登记，前端组件库 11_02）', () => {
    // 新增语义令牌：亮 / 暗两套各一处 → 至少两处定义
    for (const token of [
      '--bms-diff-add-bg',
      '--bms-diff-del-bg',
      '--bms-diff-add-color',
      '--bms-diff-del-color',
      '--bms-qr-mask-bg',
      '--bms-file-preview-mask-bg',
      '--bms-color-mask-bg',
    ]) {
      expect(scss.split(token).length - 1).toBeGreaterThanOrEqual(2)
    }
  })

  it('字段族令牌齐备（2026-10-14 登记，前端组件库 11_03）', () => {
    // 新增语义令牌：亮 / 暗两套各一处 → 至少两处定义
    for (const token of [
      '--bms-field-error-color',
      '--bms-field-readonly-bg',
      '--bms-field-readonly-border',
      '--bms-field-suggest-bg',
      '--bms-field-suggest-hover-bg',
      '--bms-richtext-toolbar-bg',
      '--bms-richtext-content-bg',
      '--bms-richtext-border',
      '--bms-richtext-code-bg',
      '--bms-i18n-marker-bg',
      '--bms-i18n-missing-color',
      '--bms-tristate-bg',
      '--bms-tristate-color',
    ]) {
      expect(scss.split(token).length - 1).toBeGreaterThanOrEqual(2)
    }
  })

  it('既有漂移令牌落地（《设计令牌》已登记、工程侧补齐，2026-10-14）', () => {
    // 滚动条 5 条 + 反白字色 + 插画尺寸（漂移落地）与全屏背景（覆盖点转正式）
    for (const token of [
      '--bms-scrollbar-size',
      '--bms-scrollbar-radius',
      '--bms-scrollbar-thumb',
      '--bms-scrollbar-thumb-hover',
      '--bms-scrollbar-track',
      '--bms-color-text-inverse',
      '--bms-illustration-size',
      '--bms-fullscreen-bg',
    ]) {
      expect(scss).toContain(token)
    }
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
