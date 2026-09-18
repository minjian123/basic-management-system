<script setup lang="ts">
// 懒加载容器：进入视口才渲染（占位防抖动；`once` 缺省 true），能力缺失直接渲染。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

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
let observer: IntersectionObserver | undefined

function show(): void {
  if (shown.value) {
    return
  }
  shown.value = true
  emit('visible')
  if (props.once) {
    observer?.disconnect()
  }
}

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') {
    show()
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      const intersecting = entries.some((entry) => entry.isIntersecting)
      if (intersecting) {
        show()
      } else if (!props.once) {
        shown.value = false
      }
    },
    { rootMargin: props.rootMargin, threshold: props.threshold },
  )
  if (root.value !== undefined) {
    observer.observe(root.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
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
    <div v-else class="bms-lazy-container__placeholder" :style="{ height: typeof placeholderHeight === 'number' ? `${placeholderHeight}px` : placeholderHeight }" />
  </div>
</template>
