<script setup lang="ts">
// 滚动容器：统一滚动区（自定义滚动条 / 触底 / 位置保持），封装 `el-scrollbar`。
import { ElScrollbar } from 'element-plus'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 高度（缺省自适应父容器）。 */
  height?: string
  /** 最大高度。 */
  maxHeight?: string
  /** 使用原生滚动（不使用 `el-scrollbar`）。 */
  native?: boolean
  /** 触底阈值（px）。 */
  reachThreshold?: number
  /** 是否保持滚动位置。 */
  keepPosition?: boolean
  /** 位置保持键（`sessionStorage`）。 */
  positionKey?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '',
  maxHeight: '',
  native: false,
  reachThreshold: 24,
  keepPosition: true,
  positionKey: '',
})

const emit = defineEmits<{ scroll: [payload: { top: number; left: number }]; 'reach-bottom': [] }>()

const { sizeToken, isCompact } = useBaseContainer()
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const wrap = ref<HTMLElement>()
const reached = ref(false)

function wrapElement(): HTMLElement | undefined {
  const instance = scrollbarRef.value as unknown as { wrapRef?: HTMLElement } | undefined
  return instance?.wrapRef ?? wrap.value
}

function onScroll(payload: { scrollTop: number; scrollLeft: number }): void {
  emit('scroll', { top: payload.scrollTop, left: payload.scrollLeft })
  const element = wrapElement()
  if (element === undefined) {
    return
  }
  const atBottom = payload.scrollTop + element.clientHeight >= element.scrollHeight - props.reachThreshold
  if (atBottom && !reached.value) {
    reached.value = true
    emit('reach-bottom')
  } else if (!atBottom) {
    reached.value = false
  }
}

onMounted(async () => {
  if (!props.keepPosition || props.positionKey === '') {
    return
  }
  await nextTick()
  const element = wrapElement()
  if (element === undefined) {
    return
  }
  try {
    const stored = sessionStorage.getItem(`scroll:${props.positionKey}`)
    if (stored !== null) {
      element.scrollTop = Number(stored)
    }
  } catch {
    // 隐私模式等场景降级为不保持位置。
  }
})

onBeforeUnmount(() => {
  if (!props.keepPosition || props.positionKey === '') {
    return
  }
  const element = wrapElement()
  if (element === undefined) {
    return
  }
  try {
    sessionStorage.setItem(`scroll:${props.positionKey}`, String(element.scrollTop))
  } catch {
    // 同上。
  }
})
</script>

<template>
  <div
    ref="wrap"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    class="bms-scroll-container"
    :style="{ height: height === '' ? undefined : height, maxHeight: maxHeight === '' ? undefined : maxHeight }"
  >
    <el-scrollbar v-if="!native" ref="scrollbarRef" @scroll="onScroll">
      <slot />
    </el-scrollbar>
    <slot v-else />
  </div>
</template>
