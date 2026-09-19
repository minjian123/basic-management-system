/**
 * 主题与品牌能力基类：模式解析（用户 > 租户默认 > 平台默认）/ 系统偏好联动 / 品牌注入 / 品牌色派生。
 *
 * 在设计令牌能力基类 `BaseDesignToken` 之上派生：令牌消费是底座，主题与品牌在其上加层。
 * **不含渲染语义与 DOM 操作**（根元素属性、品牌 CSS 变量、标题 / favicon 由件层写入）。
 */

import { BaseDesignToken } from './design-token'
import {
  DEFAULT_BRAND_PRIMARY,
  deriveBrandTokens,
  isValidColor,
  normalizeBrand,
  parseColor,
  resolveThemeMode,
  toHex,
  type BrandTokenMap,
} from '../domain/brand'
import type { BasePersistedState } from './persisted-state'

/** 主题模式（用户选择）。 */
export type ThemeMode = 'light' | 'dark' | 'system'

/** 有效主题（解析结果）。 */
export type ResolvedTheme = 'light' | 'dark'

/** 租户品牌配置（未配置时用平台默认）。 */
export interface BrandConfig {
  /** 品牌名称（页面标题 / 侧栏 / 登录页）。 */
  name?: string
  /** Logo 地址。 */
  logo?: string
  /** favicon 地址。 */
  favicon?: string
  /** 品牌主色。 */
  primaryColor?: string
  /** 租户默认主题模式。 */
  defaultMode?: ThemeMode
  /** 登录页背景图。 */
  loginBg?: string
  /** 是否允许用户覆盖强调色。 */
  allowUserAccent?: boolean
  /** 是否禁用暗色。 */
  disableDark?: boolean
}

/** 判断是否为普通对象。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 判断是否为合法主题模式。 */
function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'light' || value === 'dark' || value === 'system'
}

/**
 * 归一颜色为十六进制（非法回退平台默认主色）。
 *
 * @param input 颜色字符串。
 * @returns 十六进制颜色。
 */
function normalizeColorHex(input: string): string {
  const parsed = parseColor(input)
  return parsed === undefined ? DEFAULT_BRAND_PRIMARY : toHex(parsed)
}

/** 主题与品牌能力基类（抽象）。 */
export abstract class BaseTheme extends BaseDesignToken {
  /** 能力键。 */
  readonly identifier: string = 'theme'
  /** 用户主题模式（真源：用户偏好 `themeMode`）。 */
  mode: ThemeMode = 'light'
  /** 租户品牌配置。 */
  brand: BrandConfig | undefined
  /** 用户强调色（仅在品牌允许时生效）。 */
  accent: string | undefined
  /** 是否监听系统偏好。 */
  followSystem = true
  /** 系统是否偏好暗色（由投影层写入）。 */
  systemPrefersDark = false
  /** 偏好持久化通道（`themeMode` 真源）。 */
  persisted: BasePersistedState | undefined
  /** 用户是否显式设置过模式（未设置时回落到租户默认 / 平台默认）。 */
  private userChosen = false

  /** 有效主题（解析优先级：用户模式 > 租户默认模式 > 平台默认）。 */
  get resolved(): ResolvedTheme {
    return resolveThemeMode({
      mode: this.userChosen ? this.mode : undefined,
      systemPrefersDark: this.systemPrefersDark,
      defaultMode: this.brand?.defaultMode,
      disableDark: this.brand?.disableDark,
    })
  }

  /** 是否允许暗色（品牌可禁用）。 */
  get canUseDark(): boolean {
    return this.brand?.disableDark !== true
  }

  /** 展示用模式（禁用暗色时 `system` 亦归一亮色展示）。 */
  get displayMode(): ThemeMode {
    return this.canUseDark ? this.mode : 'light'
  }

  /** 有效主色（用户强调色 ∩ 品牌允许 > 品牌主色 > 令牌默认 > 平台默认）。 */
  get primary(): string {
    if (this.accent !== undefined && this.brand?.allowUserAccent === true && isValidColor(this.accent)) {
      return normalizeColorHex(this.accent)
    }
    const brandColor = this.brand?.primaryColor
    if (brandColor !== undefined && isValidColor(brandColor)) {
      return normalizeColorHex(brandColor)
    }
    const tokenColor = this.tokens.colors?.primary
    if (typeof tokenColor === 'string' && isValidColor(tokenColor)) {
      return normalizeColorHex(tokenColor)
    }
    return DEFAULT_BRAND_PRIMARY
  }

  /** 品牌派生令牌（CSS 变量名 → 值）。 */
  get brandTokens(): BrandTokenMap {
    return deriveBrandTokens(this.primary)
  }

  /**
   * 设置用户主题模式（写用户偏好并即时生效）。
   *
   * @param mode 主题模式。
   * @returns 有效主题。
   */
  setMode(mode: ThemeMode): ResolvedTheme {
    this.mode = mode
    this.userChosen = true
    this.syncPersisted()
    return this.resolve()
  }

  /**
   * 设置租户品牌（归一后即时生效）。
   *
   * @param brand 品牌配置（`undefined` 表示用平台默认）。
   * @returns 有效主题。
   */
  setBrand(brand?: BrandConfig): ResolvedTheme {
    this.brand = brand === undefined ? undefined : normalizeBrand(brand)
    return this.resolve()
  }

  /**
   * 设置用户强调色（仅在品牌允许时参与主色）。
   *
   * @param color 强调色（空串 / `undefined` 表示清除）。
   * @returns 有效主题。
   */
  setAccent(color?: string): ResolvedTheme {
    this.accent = color === undefined || color === '' ? undefined : color
    return this.resolve()
  }

  /**
   * 写入系统偏好（`followSystem` 且模式为 `system` 时联动主题）。
   *
   * @param value 系统是否偏好暗色。
   * @returns 有效主题。
   */
  setSystemPrefersDark(value: boolean): ResolvedTheme {
    this.systemPrefersDark = value
    if (this.followSystem && this.mode === 'system') {
      return this.resolve()
    }
    return this.resolved
  }

  /**
   * 接入偏好持久化通道（读取偏好中的 `themeMode` 并落模式）。
   *
   * @param persisted 偏好持久化能力。
   * @returns 有效主题。
   */
  attachPersisted(persisted: BasePersistedState): ResolvedTheme {
    this.persisted = persisted
    persisted.restore()
    const local = persisted.local
    if (isRecord(local) && isThemeMode(local.themeMode)) {
      this.mode = local.themeMode
      this.userChosen = true
    }
    return this.resolve()
  }

  /**
   * 把当前模式写回偏好（与偏好面板同一真源）。
   *
   * @returns 是否写入本地存储成功。
   */
  syncPersisted(): boolean {
    if (this.persisted === undefined) {
      return false
    }
    const local = this.persisted.local
    const next = isRecord(local) ? { ...local, themeMode: this.mode } : { themeMode: this.mode }
    this.persisted.setLocal(next)
    return this.persisted.persist()
  }

  /**
   * 亮暗互切（`system` 下切到与解析结果相反的一侧）。
   *
   * @returns 有效主题。
   */
  toggle(): ResolvedTheme {
    return this.setMode(this.resolved === 'dark' ? 'light' : 'dark')
  }

  /**
   * 重算并应用主题（幂等：值未变不触发通知）。
   *
   * @returns 有效主题。
   */
  resolve(): ResolvedTheme {
    const next = this.resolved
    this.setTheme(next)
    return next
  }
}
