import { describe, expect, it } from 'vitest'

import { BasePersistedState, BaseTheme, validateCapabilityGraph } from '../src'

/** 具体主题件（测试用）。 */
class Theme extends BaseTheme {}

/** 具体偏好持久化（测试用）。 */
class Persisted extends BasePersistedState {}

/** 内存存储（测试用，模拟 localStorage 最小接口）。 */
class MemoryStorage {
  /** 内部键值表。 */
  private store = new Map<string, string>()

  /**
   * 读取键值。
   *
   * @param key 键。
   */
  getItem(key: string): string | null {
    return this.store.get(key) ?? null
  }

  /**
   * 写入键值。
   *
   * @param key 键。
   * @param value 值。
   */
  setItem(key: string, value: string): void {
    this.store.set(key, value)
  }

  /**
   * 删除键值。
   *
   * @param key 键。
   */
  removeItem(key: string): void {
    this.store.delete(key)
  }
}

describe('capabilities/theme · 主题解析', () => {
  it('默认亮色；品牌默认模式作为用户未设置时的回落', () => {
    const theme = new Theme()
    expect(theme.resolved).toBe('light')
    expect(theme.canUseDark).toBe(true)
    expect(theme.displayMode).toBe('light')

    theme.setBrand({ defaultMode: 'dark' })
    expect(theme.resolved).toBe('dark')

    theme.setMode('light')
    expect(theme.resolved).toBe('light')
  })

  it('system 随系统偏好联动；followSystem 为假时不改已应用主题', () => {
    const theme = new Theme()
    theme.setMode('system')
    theme.setSystemPrefersDark(true)
    expect(theme.resolved).toBe('dark')
    expect(theme.theme).toBe('dark')

    theme.followSystem = false
    theme.setSystemPrefersDark(false)
    expect(theme.theme).toBe('dark')
    expect(theme.resolved).toBe('light')
  })

  it('禁用暗色强制亮色并收窄展示模式', () => {
    const theme = new Theme()
    theme.setBrand({ defaultMode: 'dark', disableDark: true })
    theme.setMode('dark')
    expect(theme.resolved).toBe('light')
    expect(theme.canUseDark).toBe(false)
    expect(theme.displayMode).toBe('light')
  })

  it('强调色仅在品牌允许时生效；主色优先品牌、其次令牌、最后平台默认', () => {
    const theme = new Theme()
    theme.setAccent('#ff0000')
    expect(theme.primary).toBe('#1677ff')

    theme.setBrand({ primaryColor: '#00ff00', allowUserAccent: true })
    expect(theme.primary).toBe('#ff0000')

    theme.setAccent('#ff0000')
    theme.setBrand({ primaryColor: 'bad', allowUserAccent: false })
    expect(theme.primary).toBe('#1677ff')

    theme.setTokens({ colors: { primary: '#00ff00' } })
    expect(theme.primary).toBe('#00ff00')
  })

  it('品牌令牌六项齐全且随主色变化', () => {
    const theme = new Theme()
    theme.setBrand({ primaryColor: '#1677ff' })
    const tokens = theme.brandTokens
    expect(Object.keys(tokens)).toHaveLength(6)
    expect(tokens['--bms-color-primary']).toBe('#1677ff')

    theme.setBrand({ primaryColor: '#00ff00' })
    expect(theme.brandTokens['--bms-color-primary']).toBe('#00ff00')
    expect(theme.brandTokens['--bms-color-primary-hover']).not.toBe('#00ff00')
  })
})

describe('capabilities/theme · 应用与持久化', () => {
  it('模式变更联动设计令牌主题订阅（同值不重复通知）', () => {
    const theme = new Theme()
    const seen: string[] = []
    theme.onThemeChange((value) => seen.push(value))

    theme.setMode('dark')
    expect(theme.theme).toBe('dark')
    expect(seen).toEqual(['dark'])

    theme.setMode('dark')
    expect(seen).toEqual(['dark'])
  })

  it('亮暗互切（system 下切到与解析结果相反的一侧）', () => {
    const theme = new Theme()
    theme.setMode('system')
    theme.setSystemPrefersDark(true)
    expect(theme.toggle()).toBe('light')
    expect(theme.mode).toBe('light')

    expect(theme.toggle()).toBe('dark')
    expect(theme.mode).toBe('dark')
  })

  it('接入偏好通道读取 themeMode，并把模式写回同一真源', () => {
    const persisted = new Persisted()
    persisted.storage = new MemoryStorage()
    persisted.stateKey = 'bms_preferences'
    persisted.setLocal({ themeMode: 'dark', locale: 'zh-CN' })
    expect(persisted.persist()).toBe(true)

    const theme = new Theme()
    theme.attachPersisted(persisted)
    expect(theme.mode).toBe('dark')
    expect(theme.resolved).toBe('dark')

    theme.setMode('light')
    expect(persisted.local).toEqual({ themeMode: 'light', locale: 'zh-CN' })
    persisted.restore()
    expect(persisted.local).toEqual({ themeMode: 'light', locale: 'zh-CN' })
  })

  it('偏好通道未写入值时可写回（构造仅含 themeMode 的载荷）', () => {
    const persisted = new Persisted()
    persisted.storage = new MemoryStorage()
    persisted.stateKey = 'bms_preferences'

    const theme = new Theme()
    theme.attachPersisted(persisted)
    expect(theme.mode).toBe('light')
    expect(theme.syncPersisted()).toBe(true)
    expect(persisted.local).toEqual({ themeMode: 'light' })

    theme.setMode('dark')
    expect(persisted.local).toEqual({ themeMode: 'dark' })
  })

  it('能力依赖登记包含 theme 且无环', () => {
    expect(validateCapabilityGraph()).toEqual([])
  })
})
