/** 模块内文案组合式：读取模块文案真源（与 `i18nPacks` 注册载荷同源）。 */

import { SAMPLE_DEFAULT_LOCALE, SAMPLE_MESSAGES } from '../i18n/messages'

/** 占位符参数。 */
export type SampleI18nParams = Record<string, string | number>

/**
 * 模块内文案读取器。
 *
 * 模块视图不直连宿主 i18n 实例（隔离约定），读取模块文案真源；`{name}` 占位按参数替换。
 *
 * @returns `t(key, params?)`。
 */
export function useSampleI18n(): { t: (key: string, params?: SampleI18nParams) => string } {
  const messages = SAMPLE_MESSAGES[SAMPLE_DEFAULT_LOCALE] ?? {}
  function t(key: string, params?: SampleI18nParams): string {
    let text = messages[key] ?? key
    if (params === undefined) {
      return text
    }
    for (const [name, value] of Object.entries(params)) {
      text = text.split(`{${name}}`).join(String(value))
    }
    return text
  }
  return { t }
}
