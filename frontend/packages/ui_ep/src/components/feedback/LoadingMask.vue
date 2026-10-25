<script setup lang="ts">
// 内容遮罩：局部加载遮罩，延迟展示防闪烁。
import { onBeforeUnmount, ref, watch } from 'vue'

import { useFeedback } from '../../composables/useFeedback'

interface Props {
  /** 加载中。 */
  loading: boolean
  /** 延迟展示（毫秒，防闪烁）。 */
  delay?: number
  /** 文案。 */
  text?: string
  /** 整页遮罩（缺省仅覆盖包裹内容区）。 */
  fullscreen?: boolean
}

const props = withDefaults(defineProps<Props>(), { delay: 200, text: '', fullscreen: false })

const { begin, ready } = useFeedback()
const shown = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch(
  () => props.loading,
  (loading) => {
    if (loading) {
      begin()
    } else {
      ready()
    }
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
    if (!loading) {
      shown.value = false
      return
    }
    if (props.delay <= 0) {
      shown.value = true
      return
    }
    timer = setTimeout(() => {
      shown.value = true
    }, props.delay)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer !== undefined) {
    clearTimeout(timer)
  }
})
</script>

<template>
  <div class="bms-loading-mask">
    <slot />
    <div
      v-if="shown"
      class="bms-loading-mask__overlay"
      :class="{ 'is-fullscreen': fullscreen }"
      data-test="loading-mask"
    >
      <span class="bms-loading-mask__spinner" aria-hidden="true" />
      <span v-if="text" class="bms-loading-mask__text">{{ text }}</span>
    </div>
  </div>
</template>

<style scoped>
.bms-loading-mask {
  position: relative;
  box-sizing: border-box;
}

.bms-loading-mask__overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
  justify-content: center;
  background: var(--bms-color-mask-bg);
  border-radius: var(--bms-radius-md);
}

.bms-loading-mask__overlay.is-fullscreen {
  position: fixed;
  z-index: 3000;
  border-radius: 0;
}

.bms-loading-mask__spinner {
  display: block;
  width: 20px;
  height: 20px;
  border: 2px solid var(--bms-color-border);
  border-top-color: var(--bms-color-primary);
  border-radius: 50%;
  animation: bms-loading-spin 0.8s linear infinite;
}

.bms-loading-mask__text {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

@keyframes bms-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

