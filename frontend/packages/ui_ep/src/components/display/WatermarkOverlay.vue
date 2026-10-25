<script setup lang="ts">
// 水印容器（07_02）：平铺水印（文字 / 图片），旋转 / 间距 / 透明度 / 全屏或局部，防篡改自动恢复。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseWatermark } from '../../composables/useBaseWatermark'
import { observeChildList } from '../../utils/observe'

/** 水印字体。 */
export interface WatermarkFont {
  /** 字号（px）。 */
  fontSize?: number
  /** 字重。 */
  fontWeight?: number | string
  /** 字体族。 */
  fontFamily?: string
}

interface Props {
  /** 水印文案（一行或多行）；缺省由水印能力组装（用户 / 租户 / 时间）。 */
  content?: string | string[]
  /** 用户信息文本。 */
  user?: string
  /** 租户信息文本。 */
  tenant?: string
  /** 图片水印地址（logo）。 */
  image?: string
  /** 水印颜色（建议传设计令牌值）。 */
  color?: string
  /** 字体（字号 / 字重 / 字体族）。 */
  font?: WatermarkFont
  /** 整体透明度。 */
  opacity?: number
  /** 旋转角度。 */
  rotate?: number
  /** 间距 [水平, 垂直]。 */
  gap?: number[]
  /** 偏移 [水平, 垂直]。 */
  offset?: number[]
  /** 单个水印宽度（缺省取间距水平值）。 */
  width?: number
  /** 单个水印高度（缺省取间距垂直值）。 */
  height?: number
  /** 层级。 */
  zIndex?: number
  /** 是否全屏。 */
  fullscreen?: boolean
  /** 是否包含时间（配合定时刷新）。 */
  showTime?: boolean
  /** 是否启用水印。 */
  enabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: undefined,
  user: '',
  tenant: '',
  image: '',
  color: 'var(--bms-color-text-secondary)',
  font: () => ({}),
  opacity: 0.15,
  rotate: -22,
  gap: () => [100, 100],
  offset: () => [0, 0],
  width: 0,
  height: 0,
  zIndex: 9,
  fullscreen: false,
  showTime: false,
  enabled: true,
})

const emit = defineEmits<{
  ready: []
  change: [lines: string[]]
}>()

const watermark = useBaseWatermark({ user: props.user, tenant: props.tenant })
watch(
  () => props.user,
  (next) => watermark.setUser(next),
)
watch(
  () => props.tenant,
  (next) => watermark.setTenant(next),
)

const timeText = ref('')
function formatNow(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ')
}

const lines = computed<string[]>(() => {
  if (Array.isArray(props.content)) {
    return props.content
  }
  if (typeof props.content === 'string' && props.content !== '') {
    return [props.content]
  }
  const parts = watermark.text.value !== '' ? watermark.text.value.split(' / ') : []
  if (props.showTime) {
    parts.push(timeText.value || formatNow())
  }
  return parts
})

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

const tileUrl = computed(() => {
  const gapX = props.gap[0] ?? 100
  const gapY = props.gap[1] ?? 100
  const tileWidth = props.width > 0 ? props.width : gapX
  const tileHeight = props.height > 0 ? props.height : gapY
  const fontSize = props.font.fontSize ?? 14
  const lineHeight = Math.round(fontSize * 1.15)
  const texts = lines.value
    .map((line, index) => {
      const x = tileWidth / 2
      const y = tileHeight / 2 + index * lineHeight
      return `<text x="${x}" y="${y}" font-size="${fontSize}" font-weight="${props.font.fontWeight ?? 400}" font-family="${escapeXml(props.font.fontFamily ?? '')}" text-anchor="middle" fill="${props.color}">${escapeXml(line)}</text>`
    })
    .join('')
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${tileWidth}" height="${tileHeight}">` +
    `<g transform="rotate(${props.rotate} ${tileWidth / 2} ${tileHeight / 2})">${texts}</g></svg>`
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`
})

/** 平铺水印原始 SVG 文本（导出用）。 */
const tileSvg = computed(() => {
  const url = tileUrl.value
  const start = url.indexOf('utf8,') + 'utf8,'.length
  const end = url.lastIndexOf('")')
  return decodeURIComponent(url.slice(start, end))
})

/**
 * 导出水印平铺图数据地址（SVG）。
 *
 * @returns 数据地址（`data:image/svg+xml;utf8,...`）。
 */
function exportImage(): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(tileSvg.value)}`
}

defineExpose({ exportImage })

const layerStyle = computed<Record<string, string>>(() => {
  const backgrounds = [tileUrl.value]
  if (props.image !== '') {
    backgrounds.push(`url("${props.image}")`)
  }
  return {
    position: props.fullscreen ? 'fixed' : 'absolute',
    inset: '0',
    backgroundImage: backgrounds.join(', '),
    backgroundRepeat: 'repeat',
    backgroundPosition: `${props.offset[0] ?? 0}px ${props.offset[1] ?? 0}px`,
    opacity: String(props.opacity),
    zIndex: String(props.zIndex),
    pointerEvents: 'none',
    userSelect: 'none',
  }
})

const containerEl = ref<HTMLElement>()
const layerEl = ref<HTMLElement>()
let stopObserve: (() => void) | undefined
let timeTimer: ReturnType<typeof setInterval> | undefined

function restoreLayer(): void {
  if (containerEl.value && layerEl.value && layerEl.value.parentNode !== containerEl.value) {
    containerEl.value.appendChild(layerEl.value)
  }
}

onMounted(() => {
  if (containerEl.value) {
    stopObserve = observeChildList(containerEl.value, restoreLayer)
  }
  if (props.showTime) {
    timeText.value = formatNow()
    timeTimer = setInterval(() => {
      timeText.value = formatNow()
      emit('change', lines.value)
    }, 60_000)
  }
  emit('ready')
})

onBeforeUnmount(() => {
  stopObserve?.()
  if (timeTimer !== undefined) {
    clearInterval(timeTimer)
  }
})
</script>

<template>
  <div ref="containerEl" class="bms-watermark" :data-fullscreen="fullscreen || undefined">
    <slot />
    <div
      v-if="enabled"
      ref="layerEl"
      class="bms-watermark__layer"
      data-test="watermark-layer"
      aria-hidden="true"
      :style="layerStyle"
    />
  </div>
</template>

<style scoped>
.bms-watermark {
  position: relative;
  box-sizing: border-box;
}

.bms-watermark[data-fullscreen] {
  position: static;
}

.bms-watermark__layer {
  overflow: hidden;
  pointer-events: none;
  user-select: none;
}
</style>

