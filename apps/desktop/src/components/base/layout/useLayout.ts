/**
 * 布局片段（`layout`）：栅格与断点、间距与对齐、布局根元素与显隐。
 *
 * 契约见《组件设计 · 布局片段》：`span` / `offset` / `gap` / `align` / `justify` / `wrap` /
 * `responsive` + 断点感知；布局根元素属性透传与显隐。
 * **组合依赖**：`design-token`（间距取令牌、断点取令牌口径）。**占位**：读不到令牌时按 `gap` 步数计算像素。
 */

import { computed, onScopeDispose, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import { useDesignToken } from '../design-token/useDesignToken'

/** 布局片段参数 */
export interface UseLayoutOptions {
  /** 栅格跨度（1 ~ columns） */
  span?: MaybeRefOrGetter<number>
  /** 栅格偏移 */
  offset?: MaybeRefOrGetter<number>
  /** 栅格列数（默认 24） */
  columns?: MaybeRefOrGetter<number>
  /** 间距步数（走设计令牌 `--bms-space-<n>`；读不到按 4px 步进） */
  gap?: MaybeRefOrGetter<number>
  align?: MaybeRefOrGetter<'start' | 'center' | 'end' | 'stretch' | 'baseline'>
  justify?: MaybeRefOrGetter<'start' | 'center' | 'end' | 'space-between' | 'space-around'>
  wrap?: MaybeRefOrGetter<boolean>
  /** 是否响应式（按断点切列数：`sm` 1 列 / `md` 2 列 / `lg` 全列） */
  responsive?: MaybeRefOrGetter<boolean>
  visible?: MaybeRefOrGetter<boolean>
}

/** 布局片段返回值 */
export interface UseLayoutReturn {
  readonly span: number
  readonly offset: number
  readonly gapValue: string
  readonly isVisible: boolean
  readonly breakpoint: string
  readonly density: string
  /** 布局根属性（`data-span` / `data-offset` / `data-breakpoint`） */
  readonly layoutAttrs: Record<string, string | number>
  /** 布局根样式（间距 / 对齐 / 换行） */
  readonly layoutStyle: Record<string, string>
  /** 断点变化订阅（透传设计令牌片段的主题观察）；返回取消函数 */
  onBreakpointChange: (cb: (breakpoint: string) => void) => () => void
}

/**
 * 获取布局能力。
 *
 * 用法：`const layout = useLayout({ span: 12, gap: 4 })`；模板把 `layoutAttrs` / `layoutStyle` 透传到布局根元素。
 */
export function useLayout(options: UseLayoutOptions = {}): UseLayoutReturn {
  declareFragment('layout')

  const token = useDesignToken()
  const breakpoint = ref(token.currentBreakpoint)

  const span = computed(() => Math.max(1, Number(toValue(options.span) ?? Number(toValue(options.columns) ?? 24))))
  const offset = computed(() => Math.max(0, Number(toValue(options.offset) ?? 0)))
  const gapSteps = computed(() => Number(toValue(options.gap) ?? 0))
  const gapValue = computed(() => (gapSteps.value > 0 ? token.spacing(gapSteps.value) : '0'))
  const isVisible = computed(() => options.visible === undefined || Boolean(toValue(options.visible)))

  const cancel = token.onThemeChange(() => {
    breakpoint.value = token.currentBreakpoint
  })
  onScopeDispose(() => cancel())

  const layoutStyle = computed<Record<string, string>>(() => {
    const style: Record<string, string> = { gap: gapValue.value }
    const align = toValue(options.align)
    const justify = toValue(options.justify)
    if (align !== undefined) {
      style.alignItems = align === 'start' || align === 'end' ? `flex-${align}` : align
    }
    if (justify !== undefined) {
      style.justifyContent = justify === 'start' || justify === 'end' ? `flex-${justify}` : justify
    }
    if (toValue(options.wrap) !== undefined) {
      style.flexWrap = toValue(options.wrap) ? 'wrap' : 'nowrap'
    }
    return style
  })

  return {
    get span() {
      return span.value
    },
    get offset() {
      return offset.value
    },
    get gapValue() {
      return gapValue.value
    },
    get isVisible() {
      return isVisible.value
    },
    get breakpoint() {
      return breakpoint.value
    },
    get density() {
      return token.density
    },
    get layoutAttrs() {
      return {
        'data-span': span.value,
        'data-offset': offset.value,
        'data-breakpoint': breakpoint.value,
        'data-responsive': toValue(options.responsive) === true ? 'true' : 'false',
      }
    },
    get layoutStyle() {
      return layoutStyle.value
    },
    onBreakpointChange: (cb) =>
      token.onThemeChange(() => {
        breakpoint.value = token.currentBreakpoint
        cb(token.currentBreakpoint)
      }),
  }
}
