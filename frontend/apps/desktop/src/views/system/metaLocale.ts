/**
 * 权限元数据维护页的语言注入：启用语言清单 + 当前登录用户语言。
 *
 * 语言清单由宿主注入（不写死中英两栏）：当前平台种子语言为 `zh-CN` / `en-US`
 * （`bms_core.i18n.base.SUPPORTED_LOCALES`），默认语言 `zh-CN`；用户语言取动态菜单
 * 响应解析出的 `locale`，未装载时回退默认语言（与后端 `DEFAULT_LOCALE` 同口径）。
 */

import { useMenuStore } from '@/stores/menu'

/** 默认语言（与后端 `DEFAULT_LOCALE` 同源）。 */
export const DEFAULT_LOCALE = 'zh-CN'

/** 语言选项（注入多语言文案字段）。 */
export interface MetaLocaleOption {
  /** 语言标识。 */
  code: string
  /** 语言名称。 */
  name: string
  /** 是否系统默认语言。 */
  isDefault?: boolean
}

/** 启用语言清单（宿主注入；加语言只改此处，页面语言格自动增减）。 */
export const ENABLED_LOCALES: MetaLocaleOption[] = [
  { code: 'zh-CN', name: '简体中文', isDefault: true },
  { code: 'en-US', name: 'English' },
]

/**
 * 当前登录用户语言（动态菜单解析结果，缺省回退默认语言）。
 *
 * @returns 语言标识。
 */
export function currentUserLocale(): string {
  return useMenuStore().locale || DEFAULT_LOCALE
}
