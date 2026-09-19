<script setup lang="ts">
// 报表网格画布（08_09_01）：gridstack 独立分包入口，12 列网格拖拽 / 缩放；对外仅上抛布局落点。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ReportChartItem, ReportDataset } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'

/** gridstack 节点最小面。 */
interface GridNode {
  /** 标识。 */
  id?: unknown
  /** 列。 */
  x?: number
  /** 行。 */
  y?: number
  /** 宽。 */
  w?: number
  /** 高。 */
  h?: number
}
/** gridstack 实例最小面。 */
interface GridInstance {
  /** 订阅事件。 */
  on: (event: string, handler: (event: unknown, nodes: GridNode[]) => void) => void
  /** 启用。 */
  enable: () => void
  /** 禁用。 */
  disable: () => void
  /** 销毁（保留 DOM）。 */
  destroy: (removeDOM?: boolean) => void
}
/** gridstack 模块最小面。 */
interface GridStackModule {
  /** 初始化。 */
  GridStack: { init: (options: Record<string, unknown>, el: HTMLElement) => GridInstance }
}

interface Props {
  /** 图表项。 */
  charts?: ReportChartItem[]
  /** 当前选中标识。 */
  selectedId?: string
  /** 只读。 */
  readOnly?: boolean
  /** 网格列数。 */
  columns?: number
  /** 数据集（脚注标注用）。 */
  datasets?: ReportDataset[]
}

const props = withDefaults(defineProps<Props>(), {
  charts: () => [],
  selectedId: '',
  readOnly: false,
  columns: 12,
  datasets: () => [],
})

const emit = defineEmits<{
  select: [id: string]
  'move-chart': [payload: { id: string; x: number; y: number }]
  'resize-chart': [payload: { id: string; w: number; h: number }]
}>()

/** 网格容器。 */
const gridRef = ref<HTMLElement>()
/** gridstack 实例。 */
let grid: GridInstance | undefined
/** 是否降级（内核不可用）。 */
const degraded = ref(false)
/** 数据状态（空 / 就绪）。 */
const { state, setState } = useBaseDataState()

watch(
  () => props.charts.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/** 初始化网格。 */
async function initGrid(): Promise<void> {
  if (gridRef.value === undefined) {
    return
  }
  try {
    const module = (await import('gridstack')) as unknown as GridStackModule
    grid = module.GridStack.init(
      { column: props.columns, cellHeight: 72, margin: 6, float: false, resizable: { handles: 'e,se,s,sw,w' } },
      gridRef.value,
    )
    grid.on('change', (_event, nodes) => {
      for (const node of nodes) {
        const id = String(node.id ?? '')
        if (id === '') {
          continue
        }
        emit('move-chart', { id, x: node.x ?? 0, y: node.y ?? 0 })
        emit('resize-chart', { id, w: node.w ?? 6, h: node.h ?? 4 })
      }
    })
    if (props.readOnly) {
      grid.disable()
    }
  } catch {
    degraded.value = true
  }
}

/** 重建网格（图表项变化时）。 */
async function rebuild(): Promise<void> {
  grid?.destroy(false)
  grid = undefined
  await initGrid()
}

onMounted(() => {
  void import('gridstack/dist/gridstack.min.css').catch(() => undefined)
  void initGrid()
})

watch(
  () => props.charts.map((item) => `${item.id}:${item.layout.x}:${item.layout.y}:${item.layout.w}:${item.layout.h}`).join(','),
  () => {
    void rebuild()
  },
)

watch(
  () => props.readOnly,
  (value) => {
    if (value) {
      grid?.disable()
    } else {
      grid?.enable()
    }
  },
)

onBeforeUnmount(() => {
  grid?.destroy(false)
  grid = undefined
})
</script>

<template>
  <div
    ref="gridRef"
    class="bms-report-grid grid-stack"
    data-test="report-grid"
    data-subpackage="gridstack"
    :data-state="state"
    :data-degraded="degraded"
  >
    <div
      v-for="item in charts"
      :key="item.id"
      class="grid-stack-item"
      :gs-id="item.id"
      :gs-x="item.layout.x"
      :gs-y="item.layout.y"
      :gs-w="item.layout.w"
      :gs-h="item.layout.h"
      :data-test="`grid-item-${item.id}`"
      :data-selected="item.id === selectedId || undefined"
      @click="emit('select', item.id)"
    >
      <div class="grid-stack-item-content">
        <slot :item="item" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-report-grid {
  position: relative;
  min-height: 320px;
  background: var(--bms-color-bg, #fff);
}
.grid-stack-item-content {
  overflow: hidden;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-md, 4px);
}
.grid-stack-item[data-selected='true'] .grid-stack-item-content {
  border-color: var(--bms-color-primary, #409eff);
  box-shadow: 0 0 0 1px var(--bms-color-primary, #409eff);
}
</style>
