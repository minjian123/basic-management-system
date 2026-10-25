<script setup lang="ts">
// 懒加载容器：进入视口才渲染（占位防抖动；`once` 缺省 true），能力缺失直接渲染。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { observeIntersection, supportsIntersection } from '../../utils/observe'

interface Props {
  /** 视口扩展边距。 */
  rootMargin?: string
  /** 交叉阈值。 */
  threshold?: number
  /** 进入视口一次后常驻。 */
  once?: boolean
  /** 占位高度（防抖动，数字按 px）。 */
  placeholderHeight?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  rootMargin: '0px',
  threshold: 0,
  once: true,
  placeholderHeight: 120,
})

const emit = defineEmits<{ visible: [] }>()

const { sizeToken, isCompact } = useBaseContainer()
const root = ref<HTMLElement>()
const shown = ref(false)
let off: () => void = () => {}

function show(): void {
  if (shown.value) {
    return
  }
  shown.value = true
  emit('visible')
  if (props.once) {
    off()
  }
}

onMounted(() => {
  if (!supportsIntersection() || root.value === undefined) {
    show()
    return
  }
  off = observeIntersection(
    root.value,
    (entry) => {
      if (entry.isIntersecting) {
        show()
      } else if (!props.once) {
        shown.value = false
      }
    },
    { rootMargin: props.rootMargin, threshold: props.threshold },
  )
})

onBeforeUnmount(() => {
  off()
})
</script>

<template>
  <div
    ref="root"
    class="bms-lazy-container"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
  >
    <slot v-if="shown" />
    <div
      v-else
      class="bms-lazy-container__placeholder"
      data-test="lazy-placeholder"
      :style="{ height: typeof placeholderHeight === 'number' ? `${placeholderHeight}px` : placeholderHeight }"
    >
      <slot name="placeholder">
        <span class="bms-lazy-container__placeholder-text">加载中…</span>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-lazy-container {
  box-sizing: border-box;
  min-height: 0;
}

.bms-lazy-container__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60px;
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-md);
  animation: bms-lazy-pulse 1.6s ease-in-out infinite;
}

.bms-lazy-container__placeholder-text {
  font-size: var(--bms-font-size-sm);
}

@keyframes bms-lazy-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.6;
  }
}
</style>

