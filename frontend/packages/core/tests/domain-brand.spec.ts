import { describe, expect, it } from 'vitest'

import {
  DEFAULT_BRAND_PRIMARY,
  darken,
  deriveBrandTokens,
  isValidColor,
  lighten,
  luminance,
  mixColor,
  normalizeBrand,
  parseColor,
  resolveThemeMode,
  toHex,
} from '../src'

describe('domain/brand · 颜色解析', () => {
  it('解析 #rgb / #rrggbb / rgb() / rgba() 并归一为十六进制', () => {
    expect(parseColor('#1677ff')).toEqual({ r: 22, g: 119, b: 255 })
    expect(parseColor('#fff')).toEqual({ r: 255, g: 255, b: 255 })
    expect(parseColor('rgb(22, 119, 255)')).toEqual({ r: 22, g: 119, b: 255 })
    expect(parseColor('rgba(22, 119, 255, 0.5)')).toEqual({ r: 22, g: 119, b: 255 })
    expect(toHex({ r: 22, g: 119, b: 255 })).toBe('#1677ff')
    expect(toHex({ r: 22, g: 119, b: 300 })).toBe('#1677ff')
  })

  it('非法颜色返回 undefined，isValidColor 判定一致', () => {
    expect(parseColor('not-a-color')).toBeUndefined()
    expect(parseColor('rgb(300, 0, 0)')).toBeUndefined()
    expect(isValidColor('#1677ff')).toBe(true)
    expect(isValidColor('red')).toBe(false)
  })

  it('混色 / 提亮 / 压暗按占比插值（越界截断）', () => {
    expect(mixColor('#000000', '#ffffff', 0.5)).toBe('#808080')
    expect(mixColor('#000000', '#ffffff', 2)).toBe('#ffffff')
    expect(lighten('#000000', 1)).toBe('#ffffff')
    expect(darken('#ffffff', 1)).toBe('#000000')
    expect(luminance('#ffffff')).toBe(1)
    expect(luminance('bad')).toBe(0)
  })
})

describe('domain/brand · 品牌令牌派生', () => {
  it('派生六项令牌（固定样例）', () => {
    const tokens = deriveBrandTokens('#1677ff')
    expect(tokens['--bms-color-primary']).toBe('#1677ff')
    expect(tokens['--bms-color-primary-hover']).toBe('#146deb')
    expect(tokens['--bms-color-primary-active']).toBe('#1264d6')
    expect(tokens['--bms-color-primary-light']).toBe('#e3efff')
    expect(tokens['--bms-color-primary-border']).toBe('#b4d3ff')
    expect(tokens['--bms-color-on-primary']).toBe('#ffffff')
  })

  it('浅色主色前景转深色；非法主色回退平台默认', () => {
    expect(deriveBrandTokens('#ffd700')['--bms-color-on-primary']).toBe('#1a1a1a')
    expect(deriveBrandTokens('bad')['--bms-color-primary']).toBe(DEFAULT_BRAND_PRIMARY)
  })
})

describe('domain/brand · 主题解析与品牌归一', () => {
  it('解析优先级：用户模式 > 租户默认 > 平台默认；system 按系统偏好', () => {
    expect(resolveThemeMode({ systemPrefersDark: false })).toBe('light')
    expect(resolveThemeMode({ systemPrefersDark: true })).toBe('dark')
    expect(resolveThemeMode({ mode: 'system', systemPrefersDark: true })).toBe('dark')
    expect(resolveThemeMode({ mode: 'light', systemPrefersDark: true })).toBe('light')
    expect(resolveThemeMode({ defaultMode: 'dark', systemPrefersDark: false })).toBe('dark')
    expect(resolveThemeMode({ mode: 'system', defaultMode: 'dark', systemPrefersDark: false })).toBe('light')
  })

  it('禁用暗色强制亮色', () => {
    expect(resolveThemeMode({ mode: 'dark', systemPrefersDark: true, disableDark: true })).toBe('light')
  })

  it('品牌归一剔除空值与非法色值', () => {
    expect(normalizeBrand({ name: '示例', logo: '', primaryColor: 'bad', defaultMode: 'dark' })).toEqual({
      name: '示例',
      defaultMode: 'dark',
    })
    expect(normalizeBrand()).toEqual({})
    expect(normalizeBrand({ primaryColor: '#FFF' }).primaryColor).toBe('#ffffff')
    expect(normalizeBrand({ allowUserAccent: true, disableDark: false })).toEqual({
      allowUserAccent: true,
      disableDark: false,
    })
  })
})
