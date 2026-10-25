/** 设计令牌投影：把核心设计令牌能力基类 `BaseDesignToken` 投影为组合式（令牌 / 主题）。 */

import { BaseDesignToken, type DesignTokens } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体设计令牌（可实例化）。 */
class TokenState extends BaseDesignToken {}

/** 选项。 */
export interface UseBaseDesignTokenOptions {
  /** 初始令牌集。 */
  tokens?: Partial<DesignTokens>
  /** 初始主题。 */
  theme?: string
}

/** `useBaseDesignToken` 返回面。 */
export interface UseBaseDesignTokenResult {
  /** 设计令牌基类实例。 */
  designToken: BaseDesignToken
  /** 当前令牌集（响应式）。 */
  tokens: Ref<Readonly<Partial<DesignTokens>>>
  /** 当前主题（响应式）。 */
  theme: Ref<string>
  /** 注入令牌集。 */
  setTokens: (tokens: Partial<DesignTokens>) => void
  /** 切换主题。 */
  setTheme: (theme: string) => void
  /** 订阅主题变更。 */
  onThemeChange: (listener: (theme: string) => void) => () => void
}

/**
 * 使用设计令牌投影。
 *
 * @param options 选项。
 * @returns 设计令牌基类实例与响应式面。
 */
export function useBaseDesignToken(options: UseBaseDesignTokenOptions = {}): UseBaseDesignTokenResult {
  const designToken = new TokenState()
  if (options.tokens !== undefined) {
    designToken.setTokens(options.tokens)
  }
  if (options.theme !== undefined) {
    designToken.setTheme(options.theme)
  }

  const tokens = ref<Readonly<Partial<DesignTokens>>>(designToken.tokens)
  const theme = ref(designToken.theme)
  const off = designToken.onLifecycle((event) => {
    if (event === 'update') {
      tokens.value = designToken.tokens
      theme.value = designToken.theme
    }
  })
  onScopeDispose(off)

  return {
    designToken,
    tokens,
    theme,
    setTokens: (next) => designToken.setTokens(next),
    setTheme: (next) => designToken.setTheme(next),
    onThemeChange: (listener) => designToken.onThemeChange(listener),
  }
}
