/** 首屏主题预读用例（08-3-2 / Kiwi 765）：偏好解析优先级 / 系统偏好跟随 / 非法值降级 / 非浏览器环境兜底。 */
// kiwi_id: 765

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { applyInitialTheme } from '../src/utils/initialTheme'

describe('applyInitialTheme 首屏主题预读', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('无偏好时按平台默认解析并写根元素', () => {
    const resolved = applyInitialTheme()
    expect(resolved).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('偏好为 dark 时直接解析为暗色', () => {
    localStorage.setItem('bms_preferences', JSON.stringify({ themeMode: 'dark' }))
    expect(applyInitialTheme()).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('偏好为 system 且系统偏好不可用时回落亮色', () => {
    localStorage.setItem('bms_preferences', JSON.stringify({ themeMode: 'system', locale: 'zh-CN' }))
    expect(applyInitialTheme()).toBe('light')
  })

  it('偏好为 system 且系统偏好为暗色时解析为暗色（媒体查询可用分支）', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: true, media: query }))
    localStorage.setItem('bms_preferences', JSON.stringify({ themeMode: 'system' }))

    expect(applyInitialTheme()).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('非法偏好内容降级为平台默认', () => {
    localStorage.setItem('bms_preferences', 'not-json')
    expect(applyInitialTheme()).toBe('light')

    localStorage.setItem('bms_preferences', JSON.stringify({ themeMode: 'unknown' }))
    expect(applyInitialTheme()).toBe('light')

    localStorage.setItem('bms_preferences', JSON.stringify('text'))
    expect(applyInitialTheme()).toBe('light')
  })

  it('非浏览器环境（无 document）时兜底亮色且不写根元素', () => {
    vi.stubGlobal('document', undefined)
    expect(applyInitialTheme()).toBe('light')
  })
})
