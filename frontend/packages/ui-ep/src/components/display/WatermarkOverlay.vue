<script setup lang="ts">
// 水印容器（07_02）：平铺水印（文字 / 图片），旋转 / 间距 / 透明度 / 全屏或局部，防篡改自动恢复。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseWatermark } from '../../composables/useBaseWatermark'

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
  /** 整体透明度。 */
  opacity?: number
  /** 旋转角度。 */
  rotate?: number
  /** 间距 [水平, 垂直]。 */
  gap?: number[]
  /** 偏移 [水平, 垂直]。 */
  offset?: number[]
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
  color: '#909399',
  opacity: 0.15,
  rotate: -22,
  gap: () => [100, 100],
  offset: () => [0, 0],
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
  const texts = lines.value
    .map((line, index) => {
      const x = gapX / 2
      const y = gapY / 2 + index * 16
      return `<text x="${x}" y="${y}" font-size="14" text-anchor="middle" fill="${props.color}">${escapeXml(line)}</text>`
    })
    .join('')
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${gapX}" height="${gapY}">` +
    `<g transform="rotate(${props.rotate} ${gapX / 2} ${gapY / 2})">${texts}</g></svg>`
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`
})

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
let observer: MutationObserver | undefined
let timeTimer: ReturnType<typeof setInterval> | undefined

function restoreLayer(): void {
  if (containerEl.value && layerEl.value && layerEl.value.parentNode !== containerEl.value) {
    containerEl.value.appendChild(layerEl.value)
  }
}

onMounted(() => {
  if (typeof MutationObserver !== 'undefined' && containerEl.value) {
    observer = new MutationObserver(() => restoreLayer())
    observer.observe(containerEl.value, { childList: true, subtree: true })
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
  observer?.disconnect()
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
