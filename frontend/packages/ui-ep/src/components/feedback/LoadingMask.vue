<script setup lang="ts">
// 内容遮罩：局部加载遮罩，延迟展示防闪烁。
import { onBeforeUnmount, ref, watch } from 'vue'

interface Props {
  /** 加载中。 */
  loading: boolean
  /** 延迟展示（毫秒，防闪烁）。 */
  delay?: number
  /** 文案。 */
  text?: string
}

const props = withDefaults(defineProps<Props>(), { delay: 200, text: '' })

const shown = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch(
  () => props.loading,
  (loading) => {
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
    <div v-if="shown" class="bms-loading-mask__overlay" data-test="loading-mask">
      <span class="bms-loading-mask__spinner" aria-hidden="true" />
      <span v-if="text" class="bms-loading-mask__text">{{ text }}</span>
    </div>
  </div>
</template>
