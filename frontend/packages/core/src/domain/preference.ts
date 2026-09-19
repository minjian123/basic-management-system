/**
 * 偏好领域纯函数：偏好项键与平台默认值、租户策略判定、默认值合并与差异计算。
 *
 * 框架无关；偏好项集合与《组件设计 · 偏好设置面板》「偏好项（内置）」及后端用户喜好登记项对齐。
 * 偏好项的后端存储与同步不在此列（本模块只做前端取值口径）。
 */

import { stableStringify } from './serialize'

/** 偏好项键（扁平路径，含嵌套键；与组件设计登记一致）。 */
export const PREFERENCE_KEYS = [
  'themeMode',
  'accent',
  'locale',
  'timezone',
  'sidebarCollapsed',
  'tabsEnabled',
  'tabsStyle',
  'listDensity',
  'defaultRoute',
  'notify.inbox',
  'notify.email',
  'notify.sms',
  'shortcuts',
] as const

/** 偏好项键类型。 */
export type PreferenceKey = (typeof PREFERENCE_KEYS)[number]

/** 通知渠道键（`notify` 子对象）。 */
type NotifyChannel = 'inbox' | 'email' | 'sms'

/** 偏好值（全量键）。 */
export interface PreferenceValues {
  /** 主题模式：亮色 / 暗色 / 跟随系统（用户级覆盖租户品牌）。 */
  themeMode: 'light' | 'dark' | 'system'
  /** 是否允许强调色覆盖（受租户策略控制）。 */
  accent: boolean
  /** 界面语言。 */
  locale: string
  /** 时区（影响日期时间显示）。 */
  timezone: string
  /** 侧栏默认折叠。 */
  sidebarCollapsed: boolean
  /** 是否启用多标签导航。 */
  tabsEnabled: boolean
  /** 多标签样式。 */
  tabsStyle: 'card' | 'plain'
  /** 列表密度。 */
  listDensity: 'compact' | 'comfortable' | 'loose'
  /** 默认主页（登录后默认页）。 */
  defaultRoute: string
  /** 通知偏好（渠道开关）。 */
  notify: { inbox: boolean; email: boolean; sms: boolean }
  /** 是否启用快捷键。 */
  shortcuts: boolean
}

/** 平台默认偏好值。 */
export const PREFERENCE_DEFAULTS: Readonly<PreferenceValues> = {
  themeMode: 'light',
  accent: false,
  locale: 'zh-CN',
  timezone: 'Asia/Shanghai',
  sidebarCollapsed: false,
  tabsEnabled: true,
  tabsStyle: 'card',
  listDensity: 'comfortable',
  defaultRoute: '/dashboard',
  notify: { inbox: true, email: false, sms: false },
  shortcuts: true,
}

/** 租户策略项（缺省即可见且可选）。 */
export interface PreferencePolicy {
  /** 是否可见（`false` 时该项不展示）。 */
  visible?: boolean
  /** 是否可选（`false` 时该项不可修改）。 */
  enabled?: boolean
}

/** 租户策略表（按偏好项键）。 */
export type PreferencePolicyMap = Partial<Record<PreferenceKey, PreferencePolicy>>

/** 主题模式取值域。 */
const THEME_MODES: readonly PreferenceValues['themeMode'][] = ['light', 'dark', 'system']

/** 多标签样式取值域。 */
const TABS_STYLES: readonly PreferenceValues['tabsStyle'][] = ['card', 'plain']

/** 列表密度取值域。 */
const LIST_DENSITIES: readonly PreferenceValues['listDensity'][] = ['compact', 'comfortable', 'loose']

/**
 * 读取扁平偏好键对应的值。
 *
 * @param values 偏好值。
 * @param key 偏好项键。
 * @returns 原始值。
 */
export function readPreferenceValue(values: PreferenceValues, key: PreferenceKey): unknown {
  if (key.startsWith('notify.')) {
    return values.notify[key.slice('notify.'.length) as NotifyChannel]
  }
  return (values as unknown as Record<string, unknown>)[key]
}

/**
 * 写入扁平偏好键（返回新值对象，不改原对象）。
 *
 * @param values 偏好值。
 * @param key 偏好项键。
 * @param value 新值（不合法值视为未变更）。
 * @returns 新的偏好值。
 */
export function writePreferenceValue(values: PreferenceValues, key: PreferenceKey, value: unknown): PreferenceValues {
  if (key.startsWith('notify.')) {
    const channel = key.slice('notify.'.length) as NotifyChannel
    return { ...values, notify: { ...values.notify, [channel]: value as boolean } }
  }
  return { ...values, [key]: value } as PreferenceValues
}

/**
 * 合并偏好值（嵌套 `notify` 逐键合并）。
 *
 * @param base 基线值。
 * @param override 覆盖值。
 * @returns 合并结果。
 */
export function mergePreferences(base: PreferenceValues, override?: Partial<PreferenceValues>): PreferenceValues {
  const source = override ?? {}
  return { ...base, ...source, notify: { ...base.notify, ...(source.notify ?? {}) } }
}

/**
 * 校验单个偏好项取值是否合法（非法值回退默认）。
 *
 * @param key 偏好项键。
 * @param value 原始值。
 * @returns 是否合法。
 */
function isValidPreferenceValue(key: PreferenceKey, value: unknown): boolean {
  switch (key) {
    case 'themeMode':
      return THEME_MODES.includes(value as PreferenceValues['themeMode'])
    case 'tabsStyle':
      return TABS_STYLES.includes(value as PreferenceValues['tabsStyle'])
    case 'listDensity':
      return LIST_DENSITIES.includes(value as PreferenceValues['listDensity'])
    case 'locale':
    case 'timezone':
    case 'defaultRoute':
      return typeof value === 'string' && value !== ''
    default:
      return typeof value === 'boolean'
  }
}

/**
 * 按默认值修正非法项（返回新值对象）。
 *
 * @param values 候选值。
 * @param fallback 回退基线。
 * @param keys 需回退的键。
 * @returns 修正后的偏好值。
 */
function fallbackPreferences(
  values: PreferenceValues,
  fallback: PreferenceValues,
  keys: readonly PreferenceKey[],
): PreferenceValues {
  let next = values
  for (const key of keys) {
    next = writePreferenceValue(next, key, readPreferenceValue(fallback, key))
  }
  return next
}

/**
 * 归一偏好值：逐键校验，非法值回退基线（缺省平台默认）。
 *
 * @param input 候选值（含部分键）。
 * @param fallback 回退基线。
 * @returns 全量合法偏好值。
 */
export function sanitizePreferences(
  input: Partial<PreferenceValues> = {},
  fallback: PreferenceValues = PREFERENCE_DEFAULTS,
): PreferenceValues {
  const merged = mergePreferences(fallback, input)
  const invalid = PREFERENCE_KEYS.filter((key) => !isValidPreferenceValue(key, readPreferenceValue(merged, key)))
  return invalid.length === 0 ? merged : fallbackPreferences(merged, fallback, invalid)
}

/**
 * 解析默认值 = 平台默认 ∩ 租户默认（租户已禁用项不接受租户覆盖）。
 *
 * @param tenantDefaults 租户默认值。
 * @param policy 租户策略。
 * @returns 默认偏好值。
 */
export function resolvePreferenceDefaults(
  tenantDefaults?: Partial<PreferenceValues>,
  policy?: PreferencePolicyMap,
): PreferenceValues {
  const resolved = sanitizePreferences(tenantDefaults ?? {}, PREFERENCE_DEFAULTS)
  if (policy === undefined) {
    return resolved
  }
  const disabled = PREFERENCE_KEYS.filter((key) => !isPreferenceEnabled(key, policy))
  return disabled.length === 0 ? resolved : fallbackPreferences(resolved, { ...PREFERENCE_DEFAULTS }, disabled)
}

/**
 * 应用默认值（可选项取默认、不可选项保留现值）——「恢复默认」口径。
 *
 * @param current 当前值。
 * @param defaults 默认值（平台默认 ∩ 租户默认）。
 * @param policy 租户策略。
 * @returns 恢复后的偏好值。
 */
export function applyPreferenceDefaults(
  current: PreferenceValues,
  defaults: PreferenceValues,
  policy?: PreferencePolicyMap,
): PreferenceValues {
  let next = current
  for (const key of PREFERENCE_KEYS) {
    if (isPreferenceEnabled(key, policy)) {
      next = writePreferenceValue(next, key, readPreferenceValue(defaults, key))
    }
  }
  return next
}

/**
 * 计算差异键（用于脏标记与单项变更事件）。
 *
 * @param a 前值。
 * @param b 后值。
 * @returns 发生变更的偏好项键（按登记顺序）。
 */
export function diffPreferences(a: PreferenceValues, b: PreferenceValues): PreferenceKey[] {
  return PREFERENCE_KEYS.filter(
    (key) => stableStringify(readPreferenceValue(a, key)) !== stableStringify(readPreferenceValue(b, key)),
  )
}

/**
 * 偏好项是否可见（策略 `visible: false` 时不可见）。
 *
 * @param key 偏好项键。
 * @param policy 租户策略。
 * @returns 是否可见。
 */
export function isPreferenceVisible(key: PreferenceKey, policy?: PreferencePolicyMap): boolean {
  return policy?.[key]?.visible !== false
}

/**
 * 偏好项是否可选（不可见视为不可选）。
 *
 * @param key 偏好项键。
 * @param policy 租户策略。
 * @returns 是否可选。
 */
export function isPreferenceEnabled(key: PreferenceKey, policy?: PreferencePolicyMap): boolean {
  return isPreferenceVisible(key, policy) && policy?.[key]?.enabled !== false
}
