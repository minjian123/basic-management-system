<script setup lang="ts">
// 二维码（07_02）：按内容/容错级别生成，支持颜色 / logo / 下载 / 复制与过期刷新。
// 扫码登录仅 UI（状态展示 + 过期遮罩），轮询与换取会话随认证阶段。
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'

/** 容错级别。 */
export type QrLevel = 'L' | 'M' | 'Q' | 'H'
/** 二维码状态。 */
export type QrStatus = 'active' | 'expired' | 'scanning' | 'confirmed' | 'failed'

interface Props {
  /** 编码内容（URL / 文本）。 */
  value?: string
  /** 尺寸（px）。 */
  size?: number
  /** 容错级别。 */
  level?: QrLevel
  /** 前景色（设计令牌）。 */
  fgColor?: string
  /** 背景色（设计令牌，不可透明）。 */
  bgColor?: string
  /** 居中 logo 图片地址。 */
  logo?: string
  /** 是否可下载。 */
  downloadable?: boolean
  /** 是否可复制内容。 */
  copyable?: boolean
  /** 状态（扫码登录用）。 */
  status?: QrStatus
  /** 有效期（秒，0 = 不自动过期）。 */
  expiresIn?: number
}

const props = withDefaults(defineProps<Props>(), {
  value: '',
  size: 160,
  level: 'M',
  fgColor: '',
  bgColor: '',
  logo: '',
  downloadable: true,
  copyable: true,
  status: 'active',
  expiresIn: 0,
})

const emit = defineEmits<{
  refresh: []
  download: [dataUrl: string]
  copy: [value: string]
  'status-change': [status: QrStatus]
}>()

const { value: encoded, setValue } = useBaseDisplay<string>()
const dataUrl = ref('')
const error = ref('')
const currentStatus = ref<QrStatus>(props.status)
let expiryTimer: ReturnType<typeof setTimeout> | undefined

function clearExpiry(): void {
  if (expiryTimer !== undefined) {
    clearTimeout(expiryTimer)
    expiryTimer = undefined
  }
}

function setStatus(status: QrStatus): void {
  if (currentStatus.value !== status) {
    currentStatus.value = status
    emit('status-change', status)
  }
}

function startExpiry(): void {
  clearExpiry()
  if (props.expiresIn > 0) {
    expiryTimer = setTimeout(() => {
      setStatus('expired')
    }, props.expiresIn * 1000)
  }
}

async function generate(): Promise<void> {
  const text = props.value
  if (text === '') {
    dataUrl.value = ''
    error.value = ''
    return
  }
  try {
    const { default: QRCode } = await import('qrcode')
    const color: { dark?: string; light?: string } = {}
    if (props.fgColor !== '') {
      color.dark = props.fgColor
    }
    if (props.bgColor !== '') {
      color.light = props.bgColor
    }
    dataUrl.value = await QRCode.toDataURL(text, {
      width: props.size,
      margin: 1,
      errorCorrectionLevel: props.level,
      color: Object.keys(color).length > 0 ? color : undefined,
    })
    error.value = ''
    setStatus('active')
    startExpiry()
  } catch {
    error.value = '二维码生成失败'
    setStatus('failed')
  }
}

watch(
  () => props.value,
  (next) => {
    setValue(next)
    void generate()
  },
  { immediate: true },
)

watch(
  () => props.status,
  (next) => {
    currentStatus.value = next
  },
)

onBeforeUnmount(clearExpiry)

const hasContent = computed(() => encoded.value !== undefined && encoded.value !== '')

function refresh(): void {
  emit('refresh')
  setStatus('active')
  void generate()
}

function download(): void {
  if (dataUrl.value === '') {
    return
  }
  emit('download', dataUrl.value)
  if (typeof document !== 'undefined') {
    try {
      const anchor = document.createElement('a')
      anchor.href = dataUrl.value
      anchor.download = `qrcode-${Date.now()}.png`
      anchor.click()
    } catch {
      // 非浏览器环境或下载不可用时忽略（数据地址已随事件上报）
    }
  }
}

async function copy(): Promise<void> {
  if (encoded.value === undefined) {
    return
  }
  emit('copy', encoded.value)
  try {
    await navigator.clipboard?.writeText(encoded.value)
  } catch {
    // 剪贴板不可用时忽略（宿主可另行处理）
  }
}
</script>

<template>
  <div class="bms-qr-code" :data-status="currentStatus" :data-test="'qr-code'">
    <div v-if="!hasContent" class="bms-qr-code__empty" data-test="qr-empty">请输入内容</div>
    <template v-else>
      <div class="bms-qr-code__canvas">
        <img v-if="dataUrl !== ''" :src="dataUrl" alt="二维码" data-test="qr-image" />
        <div v-else-if="error !== ''" data-test="qr-error">{{ error }}</div>
        <div v-else data-test="qr-loading">生成中…</div>
        <img v-if="logo !== ''" class="bms-qr-code__logo" :src="logo" alt="logo" data-test="qr-logo" />
        <div v-if="currentStatus === 'expired'" class="bms-qr-code__mask" data-test="qr-expired">
          <slot name="expired"><span>二维码已过期</span></slot>
          <button type="button" data-test="qr-refresh" @click="refresh">刷新</button>
        </div>
      </div>
      <div class="bms-qr-code__actions">
        <button v-if="downloadable" type="button" data-test="qr-download" @click="download">下载</button>
        <button v-if="copyable" type="button" data-test="qr-copy" @click="copy">复制</button>
      </div>
    </template>
  </div>
</template>
