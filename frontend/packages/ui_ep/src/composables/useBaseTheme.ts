/** 主题与品牌投影：把核心主题能力基类 `BaseTheme` 投影为组合式（模式 / 解析 / 品牌令牌 / 系统监听 / 根元素注入）。 */

import {
  BaseTheme,
  type BasePersistedState,
  type BrandConfig,
  type ResolvedTheme,
  type ThemeMode,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

import { matchesMedia, onMediaChange as subscribeMediaChange, supportsMediaQuery } from '../utils/media'

/** 具体主题件（可实例化）。 */
class Theme extends BaseTheme {}

/** 选项。 */
export interface UseBaseThemeOptions {
  /** 初始用户模式（缺省读偏好或回落到租户 / 平台默认）。 */
  mode?: ThemeMode
  /** 租户品牌配置。 */
  brand?: BrandConfig
  /** 是否监听系统偏好（缺省 `true`）。 */
  followSystem?: boolean
  /** 偏好持久化通道（`themeMode` 真源）。 */
  persisted?: BasePersistedState
  /** 系统偏好媒体查询（缺省 `(prefers-color-scheme: dark)`）。 */
  mediaQuery?: string
  /** 根元素注入时是否设置文档标题（缺省 `true`）。 */
  applyTitle?: boolean
  /** 根元素注入时是否设置 favicon（缺省 `true`）。 */
  applyFavicon?: boolean
}

/** `useBaseTheme` 返回面。 */
export interface UseBaseThemeResult {
  /** 主题基类实例。 */
  theme: BaseTheme
  /** 用户模式（响应式）。 */
  mode: Ref<ThemeMode>
  /** 有效主题（响应式）。 */
  resolved: Ref<ResolvedTheme>
  /** 有效主色（响应式）。 */
  primary: Ref<string>
  /** 品牌派生令牌（响应式）。 */
  brandTokens: Ref<Record<string, string>>
  /** 是否允许暗色（响应式）。 */
  canUseDark: Ref<boolean>
  /** 展示用模式（响应式）。 */
  displayMode: Ref<ThemeMode>
  /** 设置用户模式。 */
  setMode: (mode: ThemeMode) => ResolvedTheme
  /** 设置租户品牌。 */
  setBrand: (brand?: BrandConfig) => ResolvedTheme
  /** 设置用户强调色。 */
  setAccent: (color?: string) => ResolvedTheme
  /** 亮暗互切。 */
  toggle: () => ResolvedTheme
  /** 应用主题到根元素（`data-theme` + 品牌 CSS 变量 + 标题 / favicon）。 */
  applyToElement: (target?: HTMLElement) => void
  /** 挂载前同步预读（防闪烁），返回有效主题并写入根元素。 */
  preload: () => ResolvedTheme
}

/**
 * 使用主题与品牌投影。
 *
 * @param options 选项。
 * @returns 主题基类实例与响应式面。
 */
export function useBaseTheme(options: UseBaseThemeOptions = {}): UseBaseThemeResult {
  const theme = new Theme()
  theme.followSystem = options.followSystem ?? true
  if (options.persisted !== undefined) {
    // 跨实例基类对象不进入响应式（私有字段经代理读取会失效）。
    theme.persisted = markRaw(toRaw(options.persisted))
  }
  if (options.brand !== undefined) {
    theme.setBrand(options.brand)
  }
  if (options.mode !== undefined) {
    theme.setMode(options.mode)
  } else if (theme.persisted !== undefined) {
    theme.attachPersisted(theme.persisted)
  }

  const mediaQuery = options.mediaQuery ?? '(prefers-color-scheme: dark)'
  if (theme.followSystem && supportsMediaQuery()) {
    theme.setSystemPrefersDark(matchesMedia(mediaQuery))
  }
  const offMedia = theme.followSystem
    ? subscribeMediaChange(mediaQuery, (matches) => {
        theme.setSystemPrefersDark(matches)
      })
    : () => {}
  onScopeDispose(offMedia)

  const mode = ref<ThemeMode>(theme.mode)
  const resolved = ref<ResolvedTheme>(theme.resolved)
  const primary = ref(theme.primary)
  const brandTokens = ref<Record<string, string>>({ ...theme.brandTokens })
  const canUseDark = ref(theme.canUseDark)
  const displayMode = ref<ThemeMode>(theme.displayMode)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    mode.value = theme.mode
    resolved.value = theme.resolved
    primary.value = theme.primary
    brandTokens.value = { ...theme.brandTokens }
    canUseDark.value = theme.canUseDark
    displayMode.value = theme.displayMode
  }

  const off = theme.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  /**
   * 应用主题与品牌到目标元素。
   *
   * @param target 目标元素（缺省 `document.documentElement`）。
   */
  const applyToElement = (target?: HTMLElement): void => {
    const element = target ?? globalThis.document?.documentElement
    if (element === undefined) {
      return
    }
    element.dataset.theme = theme.resolved
    for (const [name, value] of Object.entries(theme.brandTokens)) {
      element.style.setProperty(name, value)
    }
    const doc = globalThis.document
    if (doc === undefined) {
      return
    }
    if (theme.brand?.name !== undefined && options.applyTitle !== false) {
      doc.title = theme.brand.name
    }
    if (theme.brand?.favicon !== undefined && options.applyFavicon !== false) {
      try {
        let link = doc.querySelector<HTMLLinkElement>('link[rel="icon"]')
        if (link === null) {
          link = doc.createElement('link')
          link.rel = 'icon'
          doc.head.appendChild(link)
        }
        link.href = theme.brand.favicon
      } catch {
        // 品牌资源不可用时降级为平台默认（不阻断应用）。
      }
    }
  }

  return {
    theme,
    mode,
    resolved,
    primary,
    brandTokens,
    canUseDark,
    displayMode,
    setMode: (next) => {
      const value = theme.setMode(next)
      sync()
      return value
    },
    setBrand: (brand) => {
      const value = theme.setBrand(brand)
      sync()
      return value
    },
    setAccent: (color) => {
      const value = theme.setAccent(color)
      sync()
      return value
    },
    toggle: () => {
      const value = theme.toggle()
      sync()
      return value
    },
    applyToElement,
    preload: () => {
      const value = theme.resolved
      sync()
      applyToElement()
      return value
    },
  }
}
