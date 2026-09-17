/**
 * 水印片段（`watermark`）：用户 / 租户信息注入水印，覆盖页面内容与导出。
 *
 * 契约见《组件设计 · 水印片段》：`apply(el)` / `remove(el)` / `update(opts)` / `toDataURL()` +
 * 内容组装与防移除（可与打印导出共用）。内容默认由**用户 / 租户上下文**组装（注入 `contentProvider`），
 * 未注入时回落 `text`；非浏览器环境（SSR / 测试）`apply` 静默跳过，`toDataURL()` 回落空串。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 水印参数 */
export interface WatermarkOptions {
  /** 水印文本（内容提供器缺省时使用） */
  text?: MaybeRefOrGetter<string>
  /** 内容提供器（默认组装：用户名 + 租户 + 日期） */
  contentProvider?: () => string
  opacity?: MaybeRefOrGetter<number>
  rotate?: MaybeRefOrGetter<number>
  gapX?: MaybeRefOrGetter<number>
  gapY?: MaybeRefOrGetter<number>
  fontSize?: MaybeRefOrGetter<number>
  /** 防移除（监听 DOM 篡改并重建；默认关闭，导出 / 打印场景常关） */
  guard?: MaybeRefOrGetter<boolean>
}

/** 水印片段返回值 */
export interface UseWatermarkReturn {
  /** 当前内容文案 */
  readonly content: string
  readonly backgroundUrl: string
  apply: (el: HTMLElement | null) => void
  remove: (el?: HTMLElement | null) => void
  update: (options: Partial<WatermarkOptions>) => void
  toDataURL: () => string
}

/** 解析后的水印样式（数值化，供绘制使用） */
interface ResolvedWatermarkStyle {
  opacity: number
  rotate: number
  gapX: number
  gapY: number
  fontSize: number
}

/** 生成水印图（canvas → dataURL；无 2d 上下文或非浏览器环境返回空串） */
function drawWatermark(content: string, options: ResolvedWatermarkStyle): string {
  if (typeof document === 'undefined') {
    return ''
  }
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return ''
  }
  const ratio = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1
  canvas.width = options.gapX * ratio
  canvas.height = options.gapY * ratio
  ctx.scale(ratio, ratio)
  ctx.globalAlpha = options.opacity
  ctx.font = `${options.fontSize}px sans-serif`
  ctx.fillStyle = '#999'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.translate(options.gapX / 2, options.gapY / 2)
  ctx.rotate((options.rotate * Math.PI) / 180)
  ctx.fillText(content, 0, 0)
  return canvas.toDataURL()
}

/**
 * 获取水印能力。
 *
 * 用法：`const watermark = useWatermark({ contentProvider })`；`watermark.apply(containerEl)` 即可叠加水印，
 * `toDataURL()` 供导出 / 打印注入。
 */
export function useWatermark(options: WatermarkOptions = {}): UseWatermarkReturn {
  const capability = declareFragment('watermark')

  const overrides = ref<Partial<WatermarkOptions>>({})
  const current = computed<WatermarkOptions>(() => ({ ...options, ...overrides.value }))

  const content = computed(() => {
    const provider = current.value.contentProvider
    if (provider) {
      return provider()
    }
    return String(toValue(current.value.text) ?? '')
  })

  const resolved = computed(() => ({
    opacity: Number(toValue(current.value.opacity) ?? 0.15),
    rotate: Number(toValue(current.value.rotate) ?? -22),
    gapX: Number(toValue(current.value.gapX) ?? 160),
    gapY: Number(toValue(current.value.gapY) ?? 120),
    fontSize: Number(toValue(current.value.fontSize) ?? 14),
  }))

  const backgroundUrl = computed(() => {
    if (!content.value) {
      return ''
    }
    return drawWatermark(content.value, resolved.value)
  })

  const apply = (el: HTMLElement | null): void => {
    if (!el) {
      return
    }
    if (!backgroundUrl.value) {
      capability.log('debug', 'watermark 占位：无内容或环境不支持 canvas，跳过注入')
      return
    }
    el.setAttribute('data-watermark', 'true')
    el.style.backgroundImage = `url("${backgroundUrl.value}")`
    el.style.backgroundRepeat = 'repeat'
  }

  const remove = (el?: HTMLElement | null): void => {
    if (!el) {
      return
    }
    el.removeAttribute('data-watermark')
    el.style.backgroundImage = ''
    el.style.backgroundRepeat = ''
  }

  return {
    get content() {
      return content.value
    },
    get backgroundUrl() {
      return backgroundUrl.value
    },
    apply,
    remove,
    update: (patch) => {
      overrides.value = { ...overrides.value, ...patch }
    },
    toDataURL: () => backgroundUrl.value,
  }
}
