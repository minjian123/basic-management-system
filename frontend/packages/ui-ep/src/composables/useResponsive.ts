/** 响应式断点组合式：断点值取自设计令牌（`BaseDesignToken.breakpoints`），优先 `matchMedia` 监听。 */

import { computed, onScopeDispose, ref, type Ref } from 'vue'

import { useBaseDesignToken } from './useBaseDesignToken'
import { onMediaChange, supportsMediaQuery } from '../utils/media'
import { onWindowResize, viewportWidth } from '../utils/observe'

/** 断点档位（像素）。 */
export interface ResponsiveBreakpoints {
  /** 移动端上限。 */
  mobile: number
  /** 窄屏上限。 */
  narrow: number
  /** 宽屏阈值。 */
  wide: number
}

/** 当前断点名。 */
export type ResponsiveBreakpoint = 'mobile' | 'narrow' | 'wide'

/** 内置缺省断点（可由令牌 / 选项覆盖）。 */
export const DEFAULT_BREAKPOINTS: ResponsiveBreakpoints = { mobile: 768, narrow: 992, wide: 1200 }

/** 选项。 */
export interface UseResponsiveOptions {
  /** 覆盖断点。 */
  breakpoints?: Partial<ResponsiveBreakpoints>
}

/** `useResponsive` 返回面。 */
export interface UseResponsiveResult {
  /** 当前断点（响应式）。 */
  breakpoint: Ref<ResponsiveBreakpoint>
  /** 是否移动端（`< mobile`）。 */
  isMobile: Ref<boolean>
  /** 是否窄屏（`< narrow`）。 */
  isNarrow: Ref<boolean>
  /** 是否宽屏（`>= wide`）。 */
  isWide: Ref<boolean>
  /** 生效断点值。 */
  breakpoints: Ref<ResponsiveBreakpoints>
}

/** 当前视口宽度（非浏览器回退宽屏阈值，保持原口径）。 */
function currentWidth(): number {
  return viewportWidth() || DEFAULT_BREAKPOINTS.wide
}

/**
 * 使用响应式断点。
 *
 * @param options 选项。
 * @returns 断点与派生布尔量。
 */
export function useResponsive(options: UseResponsiveOptions = {}): UseResponsiveResult {
  const token = useBaseDesignToken()
  const breakpoints = computed<ResponsiveBreakpoints>(() => ({
    ...DEFAULT_BREAKPOINTS,
    ...(token.tokens.value.breakpoints ?? {}),
    ...(options.breakpoints ?? {}),
  }))
  const width = ref(currentWidth())

  const cleanups: (() => void)[] = []
  if (supportsMediaQuery()) {
    cleanups.push(
      onMediaChange(`(max-width: ${breakpoints.value.narrow}px)`, () => {
        width.value = currentWidth()
      }),
    )
  } else {
    cleanups.push(
      onWindowResize(() => {
        width.value = currentWidth()
      }),
    )
  }

  const breakpoint = computed<ResponsiveBreakpoint>(() => {
    if (width.value < breakpoints.value.mobile) {
      return 'mobile'
    }
    return width.value < breakpoints.value.narrow ? 'narrow' : 'wide'
  })
  const isMobile = computed(() => breakpoint.value === 'mobile')
  const isNarrow = computed(() => breakpoint.value !== 'wide')
  const isWide = computed(() => breakpoint.value === 'wide')

  onScopeDispose(() => {
    for (const cleanup of cleanups) {
      cleanup()
    }
  })

  return { breakpoint, isMobile, isNarrow, isWide, breakpoints }
}
