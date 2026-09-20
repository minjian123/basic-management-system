<script setup lang="ts">
// 播放舞台（08_09_02）：由 ScreenPlayer 异步懒加载的独立分包入口；按设计分辨率绝对定位、CSS transform 等比自适应。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  canvasStyle,
  computeScale,
  type ChartDatasetResult,
  type ReportDataset,
  type ScreenCanvasConfig,
  type ScreenComponent,
} from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'
import { observeResize, supportsResize } from '../../utils/observe'
import ScreenWidget from './ScreenWidget.vue'

interface Props {
  /** 当前页标识。 */
  activePageId?: string
  /** 当前页组件。 */
  components?: ScreenComponent[]
  /** 是否播放中。 */
  playing?: boolean
  /** 轮播间隔（毫秒）。 */
  interval?: number
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 数据集（组件渲染与字段映射用）。 */
  datasets?: ReportDataset[]
  /** 各组件取数结果。 */
  data?: Record<string, ChartDatasetResult>
}

const props = withDefaults(defineProps<Props>(), {
  activePageId: '',
  components: () => [],
  playing: false,
  interval: 0,
  canvas: undefined,
  datasets: () => [],
  data: () => ({}),
})

const { state, setState } = useBaseDataState()
/** 舞台容器。 */
const stageRef = ref<HTMLElement>()
/** 容器尺寸。 */
const containerSize = ref({ width: 0, height: 0 })
let offResize: () => void = () => {}

watch(
  () => props.components.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/** 设计分辨率。 */
const design = computed(() => ({
  width: props.canvas?.width ?? 1920,
  height: props.canvas?.height ?? 1080,
}))
/** 等比缩放参数。 */
const transform = computed(() => computeScale(design.value, containerSize.value, 'contain'))
/** 视口样式。 */
const viewportStyle = computed(() => ({ width: `${design.value.width}px`, height: `${design.value.height}px`, transform: `translate(${transform.value.offsetX}px, ${transform.value.offsetY}px) scale(${transform.value.scale})`, transformOrigin: 'top left' }))

onMounted(() => {
  if (supportsResize() && stageRef.value !== undefined) {
    offResize = observeResize(stageRef.value, (entry) => {
      const rect = entry.contentRect
      containerSize.value = { width: rect.width, height: rect.height }
    })
  }
})

onBeforeUnmount(() => {
  offResize()
})
</script>

<template>
  <div
    ref="stageRef"
    class="bms-screen-stage"
    data-test="screen-stage"
    data-subpackage="screen-player"
    :data-state="state"
    :data-page="activePageId"
    :data-playing="playing"
    :data-interval="interval"
  >
    <p v-if="components.length === 0" data-test="stage-empty">当前页暂无组件（占位，真实实现按分辨率自适应播放）</p>
    <div v-else class="bms-screen-stage__viewport" data-test="stage-scale" :style="viewportStyle">
      <div
        v-for="item in components"
        :key="item.id"
        class="bms-screen-stage__item"
        :style="canvasStyle(item)"
        :data-test="`stage-${item.id}`"
        :data-type="item.type"
      >
        <ScreenWidget :component="item" :datasets="datasets" :data="data[item.id]" mode="play" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-screen-stage {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 360px;
  overflow: hidden;
  background: var(--bms-color-bg);
}
.bms-screen-stage__viewport {
  position: absolute;
  top: 0;
  left: 0;
}
.bms-screen-stage__item {
  overflow: hidden;
}
</style>
