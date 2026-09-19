/** 首屏主题预读（防闪烁）：应用挂载前解析偏好中的主题模式并写根元素 `data-theme`。 */

import { resolveThemeMode, type ThemeMode } from '@bms/core'

/** 偏好本地存储键（与偏好面板 / 主题能力同一真源）。 */
const PREFERENCE_STORAGE_KEY = 'bms_preferences'

/** 系统偏好媒体查询。 */
const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)'

/**
 * 读取偏好中的主题模式（存储不可用或解析失败时返回 `undefined`）。
 */
function readStoredMode(): ThemeMode | undefined {
  try {
    const raw = globalThis.localStorage?.getItem(PREFERENCE_STORAGE_KEY)
    if (raw === null || raw === undefined) {
      return undefined
    }
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) {
      return undefined
    }
    const value = (parsed as { themeMode?: unknown }).themeMode
    return value === 'light' || value === 'dark' || value === 'system' ? value : undefined
  } catch {
    // 存储受限（隐私模式 / 非法 JSON）时降级为平台默认。
    return undefined
  }
}

/**
 * 解析首屏主题并写入根元素（挂载前调用，避免闪白 / 闪黑）。
 *
 * @returns 解析后的有效主题。
 */
export function applyInitialTheme(): 'light' | 'dark' {
  const doc = globalThis.document
  if (doc === undefined) {
    return 'light'
  }
  const prefersDark =
    typeof globalThis.matchMedia === 'function' ? globalThis.matchMedia(DARK_MEDIA_QUERY).matches : false
  const resolved = resolveThemeMode({ mode: readStoredMode(), systemPrefersDark: prefersDark })
  doc.documentElement.dataset.theme = resolved
  return resolved
}
