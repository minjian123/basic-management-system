<script setup lang="ts">
// 滚动容器：统一滚动区（自定义滚动条 / 触顶与触底 / 位置保持），封装 `el-scrollbar`。
import { ElScrollbar } from 'element-plus'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { useBasePersistedState } from '../../composables/useBasePersistedState'

interface Props {
  /** 高度（缺省自适应父容器）。 */
  height?: string
  /** 最大高度。 */
  maxHeight?: string
  /** 使用原生滚动（不使用 `el-scrollbar`）。 */
  native?: boolean
  /** 触顶 / 触底阈值（px）。 */
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

const emit = defineEmits<{
  scroll: [payload: { top: number; left: number }]
  'reach-top': []
  'reach-bottom': []
}>()

const { sizeToken, isCompact } = useBaseContainer()
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const wrap = ref<HTMLElement>()
const reached = ref(false)
const topped = ref(false)
const positionState = useBasePersistedState({
  storage: 'session',
  restore: false,
  stateKey: props.positionKey === '' ? '' : `scroll:${props.positionKey}`,
})

function wrapElement(): HTMLElement | null | undefined {
  const instance = scrollbarRef.value as unknown as { wrapRef?: HTMLElement | null } | undefined
  return instance?.wrapRef ?? wrap.value
}

function onScroll(payload: { scrollTop: number; scrollLeft: number }): void {
  emit('scroll', { top: payload.scrollTop, left: payload.scrollLeft })
  const element = wrapElement()
  if (element == null) {
    return
  }
  const atBottom = payload.scrollTop + element.clientHeight >= element.scrollHeight - props.reachThreshold
  if (atBottom && !reached.value) {
    reached.value = true
    emit('reach-bottom')
  } else if (!atBottom) {
    reached.value = false
  }
  const atTop = payload.scrollTop <= props.reachThreshold
  if (atTop && !topped.value) {
    topped.value = true
    emit('reach-top')
  } else if (!atTop) {
    topped.value = false
  }
}

onMounted(async () => {
  if (!props.keepPosition || props.positionKey === '') {
    return
  }
  await nextTick()
  const element = wrapElement()
  if (element == null) {
    return
  }
  if (positionState.restore() && typeof positionState.local.value === 'number') {
    element.scrollTop = positionState.local.value
  }
})

onBeforeUnmount(() => {
  if (!props.keepPosition || props.positionKey === '') {
    return
  }
  const element = wrapElement()
  if (element == null) {
    return
  }
  positionState.setLocal(element.scrollTop)
  positionState.persist()
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

<style scoped>
.bms-scroll-container {
  position: relative;
  box-sizing: border-box;
  min-height: 0;
  overflow: hidden;
  scrollbar-width: thin;
  scrollbar-color: var(--bms-scrollbar-thumb) var(--bms-scrollbar-track);
}

.bms-scroll-container :deep(.el-scrollbar) {
  height: 100%;
}

.bms-scroll-container :deep(.el-scrollbar__bar) {
  z-index: 2;
}

.bms-scroll-container :deep(.el-scrollbar__thumb) {
  background-color: var(--bms-scrollbar-thumb);
  border-radius: var(--bms-scrollbar-radius);
  opacity: 0.6;
}

.bms-scroll-container :deep(.el-scrollbar__thumb:hover) {
  background-color: var(--bms-scrollbar-thumb-hover);
  opacity: 1;
}

/* 原生滚动模式的滚动条（`native` 时不渲染 `el-scrollbar`） */
.bms-scroll-container::-webkit-scrollbar {
  width: var(--bms-scrollbar-size);
  height: var(--bms-scrollbar-size);
}

.bms-scroll-container::-webkit-scrollbar-thumb {
  background: var(--bms-scrollbar-thumb);
  border-radius: var(--bms-scrollbar-radius);
}

.bms-scroll-container::-webkit-scrollbar-thumb:hover {
  background: var(--bms-scrollbar-thumb-hover);
}

.bms-scroll-container::-webkit-scrollbar-track {
  background: var(--bms-scrollbar-track);
}

/* 移动端隐藏自绘滚动条（触屏原生滚动） */
@media (max-width: 768px) {
  .bms-scroll-container {
    scrollbar-width: none;
  }

  .bms-scroll-container::-webkit-scrollbar {
    width: 0;
    height: 0;
  }
}
</style>
