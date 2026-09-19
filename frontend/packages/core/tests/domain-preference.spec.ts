/** 偏好领域纯函数用例（08_03_01）：全量键与默认值 / 扁平读写 / 合并 / 归一 / 租户策略 / 差异。 */

import { describe, expect, it } from 'vitest'

import {
  PREFERENCE_DEFAULTS,
  PREFERENCE_KEYS,
  applyPreferenceDefaults,
  diffPreferences,
  isPreferenceEnabled,
  isPreferenceVisible,
  mergePreferences,
  readPreferenceValue,
  resolvePreferenceDefaults,
  sanitizePreferences,
  writePreferenceValue,
  type PreferenceValues,
} from '../src'

describe('偏好键与平台默认值', () => {
  it('全量键覆盖设计登记项（含 notify 渠道）', () => {
    expect([...PREFERENCE_KEYS]).toEqual([
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
    ])
    for (const key of PREFERENCE_KEYS) {
      expect(readPreferenceValue({ ...PREFERENCE_DEFAULTS }, key)).toBeDefined()
    }
  })

  it('默认值口径：亮色 / 简体中文 / 舒适密度 / 站内信开启', () => {
    expect(PREFERENCE_DEFAULTS.themeMode).toBe('light')
    expect(PREFERENCE_DEFAULTS.locale).toBe('zh-CN')
    expect(PREFERENCE_DEFAULTS.timezone).toBe('Asia/Shanghai')
    expect(PREFERENCE_DEFAULTS.listDensity).toBe('comfortable')
    expect(PREFERENCE_DEFAULTS.notify).toEqual({ inbox: true, email: false, sms: false })
  })

  it('扁平读写（含嵌套 notify 键）返回新对象', () => {
    const base = { ...PREFERENCE_DEFAULTS, notify: { ...PREFERENCE_DEFAULTS.notify } }
    const next = writePreferenceValue(base, 'notify.email', true)
    expect(readPreferenceValue(next, 'notify.email')).toBe(true)
    expect(base.notify.email).toBe(false)

    const theme = writePreferenceValue(base, 'themeMode', 'dark')
    expect(readPreferenceValue(theme, 'themeMode')).toBe('dark')
    expect(readPreferenceValue(base, 'themeMode')).toBe('light')
  })
})

describe('偏好合并与归一', () => {
  it('合并嵌套 notify 逐键覆盖', () => {
    const merged = mergePreferences({ ...PREFERENCE_DEFAULTS }, { locale: 'en-US', notify: { sms: true } as never })
    expect(merged.locale).toBe('en-US')
    expect(merged.notify).toEqual({ inbox: true, email: false, sms: true })
  })

  it('归一：非法值回退基线，合法值保留', () => {
    const sanitized = sanitizePreferences({
      themeMode: 'neon' as never,
      listDensity: 'compact',
      locale: '',
      shortcuts: 'yes' as never,
    })
    expect(sanitized.themeMode).toBe(PREFERENCE_DEFAULTS.themeMode)
    expect(sanitized.locale).toBe(PREFERENCE_DEFAULTS.locale)
    expect(sanitized.shortcuts).toBe(PREFERENCE_DEFAULTS.shortcuts)
    expect(sanitized.listDensity).toBe('compact')
  })

  it('归一：无非法项时原样返回合并结果', () => {
    const sanitized = sanitizePreferences({ tabsStyle: 'plain' })
    expect(sanitized.tabsStyle).toBe('plain')
    expect(sanitized.themeMode).toBe(PREFERENCE_DEFAULTS.themeMode)
  })
})

describe('租户策略与默认值解析', () => {
  it('默认值 = 平台默认 ∩ 租户默认', () => {
    const resolved = resolvePreferenceDefaults({ themeMode: 'dark', notify: { inbox: false } as never })
    expect(resolved.themeMode).toBe('dark')
    expect(resolved.notify.inbox).toBe(false)
    expect(resolved.locale).toBe(PREFERENCE_DEFAULTS.locale)
  })

  it('租户已禁用项不接受租户默认覆盖', () => {
    const resolved = resolvePreferenceDefaults({ themeMode: 'dark' }, { themeMode: { enabled: false } })
    expect(resolved.themeMode).toBe(PREFERENCE_DEFAULTS.themeMode)
  })

  it('可见 / 可选判定（不可见视为不可选）', () => {
    const policy = { accent: { enabled: false }, shortcuts: { visible: false } }
    expect(isPreferenceVisible('accent', policy)).toBe(true)
    expect(isPreferenceEnabled('accent', policy)).toBe(false)
    expect(isPreferenceVisible('shortcuts', policy)).toBe(false)
    expect(isPreferenceEnabled('shortcuts', policy)).toBe(false)
    expect(isPreferenceEnabled('themeMode', policy)).toBe(true)
  })

  it('恢复默认跳过不可选项（保留现值）', () => {
    const current: PreferenceValues = { ...PREFERENCE_DEFAULTS, notify: { ...PREFERENCE_DEFAULTS.notify }, accent: true, themeMode: 'dark' }
    const defaults = resolvePreferenceDefaults()
    const applied = applyPreferenceDefaults(current, defaults, { accent: { enabled: false } })
    expect(applied.themeMode).toBe(defaults.themeMode)
    expect(applied.accent).toBe(true)
  })
})

describe('偏好差异', () => {
  it('按登记顺序返回变更键', () => {
    const before: PreferenceValues = { ...PREFERENCE_DEFAULTS, notify: { ...PREFERENCE_DEFAULTS.notify } }
    const after: PreferenceValues = {
      ...before,
      notify: { ...before.notify, sms: true },
      listDensity: 'compact',
      themeMode: 'dark',
    }
    expect(diffPreferences(before, after)).toEqual(['themeMode', 'listDensity', 'notify.sms'])
    expect(diffPreferences(before, { ...before, notify: { ...before.notify } })).toEqual([])
  })
})
