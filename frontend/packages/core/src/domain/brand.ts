/**
 * 领域纯函数：主题解析与品牌令牌派生（`theme` 能力与件层共用，框架无关）。
 */

import type { BrandConfig, ResolvedTheme, ThemeMode } from '../capabilities/theme'

/** 平台默认主色（未配置或非法色值时的回退值）。 */
export const DEFAULT_BRAND_PRIMARY = '#1677ff'

/** RGB 三元组（0 ~ 255）。 */
export interface RgbColor {
  /** 红通道。 */
  r: number
  /** 绿通道。 */
  g: number
  /** 蓝通道。 */
  b: number
}

/** 品牌派生令牌（CSS 变量名 → 值）。 */
export interface BrandTokenMap {
  /** 主色。 */
  '--bms-color-primary': string
  /** 悬停色。 */
  '--bms-color-primary-hover': string
  /** 激活色。 */
  '--bms-color-primary-active': string
  /** 浅色背景。 */
  '--bms-color-primary-light': string
  /** 边框色。 */
  '--bms-color-primary-border': string
  /** 主色之上的前景色。 */
  '--bms-color-on-primary': string
}

/** 主题解析输入。 */
export interface ThemeResolveInput {
  /** 用户模式（未设置时用租户默认）。 */
  mode?: ThemeMode
  /** 系统是否偏好暗色。 */
  systemPrefersDark: boolean
  /** 租户默认模式。 */
  defaultMode?: ThemeMode
  /** 是否禁用暗色。 */
  disableDark?: boolean
}

/** 十六进制短格式（`#rgb`）。 */
const HEX3 = /^#([0-9a-fA-F]{3})$/

/** 十六进制长格式（`#rrggbb`）。 */
const HEX6 = /^#([0-9a-fA-F]{6})$/

/** `rgb()` / `rgba()` 格式。 */
const RGB_FN = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/

/**
 * 通道值归一（0 ~ 255 取整）。
 *
 * @param value 通道值。
 * @returns 归一后的通道值。
 */
function clampChannel(value: number): number {
  return Math.min(255, Math.max(0, Math.round(value)))
}

/**
 * 通道值转两位十六进制。
 *
 * @param value 通道值。
 * @returns 两位十六进制字符串。
 */
function channelHex(value: number): string {
  return clampChannel(value).toString(16).padStart(2, '0')
}

/**
 * 解析颜色为 RGB 三元组（支持 `#rgb` / `#rrggbb` / `rgb()` / `rgba()`）。
 *
 * @param input 颜色字符串。
 * @returns RGB 三元组；非法返回 `undefined`。
 */
export function parseColor(input: string): RgbColor | undefined {
  const text = input.trim()
  const short = HEX3.exec(text)
  if (short !== null) {
    const [r, g, b] = (short[1] as string).split('')
    return { r: parseInt(`${r}${r}`, 16), g: parseInt(`${g}${g}`, 16), b: parseInt(`${b}${b}`, 16) }
  }
  const long = HEX6.exec(text)
  if (long !== null) {
    const hex = long[1] as string
    return { r: parseInt(hex.slice(0, 2), 16), g: parseInt(hex.slice(2, 4), 16), b: parseInt(hex.slice(4, 6), 16) }
  }
  const fn = RGB_FN.exec(text)
  if (fn !== null) {
    const r = Number(fn[1])
    const g = Number(fn[2])
    const b = Number(fn[3])
    if (r > 255 || g > 255 || b > 255) {
      return undefined
    }
    return { r, g, b }
  }
  return undefined
}

/**
 * RGB 三元组转十六进制颜色。
 *
 * @param color RGB 三元组。
 * @returns 十六进制颜色（小写，`#rrggbb`）。
 */
export function toHex(color: RgbColor): string {
  return `#${channelHex(color.r)}${channelHex(color.g)}${channelHex(color.b)}`
}

/**
 * 相对亮度（加权口径：`0.299R + 0.587G + 0.114B` / 255）。
 *
 * @param color 颜色字符串。
 * @returns 亮度（0 ~ 1）；非法颜色返回 `0`。
 */
export function luminance(color: string): number {
  const rgb = parseColor(color)
  if (rgb === undefined) {
    return 0
  }
  return (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255
}

/**
 * 颜色混合（线性插值）。
 *
 * @param from 起始色。
 * @param to 目标色。
 * @param weight 目标色占比（0 ~ 1，越界截断）。
 * @returns 混合后的十六进制颜色（非法输入回退平台默认主色）。
 */
export function mixColor(from: string, to: string, weight: number): string {
  const start = parseColor(from)
  const end = parseColor(to)
  if (start === undefined) {
    return end === undefined ? DEFAULT_BRAND_PRIMARY : toHex(end)
  }
  if (end === undefined) {
    return toHex(start)
  }
  const ratio = Math.min(1, Math.max(0, weight))
  return toHex({
    r: start.r + (end.r - start.r) * ratio,
    g: start.g + (end.g - start.g) * ratio,
    b: start.b + (end.b - start.b) * ratio,
  })
}

/**
 * 提亮（朝白色混合）。
 *
 * @param color 颜色字符串。
 * @param amount 提亮幅度（0 ~ 1）。
 * @returns 提亮后的十六进制颜色。
 */
export function lighten(color: string, amount: number): string {
  return mixColor(color, '#ffffff', amount)
}

/**
 * 压暗（朝黑色混合）。
 *
 * @param color 颜色字符串。
 * @param amount 压暗幅度（0 ~ 1）。
 * @returns 压暗后的十六进制颜色。
 */
export function darken(color: string, amount: number): string {
  return mixColor(color, '#000000', amount)
}

/**
 * 是否合法颜色（可解析）。
 *
 * @param input 颜色字符串。
 */
export function isValidColor(input: string): boolean {
  return parseColor(input) !== undefined
}

/**
 * 派生品牌令牌（主色 → 色阶 / 悬停 / 激活 / 浅底 / 边框 / 前景）。
 *
 * 算法口径：`hover = darken(primary, 0.08)`、`active = darken(primary, 0.16)`、
 * `light = mix(primary, white, 0.88)`、`border = mix(primary, white, 0.68)`、
 * `onPrimary = luminance(primary) > 0.6 ? '#1a1a1a' : '#ffffff'`。非法主色回退平台默认主色。
 *
 * @param primary 主色（十六进制或 `rgb()`）。
 * @returns 品牌令牌表。
 */
export function deriveBrandTokens(primary: string): BrandTokenMap {
  const parsed = parseColor(primary)
  const base = parsed === undefined ? DEFAULT_BRAND_PRIMARY : toHex(parsed)
  return {
    '--bms-color-primary': base,
    '--bms-color-primary-hover': darken(base, 0.08),
    '--bms-color-primary-active': darken(base, 0.16),
    '--bms-color-primary-light': mixColor(base, '#ffffff', 0.88),
    '--bms-color-primary-border': mixColor(base, '#ffffff', 0.68),
    '--bms-color-on-primary': luminance(base) > 0.6 ? '#1a1a1a' : '#ffffff',
  }
}

/**
 * 解析有效主题（用户模式 > 租户默认 > 平台默认；`system` 按系统偏好动态解析）。
 *
 * @param input 解析输入。
 * @returns 有效主题（`light` / `dark`）。
 */
export function resolveThemeMode(input: ThemeResolveInput): ResolvedTheme {
  if (input.disableDark === true) {
    return 'light'
  }
  const mode = input.mode ?? input.defaultMode
  if (mode === 'light' || mode === 'dark') {
    return mode
  }
  if (mode === undefined || mode === 'system') {
    return input.systemPrefersDark ? 'dark' : 'light'
  }
  return 'light'
}

/**
 * 品牌配置归一（剔除空值，非法主色丢弃）。
 *
 * @param brand 品牌配置。
 * @returns 归一后的品牌配置（缺省为空对象）。
 */
export function normalizeBrand(brand?: BrandConfig): BrandConfig {
  if (brand === undefined) {
    return {}
  }
  const normalized: BrandConfig = {}
  if (typeof brand.name === 'string' && brand.name !== '') {
    normalized.name = brand.name
  }
  if (typeof brand.logo === 'string' && brand.logo !== '') {
    normalized.logo = brand.logo
  }
  if (typeof brand.favicon === 'string' && brand.favicon !== '') {
    normalized.favicon = brand.favicon
  }
  if (typeof brand.loginBg === 'string' && brand.loginBg !== '') {
    normalized.loginBg = brand.loginBg
  }
  if (brand.defaultMode !== undefined) {
    normalized.defaultMode = brand.defaultMode
  }
  if (brand.allowUserAccent !== undefined) {
    normalized.allowUserAccent = brand.allowUserAccent
  }
  if (brand.disableDark !== undefined) {
    normalized.disableDark = brand.disableDark
  }
  if (typeof brand.primaryColor === 'string') {
    const parsed = parseColor(brand.primaryColor)
    if (parsed !== undefined) {
      normalized.primaryColor = toHex(parsed)
    }
  }
  return normalized
}
