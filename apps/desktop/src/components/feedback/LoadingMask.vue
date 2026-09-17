<script setup lang="ts">
/**
 * 内容遮罩 loading：局部刷新时覆盖指定区域（不整页闪烁），支持延时显示防闪。
 *
 * 契约见《组件设计 · 异常与空状态》§6：局部覆盖（缺省）/ `delay` 防闪烁（短请求不显示）/
 * `text` / `fullscreen`；按钮内 loading 用 Element Plus 自带（本组件不重复实现）。
 */

import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, ref, useAttrs, watch } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

const props = withDefaults(
  defineProps<{
    loading?: boolean
    /** 遮罩文案（缺省 i18n `feedback.loading`） */
    text?: string | null
    /** 延时显示（ms，避免闪烁；短请求不显示） */
    delay?: number
    /** 整页遮罩（缺省仅覆盖包裹内容区） */
    fullscreen?: boolean
  }>(),
  { loading: false, text: null, delay: 200, fullscreen: false },
)

const base = useComponentBase({ ns: 'bms', identifier: 'loading-mask' })
const { t } = useI18n()
const attrs = useAttrs()

const visible = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

watch(
  () => props.loading,
  (value) => {
    clearTimer()
    base.setProps({ loading: value })
    if (value) {
      if (props.delay > 0) {
        timer = setTimeout(() => {
          visible.value = true
        }, props.delay)
      } else {
        visible.value = true
      }
    } else {
      visible.value = false
    }
  },
  { immediate: true },
)

onBeforeUnmount(clearTimer)

const maskText = computed(() => props.text ?? t('feedback.loading'))

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('loading-mask'), props.fullscreen && base.nsClass('loading-mask--fullscreen'), cls],
    style: sty,
    ...rest,
  })
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('loading-mask')">
    <slot />
    <div
      v-if="visible"
      :class="base.nsClass('loading-mask-overlay')"
      role="status"
      aria-busy="true"
    >
      <span :class="base.nsClass('loading-mask-spinner')" aria-hidden="true" />
      <span v-if="maskText" :class="base.nsClass('loading-mask-text')">{{ maskText }}</span>
    </div>
  </div>
</template>

<style scoped>
.bms-loading-mask {
  position: relative;
}

.bms-loading-mask-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-2);
  background: color-mix(in srgb, var(--bms-color-bg) 70%, transparent);
}

.bms-loading-mask--fullscreen .bms-loading-mask-overlay {
  position: fixed;
  z-index: 3000;
}

.bms-loading-mask-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--bms-color-border);
  border-top-color: var(--bms-color-primary);
  border-radius: 50%;
  animation: bms-loading-mask-spin 0.8s linear infinite;
}

.bms-loading-mask-text {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

@keyframes bms-loading-mask-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
