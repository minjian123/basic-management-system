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
}

const props = withDefaults(defineProps<Props>(), {
  itemHeight: undefined,
  buffer: 4,
  estimatedHeight: 44,
  height: '',
  maxHeight: '',
})

const emit = defineEmits<{ 'visible-change': [payload: { start: number; end: number }] }>()

const { sizeToken, isCompact } = useBaseContainer()
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const scrollTop = ref(0)
const viewportHeight = ref(0)
const measured = ref<Map<number, number>>(new Map())

function wrapElement(): HTMLElement | undefined {
  const instance = scrollbarRef.value as unknown as { wrapRef?: HTMLElement } | undefined
  return instance?.wrapRef
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
  }
}

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
        <div v-for="row in rows" :key="row.index" class="bms-virtual-list-container__item" :style="itemStyle(row.index)">
          <slot :item="row.item" :index="row.index" />
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>
