<script setup lang="ts">
// 滑块验证码件（06_04，自绘）：拖动到缺口位置并采样轨迹（坐标 + 相对毫秒），松手提交后端判定；
// 通过 / 失败自动复位、键盘可操作；前端不做真伪判断；无背景时纯轨道降级。
import {
  CAPTCHA_PASS_TEXT,
  CAPTCHA_PLACEHOLDER_TEXT,
  CAPTCHA_REFRESH_TEXT,
  CAPTCHA_SLIDER_HINT,
  CAPTCHA_SLIDER_RETRY_TEXT,
  CAPTCHA_SLIDER_TOLERANCE,
  parseCaptchaSliderParams,
  type CaptchaScene,
  type CaptchaSourceAdapter,
} from '@bms/core'
import { computed, onScopeDispose, ref, watch } from 'vue'

import { useBaseCaptcha } from '../../composables/useBaseCaptcha'
import { startPointerDrag } from '../../utils/keyboard'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 外部直连背景图（缺省由数据源挑战提供）。 */
  imageUrl?: string
  /** 形态参数原始串（背景与缺口参数）。 */
  payload?: string
  /** 验证码数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 使用场景。 */
  scene?: CaptchaScene
  /** 缺口对齐容差（像素；仅展示校正，不做真伪判断）。 */
  tolerance?: number
  /** 禁用。 */
  disabled?: boolean
  /** 提示文案。 */
  hint?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  imageUrl: '',
  payload: '',
  source: undefined,
  scene: 'login',
  tolerance: CAPTCHA_SLIDER_TOLERANCE,
  disabled: false,
  hint: CAPTCHA_SLIDER_HINT,
  degradeText: CAPTCHA_PLACEHOLDER_TEXT,
})

const emit = defineEmits<{
  pass: []
  fail: [payload: { code?: number; message: string }]
  refresh: []
  loaded: [challengeId: string]
}>()

const api = useBaseCaptcha({
  ready: props.ready,
  kind: 'slider',
  scene: props.scene,
  source: props.source,
  disabled: props.disabled,
  imageUrl: props.imageUrl,
})

/** 轨道元素（拖动宽度测量）。 */
const trackRef = ref<HTMLElement | undefined>(undefined)
/** 拖动位移（0 ~ 100）。 */
const percent = ref(0)
/** 是否拖动中。 */
const dragging = ref(false)
/** 最近一次失败文案（刷新挑战后仍保留提示，供重试入口）。 */
const failedMessage = ref('')
/** 取消在途拖动（主动取消函数）。 */
let cancelDrag: (() => void) | undefined
/** 拖动起点（clientX / 已拖百分比 / 时间戳）。 */
let startX = 0
let startPercent = 0
let startTime = 0

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.scene,
  (next) => api.setScene(next),
)
watch(
  () => props.disabled,
  (next) => api.setOptions({ disabled: next }),
)
watch(
  () => props.imageUrl,
  (next) => {
    if (next !== '') {
      api.setImageUrl(next)
    }
  },
  { immediate: true },
)
watch(
  [() => api.ready.value, () => props.imageUrl],
  ([ready, external]) => {
    if (ready && external === '') {
      void api.loadChallenge()
    }
  },
  { immediate: true },
)

onScopeDispose(() => {
  cancelDrag?.()
})

/** 生效形态参数（外部 prop 优先，缺省取挑战回包）。 */
const sliderParams = computed(() => {
  const payload = props.payload !== '' ? props.payload : api.payload.value
  return parseCaptchaSliderParams(payload)
})

/** 生效背景图（外部 prop 优先，缺省取形态参数 / 挑战图片）。 */
const backgroundUrl = computed(() => {
  if (props.imageUrl !== '') {
    return props.imageUrl
  }
  const params = sliderParams.value
  if (params.background !== undefined && params.background !== '') {
    return params.background
  }
  return api.imageUrl.value
})

/** 缺口位置百分比（缺省居中偏右，仅展示用）。 */
const gapPercent = computed(() => {
  const params = sliderParams.value
  if (params.gapX !== undefined && params.width !== undefined && params.width > 0) {
    return Math.min(90, Math.max(10, Math.round((params.gapX / params.width) * 100)))
  }
  return 80
})

/** 是否通过。 */
const passed = computed(() => api.passed.value)

/** 错误文案（最近失败优先；刷新挑战后仍保留提示）。 */
const errorText = computed(() => {
  if (passed.value) {
    return ''
  }
  return failedMessage.value !== '' ? failedMessage.value : api.errorText.value
})

/** 轨道像素宽度（无布局环境回退 200）。 */
function trackWidth(): number {
  const rect = trackRef.value?.getBoundingClientRect()
  const width = rect === undefined ? 0 : rect.width
  return width > 0 ? width : 200
}

/**
 * 开始拖动（记录起点 + 采样首点）。
 *
 * @param event 指针事件。
 */
function onPointerDown(event: PointerEvent): void {
  if (api.disabled.value || api.verifying.value || passed.value) {
    return
  }
  dragging.value = true
  startX = event.clientX
  startPercent = percent.value
  startTime = Date.now()
  api.clearTrace()
  api.pushTrace({ x: Math.round((percent.value / 100) * trackWidth()), y: 0, t: 0 })
  cancelDrag = startPointerDrag(onPointerMove, onPointerUp)
}

/**
 * 拖动中（更新位移并采样轨迹点）。
 *
 * @param event 指针事件。
 */
function onPointerMove(event: PointerEvent): void {
  if (!dragging.value) {
    return
  }
  const width = trackWidth()
  const delta = ((event.clientX - startX) / width) * 100
  percent.value = Math.min(100, Math.max(0, startPercent + delta))
  api.pushTrace({
    x: Math.round((percent.value / 100) * width),
    y: 0,
    t: Date.now() - startTime,
  })
}

/** 松手提交（位移为 0 视作未拖动）。 */
function onPointerUp(): void {
  dragging.value = false
  cancelDrag?.()
  cancelDrag = undefined
  if (percent.value > 0) {
    void submit()
  }
}

/** 提交轨迹交后端判定（失败自动复位并重新出题）。 */
async function submit(): Promise<void> {
  const ok = await api.submitSlider()
  if (ok) {
    failedMessage.value = ''
    percent.value = 100
    emit('pass')
    return
  }
  const code = api.errorCode.value
  failedMessage.value = api.errorText.value
  percent.value = 0
  api.clearTrace()
  if (code === 20101 || code === 20102) {
    await api.refresh()
  }
  emit('fail', { code, message: failedMessage.value })
}

/**
 * 键盘操作（左右微调、回车 / 空格提交）。
 *
 * @param event 键盘事件。
 */
function onKeydown(event: KeyboardEvent): void {
  if (api.disabled.value || api.verifying.value) {
    return
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    percent.value = Math.min(100, percent.value + 5)
    api.pushTrace({ x: Math.round((percent.value / 100) * trackWidth()), y: 0, t: api.trace.value.length * 20 })
    return
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    percent.value = Math.max(0, percent.value - 5)
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (percent.value > 0) {
      void submit()
    }
  }
}

/** 复位（清位移、轨迹与失败提示，可重试）。 */
function onRetry(): void {
  percent.value = 0
  failedMessage.value = ''
  api.clearTrace()
}

/** 刷新挑战（一次性失效后重取；未注入数据源即零请求）。 */
async function onRefresh(): Promise<void> {
  onRetry()
  emit('refresh')
  const ok = await api.refresh()
  if (ok) {
    emit('loaded', api.challengeId.value)
  }
}
</script>

<template>
  <div class="bms-slider-captcha" :data-ready="api.ready.value" :data-degraded="api.degraded.value" data-test="slider-captcha">
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <div class="bms-slider-captcha__stage">
        <img v-if="backgroundUrl !== ''" class="bms-slider-captcha__bg" :src="backgroundUrl" alt="" />
        <span
          class="bms-slider-captcha__gap"
          :style="{ left: `${gapPercent}%` }"
          data-test="captcha-slider-gap"
        />
      </div>

      <div
        ref="trackRef"
        class="bms-slider-captcha__track"
        :data-pass="passed"
        data-test="captcha-slider-track"
      >
        <div class="bms-slider-captcha__fill" :style="{ width: `${percent}%` }" data-test="captcha-slider-fill" />
        <button
          type="button"
          class="bms-slider-captcha__handle"
          :style="{ left: `${percent}%` }"
          role="slider"
          :aria-valuenow="Math.round(percent)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-disabled="api.disabled.value"
          :disabled="api.disabled.value"
          data-test="captcha-slider-handle"
          @pointerdown.prevent="onPointerDown"
          @keydown="onKeydown"
        >
          {{ dragging ? '拖动中' : '→' }}
        </button>
      </div>

      <p class="bms-slider-captcha__hint">{{ hint }}</p>
      <p v-if="passed" class="bms-slider-captcha__pass" data-test="captcha-slider-pass">{{ CAPTCHA_PASS_TEXT }}</p>
      <p v-else-if="errorText !== ''" class="bms-field-error" data-test="captcha-error">
        {{ errorText }}
        <button type="button" class="bms-slider-captcha__retry" data-test="captcha-slider-retry" @click="onRetry">
          {{ CAPTCHA_SLIDER_RETRY_TEXT }}
        </button>
      </p>
      <button type="button" class="bms-slider-captcha__refresh" data-test="captcha-slider-refresh" @click="onRefresh">
        {{ CAPTCHA_REFRESH_TEXT }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.bms-slider-captcha {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-slider-captcha__stage {
  position: relative;
  height: 40px;
  overflow: hidden;
  background: var(--bms-captcha-slider-track-bg);
  border: 1px solid var(--bms-captcha-border);
  border-radius: var(--bms-radius-md);
}
.bms-slider-captcha__bg {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.bms-slider-captcha__gap {
  position: absolute;
  top: 4px;
  width: 28px;
  height: 32px;
  background: var(--bms-captcha-slider-gap-bg);
  border-radius: var(--bms-radius-sm);
}
.bms-slider-captcha__track {
  position: relative;
  height: 32px;
  background: var(--bms-captcha-slider-track-bg);
  border: 1px solid var(--bms-captcha-border);
  border-radius: var(--bms-radius-md);
}
.bms-slider-captcha__fill {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  background: var(--bms-captcha-slider-bar);
  opacity: 0.35;
  border-radius: var(--bms-radius-md);
}
.bms-slider-captcha__handle {
  position: absolute;
  top: -1px;
  width: 32px;
  height: 32px;
  margin-left: -1px;
  color: var(--bms-color-text);
  background: var(--bms-captcha-slider-handle-bg);
  border: 1px solid var(--bms-captcha-slider-handle-border);
  border-radius: var(--bms-radius-md);
  cursor: grab;
  touch-action: none;
}
.bms-slider-captcha__hint {
  margin: 0;
  color: var(--bms-captcha-countdown-color);
  font-size: 12px;
}
.bms-slider-captcha__pass {
  margin: 0;
  color: var(--bms-captcha-pass-color);
  font-size: 12px;
}
.bms-slider-captcha__retry,
.bms-slider-captcha__refresh {
  margin-left: var(--bms-spacing-sm);
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
.bms-slider-captcha__refresh {
  align-self: flex-start;
  margin-left: 0;
}
</style>
