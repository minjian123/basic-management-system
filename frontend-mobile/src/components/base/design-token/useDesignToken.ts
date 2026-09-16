/**
 * 设计令牌片段（`design-token`）：间距 / 色板 / 密度 / 断点的统一消费入口。
 *
 * 契约见《组件设计 · 设计令牌片段》：`token(name, fallback?)` / `spacing(n)` / `color(name)` /
 * `density` / `breakpoints` / `onThemeChange(cb)`。
 * 令牌唯一来源为 `src/styles/tokens.scss`（CSS 自定义属性）：本片段**只读**令牌，
 * 不复制值、不硬编码色值与尺寸；非浏览器环境（SSR / 测试）读不到变量时回落 `fallback`。
 */

import { computed, onScopeDispose, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 断点（与《布局设计 · 断点与栅格》一致，单位 px） */
export const BREAKPOINTS = {
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
} as const

/** 设计令牌片段参数 */
export interface UseDesignTokenOptions {
  /** 读不到令牌时的兜底值（可为空串） */
  fallback?: MaybeRefOrGetter<string>
  /** 数值令牌单位（`spacing()` 用，默认 px） */
  unit?: MaybeRefOrGetter<string>
}

/** 设计令牌片段返回值 */
export interface UseDesignTokenReturn {
  /** 读令牌：`token('--bms-density-gap')`；读不到回落 `fallback` */
  token: (name: string, fallback?: string) => string
  /** 间距档位：`spacing(2)` → `var(--bms-space-2, calc(...))` 风格的取值（读不到则用 unit 计算） */
  spacing: (steps: number) => string
  /** 色板：`color('primary')` → `--bms-color-primary` 取值 */
  color: (name: string) => string
  /** 当前密度（读根元素 `data-density`） */
  readonly density: string
  readonly breakpoints: typeof BREAKPOINTS
  /** 当前断点（按视口宽度；非浏览器环境为 `lg`） */
  readonly currentBreakpoint: keyof typeof BREAKPOINTS
  /** 主题变化订阅（`data-theme` / `data-density` 变更时触发）；返回取消函数 */
  onThemeChange: (cb: (theme: string) => void) => () => void
}

/** 读取 CSS 自定义属性（非浏览器 / 读不到返回空串） */
function readToken(name: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return ''
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name)
  return value ? value.trim() : ''
}

/** 当前视口断点 */
function resolveBreakpoint(): keyof typeof BREAKPOINTS {
  if (typeof window === 'undefined') {
    return 'lg'
  }
  const width = window.innerWidth
  if (width >= BREAKPOINTS.xl) {
    return 'xl'
  }
  if (width >= BREAKPOINTS.lg) {
    return 'lg'
  }
  if (width >= BREAKPOINTS.md) {
    return 'md'
  }
  return 'sm'
}

/**
 * 获取设计令牌能力。
 *
 * 用法：`const token = useDesignToken(); token.color('primary')`；组件只消费令牌，不硬编码色值与尺寸。
 */
export function useDesignToken(options: UseDesignTokenOptions = {}): UseDesignTokenReturn {
  declareFragment('design-token')

  const themeVersion = ref(0)
  const fallback = computed(() => String(toValue(options.fallback) ?? ''))

  const token = (name: string, localFallback?: string): string => {
    void themeVersion.value
    const value = readToken(name)
    if (value) {
      return value
    }
    return localFallback ?? fallback.value
  }

  const unit = computed(() => String(toValue(options.unit) ?? 'px'))
  const density = computed(() => {
    void themeVersion.value
    if (typeof document === 'undefined') {
      return 'default'
    }
    return document.documentElement.getAttribute('data-density') ?? 'default'
  })
  const currentBreakpoint = ref(resolveBreakpoint())

  const onThemeChange = (cb: (theme: string) => void): (() => void) => {
    if (typeof document === 'undefined' || typeof MutationObserver === 'undefined') {
      return () => {}
    }
    const observer = new MutationObserver(() => {
      themeVersion.value += 1
      currentBreakpoint.value = resolveBreakpoint()
      cb(document.documentElement.getAttribute('data-theme') ?? 'light')
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-density'] })
    onScopeDispose(() => observer.disconnect())
    return () => observer.disconnect()
  }

  return {
    token,
    spacing: (steps) => {
      const variable = `--bms-space-${steps}`
      const value = readToken(variable)
      if (value) {
        return value
      }
      return fallback.value || `${steps * 4}${unit.value}`
    },
    color: (name) => token(`--bms-color-${name}`),
    get density() {
      return density.value
    },
    breakpoints: BREAKPOINTS,
    get currentBreakpoint() {
      return currentBreakpoint.value
    },
    onThemeChange,
  }
}
