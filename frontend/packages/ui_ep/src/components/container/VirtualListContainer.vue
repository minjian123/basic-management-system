<script setup lang="ts">
// 虚拟列表容器：自研轻量（定高快路径 + 动态高度测量缓存），只渲染可视区 + 缓冲。
import { computeVirtualRange } from '@bms/core'
import { ElScrollbar } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch, type CSSProperties } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 数据。 */
  items: readonly unknown[]
  /** 定高（给定则走快路径）。 */
  itemHeight?: number
  /** 上下缓冲条数。 */
  buffer?: number
  /** 动态高度模式的估算值。 */
  estimatedHeight?: number
  /** 高度。 */
  height?: string
  /** 最大高度。 */
  maxHeight?: string
  /** 项唯一键字段名（用于渲染复用与滚动定位）。 */
  itemKey?: string
  /** 触底阈值（px）。 */
  reachThreshold?: number
}

const props = withDefaults(defineProps<Props>(), {
  itemHeight: undefined,
  buffer: 4,
  estimatedHeight: 44,
  height: '',
  maxHeight: '',
  itemKey: 'id',
  reachThreshold: 24,
})

const emit = defineEmits<{
  'visible-change': [payload: { start: number; end: number }]
  'reach-bottom': []
}>()

const { sizeToken, isCompact } = useBaseContainer()
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const scrollTop = ref(0)
const viewportHeight = ref(0)
const measured = ref<Map<number, number>>(new Map())
const reached = ref(false)

function wrapElement(): HTMLElement | undefined {
  const instance = scrollbarRef.value as unknown as { wrapRef?: HTMLElement } | undefined
  return instance?.wrapRef
}

/**
 * 取项唯一键（缺字段回退索引）。
 *
 * @param item 列表项。
 * @param index 项索引。
 * @returns 唯一键。
 */
function keyOf(item: unknown, index: number): string | number {
  const record = item as Record<string, unknown> | null
  const value = record === null ? undefined : record[props.itemKey]
  return typeof value === 'string' || typeof value === 'number' ? value : index
}

/** 动态高度累计偏移（长度 `items.length + 1`）。 */
const offsets = computed<readonly number[] | undefined>(() => {
  if (props.itemHeight !== undefined) {
    return undefined
  }
  const size = props.items.length
  const result = new Array<number>(size + 1)
  result[0] = 0
  for (let index = 0; index < size; index += 1) {
    result[index + 1] = (result[index] ?? 0) + (measured.value.get(index) ?? props.estimatedHeight)
  }
  return result
})

const range = computed(() =>
  computeVirtualRange({
    scrollTop: scrollTop.value,
    viewportHeight: viewportHeight.value,
    count: props.items.length,
    itemHeight: props.itemHeight,
    buffer: props.buffer,
    offsets: offsets.value,
  }),
)

const rows = computed(() =>
  props.items.slice(range.value.start, range.value.end).map((item, offset) => ({
    item,
    index: range.value.start + offset,
  })),
)

function itemStyle(index: number): CSSProperties {
  const top = props.itemHeight !== undefined ? index * props.itemHeight : offsets.value?.[index] ?? 0
  const size = props.itemHeight ?? measured.value.get(index) ?? props.estimatedHeight
  return { position: 'absolute', top: `${top}px`, left: '0', right: '0', height: `${size}px` }
}

function onScroll(payload: { scrollTop: number }): void {
  scrollTop.value = payload.scrollTop
  const element = wrapElement()
  if (element !== undefined) {
    viewportHeight.value = element.clientHeight
    const atBottom = payload.scrollTop + element.clientHeight >= element.scrollHeight - props.reachThreshold
    if (atBottom && !reached.value) {
      reached.value = true
      emit('reach-bottom')
    } else if (!atBottom) {
      reached.value = false
    }
  }
}

/**
 * 滚动到指定项索引（数据未加载时按估算高度定位）。
 *
 * @param index 项索引。
 */
async function scrollToIndex(index: number): Promise<void> {
  await nextTick()
  const element = wrapElement()
  if (element === undefined) {
    return
  }
  const clamped = Math.max(0, Math.min(index, props.items.length - 1))
  const top = props.itemHeight !== undefined ? clamped * props.itemHeight : offsets.value?.[clamped] ?? 0
  element.scrollTop = top
  scrollTop.value = top
}

defineExpose({ scrollToIndex })

watch(
  () => [range.value.start, range.value.end] as const,
  ([start, end]) => {
    emit('visible-change', { start, end })
  },
)

onMounted(async () => {
  await nextTick()
  const element = wrapElement()
  if (element !== undefined) {
    viewportHeight.value = element.clientHeight
  }
})
</script>

<template>
  <div
    class="bms-virtual-list-container"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    :style="{ height: height === '' ? undefined : height, maxHeight: maxHeight === '' ? undefined : maxHeight }"
  >
    <el-scrollbar ref="scrollbarRef" @scroll="onScroll">
      <div class="bms-virtual-list-container__spacer" :style="{ position: 'relative', height: `${range.totalHeight}px` }">
        <div
          v-for="row in rows"
          :key="keyOf(row.item, row.index)"
          class="bms-virtual-list-container__item"
          :style="itemStyle(row.index)"
        >
          <slot :item="row.item" :index="row.index" />
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.bms-virtual-list-container {
  position: relative;
  box-sizing: border-box;
  min-height: 0;
  overflow: hidden;
}

.bms-virtual-list-container :deep(.el-scrollbar) {
  height: 100%;
}

.bms-virtual-list-container__spacer {
  width: 100%;
}

.bms-virtual-list-container__item {
  box-sizing: border-box;
  border-bottom: 1px solid var(--bms-color-border);
}
</style>
