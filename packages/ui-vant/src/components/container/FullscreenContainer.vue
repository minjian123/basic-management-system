<script setup lang="ts">
/**
 * 全屏容器（《组件设计 · 全屏容器》）：指定区域 / 整页全屏展示。
 *
 * - 请求 `requestFullscreen()`（`target`：`self` 根元素 / `document` 文档根 / 指定元素）；
 * - `fullscreenchange` 同步状态（含浏览器 Esc 退出）；请求失败 / API 不可用 → **降级铺满**
 *   （根元素固定定位 + `background`）+ `fullscreen-error`，降级态自监听 Esc 退出；
 * - `showTip`：组件生命周期内首次进入显示提示条（i18n），约 3 秒自动隐藏；
 * - `v-model` 受控 + `fullscreen-change` 事件对外同步（含降级态）。
 */

import { computed, onBeforeUnmount, onMounted, ref, useAttrs, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    /** 是否全屏（v-model；含降级态） */
    modelValue?: boolean
    /** 全屏目标：`self` 根元素 / `document` 文档根 / 指定元素 */
    target?: 'self' | 'document' | HTMLElement
    /** 首次进入提示（Esc 退出提示条） */
    showTip?: boolean
    /** 降级铺满背景（令牌消费） */
    background?: string
  }>(),
  {
    modelValue: false,
    target: 'self',
    showTip: true,
    background: 'var(--bms-color-bg)',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'fullscreen-change': [value: boolean]
  'fullscreen-error': [reason: string]
}>()

const { t } = useI18n()
const base = useComponentBase({ ns: 'bms', identifier: 'fullscreen-container' })
const attrs = useAttrs()

const rootRef = ref<HTMLElement | null>(null)
const isFallback = ref(false)
const tipVisible = ref(false)
let tipShown = false
let tipTimer: ReturnType<typeof setTimeout> | null = null

function resolveTarget(): Element | null {
  if (props.target === 'document') {
    return typeof document === 'undefined' ? null : document.documentElement
  }
  if (typeof HTMLElement !== 'undefined' && props.target instanceof HTMLElement) {
    return props.target
  }
  return rootRef.value
}

/** 真实全屏态（`fullscreenchange` 同步；`document` 状态非响应式，故显式缓存） */
const isActive = ref(false)

const isFullscreen = computed(() => isFallback.value || isActive.value)

function updateActive(): void {
  isActive.value = typeof document !== 'undefined' && document.fullscreenElement === resolveTarget()
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [
      base.nsClass('fullscreen-container'),
      isFallback.value && base.nsClass('fullscreen-container--fallback'),
      cls,
    ],
    style: [{ background: isFallback.value ? props.background : undefined }, sty],
    ...rest,
  })
})

function showEnterTip(): void {
  if (tipShown) {
    return
  }
  tipShown = true
  tipVisible.value = true
  tipTimer = setTimeout(() => {
    tipVisible.value = false
    tipTimer = null
  }, 3000)
}

function syncState(value: boolean): void {
  if (props.modelValue !== value) {
    emit('update:modelValue', value)
  }
  emit('fullscreen-change', value)
}

function enterFallback(reason: string): void {
  isFallback.value = true
  emit('fullscreen-error', reason)
  if (props.showTip) {
    showEnterTip()
  }
  syncState(true)
}

async function enter(): Promise<void> {
  if (isFullscreen.value) {
    return
  }
  const target = resolveTarget() as (Element & { requestFullscreen?: () => Promise<void> }) | null
  if (!target || typeof target.requestFullscreen !== 'function') {
    enterFallback('Fullscreen API unavailable')
    return
  }
  try {
    await target.requestFullscreen()
    // 状态经 fullscreenchange 同步（含提示）
    if (props.showTip) {
      showEnterTip()
    }
  } catch (error) {
    enterFallback(error instanceof Error ? error.message : String(error))
  }
}

async function exit(): Promise<void> {
  if (isFallback.value) {
    isFallback.value = false
    syncState(false)
    return
  }
  if (
    typeof document !== 'undefined' &&
    document.fullscreenElement &&
    typeof document.exitFullscreen === 'function'
  ) {
    try {
      await document.exitFullscreen()
    } catch {
      // 忽略退出失败（状态仍以 fullscreenchange 为准）
    }
    return
  }
  syncState(false)
}

function toggle(): void {
  void (isFullscreen.value ? exit() : enter())
}

function onFullscreenChange(): void {
  if (isFallback.value) {
    return
  }
  updateActive()
  syncState(isActive.value)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && isFallback.value) {
    void exit()
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value && !isFullscreen.value) {
      void enter()
    } else if (!value && isFullscreen.value) {
      void exit()
    }
  },
)

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)
  if (props.modelValue) {
    void enter()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  if (tipTimer !== null) {
    clearTimeout(tipTimer)
    tipTimer = null
  }
  if (isFallback.value) {
    isFallback.value = false
  } else if (typeof document !== 'undefined' && document.fullscreenElement === resolveTarget()) {
    void document.exitFullscreen?.()
  }
})

defineExpose({
  enter,
  exit,
  toggle,
  get isFullscreen(): boolean {
    return isFullscreen.value
  },
  get isFallback(): boolean {
    return isFallback.value
  },
})
</script>

<template>
  <div ref="rootRef" v-bind="elAttrs" :class="base.nsClass('fullscreen-container')">
    <div
      v-if="tipVisible"
      :class="base.nsClass('fullscreen-container-tip')"
      aria-live="polite"
      data-testid="fullscreen-tip"
    >
      {{ t('container.fullscreenTip') }}
    </div>
    <slot />
  </div>
</template>

<style scoped>
.bms-fullscreen-container {
  position: relative;
}

.bms-fullscreen-container--fallback {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.bms-fullscreen-container-tip {
  position: absolute;
  top: var(--bms-space-3);
  left: 50%;
  transform: translateX(-50%);
  padding: var(--bms-space-1) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-bg);
  background: color-mix(in srgb, var(--bms-color-text) 78%, transparent);
  border-radius: var(--bms-radius-sm);
  pointer-events: none;
  z-index: 1;
}
</style>
