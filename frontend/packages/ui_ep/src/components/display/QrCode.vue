<script setup lang="ts">
// 二维码（07_02）：按内容/容错级别生成，支持颜色 / logo / 下载 / 复制与过期刷新。
// 扫码登录仅 UI（状态展示 + 五态遮罩），轮询与换取会话随认证阶段。
import { ElButton } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'
import { triggerDownload } from '../../utils/downloadFile'

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

/**
 * 取当前二维码图片数据地址（未生成返回空串）。
 *
 * @returns 图片数据地址。
 */
function imageData(): string {
  return dataUrl.value
}

defineExpose({ imageData })

function download(): void {
  if (dataUrl.value === '') {
    return
  }
  emit('download', dataUrl.value)
  triggerDownload({ url: dataUrl.value, filename: `qrcode-${Date.now()}.png` })
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
        <img v-if="dataUrl !== ''" class="bms-qr-code__image" :src="dataUrl" alt="二维码" data-test="qr-image" />
        <div v-else-if="error !== ''" class="bms-qr-code__error" data-test="qr-error">{{ error }}</div>
        <div v-else class="bms-qr-code__loading" data-test="qr-loading">生成中…</div>
        <img v-if="logo !== ''" class="bms-qr-code__logo" :src="logo" alt="logo" data-test="qr-logo" />

        <div v-if="currentStatus === 'expired'" class="bms-qr-code__mask" data-test="qr-expired">
          <slot name="expired"><span class="bms-qr-code__mask-text">二维码已过期</span></slot>
          <el-button size="small" type="primary" data-test="qr-refresh" @click="refresh">刷新</el-button>
        </div>
        <div v-else-if="currentStatus === 'scanning'" class="bms-qr-code__mask" data-test="qr-scanning">
          <slot name="scanning"><span class="bms-qr-code__mask-text">已扫码，请在移动端确认</span></slot>
        </div>
        <div
          v-else-if="currentStatus === 'confirmed'"
          class="bms-qr-code__mask is-confirmed"
          data-test="qr-confirmed"
        >
          <slot name="confirmed"><span class="bms-qr-code__mask-text">已确认，正在登录…</span></slot>
        </div>
        <div v-else-if="currentStatus === 'failed'" class="bms-qr-code__mask is-failed" data-test="qr-failed">
          <slot name="failed"><span class="bms-qr-code__mask-text">二维码生成失败</span></slot>
          <el-button size="small" data-test="qr-retry" @click="refresh">重试</el-button>
        </div>
      </div>
      <div class="bms-qr-code__actions">
        <el-button v-if="downloadable" size="small" data-test="qr-download" @click="download">下载</el-button>
        <el-button v-if="copyable" size="small" data-test="qr-copy" @click="copy">复制</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-qr-code {
  display: inline-flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
}

.bms-qr-code__canvas {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--bms-space-2);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-lg);
}

.bms-qr-code__image {
  display: block;
}

.bms-qr-code__logo {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20%;
  height: 20%;
  padding: 2px;
  background: var(--bms-color-bg);
  border-radius: var(--bms-radius-sm);
  transform: translate(-50%, -50%);
}

.bms-qr-code__mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
  justify-content: center;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  background: var(--bms-qr-mask-bg);
  border-radius: var(--bms-radius-lg);
}

.bms-qr-code__mask.is-confirmed {
  color: var(--bms-color-success);
}

.bms-qr-code__mask.is-failed {
  color: var(--bms-color-danger);
}

.bms-qr-code__mask-text {
  padding: 0 var(--bms-space-2);
  text-align: center;
}

.bms-qr-code__empty,
.bms-qr-code__loading,
.bms-qr-code__error {
  padding: var(--bms-space-6) var(--bms-space-4);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  border: 1px dashed var(--bms-color-border);
  border-radius: var(--bms-radius-lg);
}

.bms-qr-code__error {
  color: var(--bms-color-danger);
}

.bms-qr-code__actions {
  display: flex;
  gap: var(--bms-space-2);
  justify-content: center;
}
</style>

