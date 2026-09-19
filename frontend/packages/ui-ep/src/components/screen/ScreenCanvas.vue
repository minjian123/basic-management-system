<script setup lang="ts">
// 大屏自由画布（08_09_02）：由 ScreenDesigner 异步懒加载的独立分包入口；vue-flow 承载绝对定位拖拽 / 缩放（内核不可用时降级为绝对定位列表）。
import { computed, onMounted, ref, shallowRef, watch, type Component } from 'vue'

import { canvasStyle, type ChartDatasetResult, type ReportDataset, type ScreenCanvasConfig, type ScreenComponent } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'
import ScreenWidget from './ScreenWidget.vue'

/** vue-flow 模块最小面（经 `utils/vueFlow.ts` 单一落点异步装载）。 */
interface VueFlowModule {
  /** 画布容器。 */
  VueFlow: Component
  /** 背景件。 */
  Background: Component
  /** 缩放控件件。 */
  Controls: Component
}

/** vue-flow 节点最小面。 */
interface FlowNode {
  /** 标识。 */
  id: string
  /** 节点类型。 */
  type: string
  /** 位置。 */
  position: { x: number; y: number }
  /** 节点数据。 */
  data: { component: ScreenComponent }
  /** 尺寸。 */
  style: Record<string, string>
  /** 可拖拽。 */
  draggable: boolean
  /** 可选中。 */
  selectable: boolean
}

/** 节点点击事件载荷。 */
interface FlowNodeEvent {
  /** 节点。 */
  node?: { id?: string; position?: { x?: number; y?: number } }
}

interface Props {
  /** 当前页组件。 */
  components?: ScreenComponent[]
  /** 当前选中组件标识。 */
  selectedId?: string
  /** 只读。 */
  readOnly?: boolean
  /** 当前页标识。 */
  activePageId?: string
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 数据集（组件渲染与字段映射用）。 */
  datasets?: ReportDataset[]
  /** 各组件取数结果（设计态预览）。 */
  data?: Record<string, ChartDatasetResult>
}

const props = withDefaults(defineProps<Props>(), {
  components: () => [],
  selectedId: '',
  readOnly: false,
  activePageId: '',
  canvas: undefined,
  datasets: () => [],
  data: () => ({}),
})

const emit = defineEmits<{
  select: [id: string]
  'remove-component': [id: string]
  'move-component': [payload: { id: string; x: number; y: number }]
  'resize-component': [payload: { id: string; w: number; h: number }]
  'reorder-component': [payload: { id: string; action: 'raise' | 'lower' | 'top' | 'bottom' }]
  'update-component': [payload: { id: string; patch: { text?: string } }]
}>()

const { state, setState } = useBaseDataState()
/** vue-flow 模块（装载成功后可用）。 */
const flow = shallowRef<VueFlowModule>()
/** 是否降级（内核不可用）。 */
const degraded = ref(false)

watch(
  () => props.components.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/** 节点清单。 */
const nodes = computed<FlowNode[]>(() =>
  props.components.map((item) => ({
    id: item.id,
    type: 'screen',
    position: { x: item.x, y: item.y },
    data: { component: item },
    style: { width: `${item.w}px`, height: `${item.h}px` },
    draggable: !props.readOnly,
    selectable: true,
  })),
)

/** 是否支持 vue-flow（需要布局观测 API）。 */
function supportsVueFlow(): boolean {
  return typeof globalThis.ResizeObserver !== 'undefined' && typeof globalThis.document !== 'undefined'
}

onMounted(async () => {
  if (!supportsVueFlow()) {
    degraded.value = true
    return
  }
  try {
    const module = (await import('../../utils/vueFlow')) as unknown as VueFlowModule
    flow.value = module
  } catch {
    degraded.value = true
  }
})

/** 选中组件。 */
function onSelect(id: string): void {
  emit('select', id)
}

/**
 * 节点点击。
 *
 * @param event 事件载荷。
 */
function onNodeClick(event: FlowNodeEvent): void {
  const id = event.node?.id
  if (typeof id === 'string' && id !== '') {
    onSelect(id)
  }
}

/**
 * 节点拖拽结束（落点上抛）。
 *
 * @param event 事件载荷。
 */
function onNodeDragStop(event: FlowNodeEvent): void {
  const id = event.node?.id
  if (typeof id !== 'string' || id === '' || event.node?.position === undefined) {
    return
  }
  emit('move-component', { id, x: Math.round(event.node.position.x ?? 0), y: Math.round(event.node.position.y ?? 0) })
}

/**
 * 开始缩放（指针拖动右下角手柄）。
 *
 * @param event 指针事件。
 * @param component 组件。
 */
function startResize(event: PointerEvent, component: ScreenComponent): void {
  if (props.readOnly) {
    return
  }
  const startX = event.clientX
  const startY = event.clientY
  let nextW = component.w
  let nextH = component.h
  const onMove = (moveEvent: PointerEvent): void => {
    nextW = Math.max(40, Math.round(component.w + (moveEvent.clientX - startX)))
    nextH = Math.max(32, Math.round(component.h + (moveEvent.clientY - startY)))
  }
  const onUp = (): void => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    emit('resize-component', { id: component.id, w: nextW, h: nextH })
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

<template>
  <div
    class="bms-screen-canvas"
    data-test="screen-canvas"
    data-subpackage="screen"
    :data-state="state"
    :data-page="activePageId"
    :data-readonly="readOnly"
    :data-degraded="degraded"
  >
    <p v-if="components.length === 0" data-test="canvas-empty">当前页暂无组件（从左侧组件面板拖入）</p>
    <component
      :is="flow.VueFlow"
      v-else-if="flow"
      class="bms-screen-canvas__flow"
      :nodes="nodes"
      :edges="[]"
      :nodes-draggable="!readOnly"
      :nodes-connectable="false"
      :pan-on-drag="!readOnly"
      :zoom-on-scroll="!readOnly"
      :min-zoom="0.2"
      :max-zoom="2"
      @node-click="onNodeClick"
      @node-drag-stop="onNodeDragStop"
    >
      <template #node-screen="nodeProps">
        <div
          class="bms-screen-canvas__node"
          :data-test="`component-${nodeProps.data.component.id}`"
          :data-type="nodeProps.data.component.type"
          :data-selected="nodeProps.data.component.id === selectedId || undefined"
          @click.stop="onSelect(nodeProps.data.component.id)"
        >
          <ScreenWidget
            :component="nodeProps.data.component"
            :datasets="datasets"
            :data="data[nodeProps.data.component.id]"
            :read-only="readOnly"
          />
          <button
            type="button"
            class="bms-screen-canvas__remove"
            :data-test="`remove-${nodeProps.data.component.id}`"
            :disabled="readOnly"
            @click.stop="emit('remove-component', nodeProps.data.component.id)"
          >
            删除
          </button>
          <span
            class="bms-screen-canvas__handle"
            :data-test="`canvas-resize-${nodeProps.data.component.id}`"
            @pointerdown.stop="startResize($event, nodeProps.data.component)"
          />
        </div>
      </template>
      <component :is="flow.Background" />
      <component :is="flow.Controls" />
    </component>
    <div v-else class="bms-screen-canvas__fallback" data-test="canvas-degrade">
      <div
        v-for="item in components"
        :key="item.id"
        class="bms-screen-canvas__node bms-screen-canvas__node--absolute"
        :style="canvasStyle(item)"
        :data-test="`component-${item.id}`"
        :data-type="item.type"
        :data-selected="item.id === selectedId || undefined"
        @click="onSelect(item.id)"
      >
        <ScreenWidget :component="item" :datasets="datasets" :data="data[item.id]" :read-only="readOnly" />
        <button
          type="button"
          class="bms-screen-canvas__remove"
          :data-test="`remove-${item.id}`"
          :disabled="readOnly"
          @click.stop="emit('remove-component', item.id)"
        >
          删除
        </button>
        <span class="bms-screen-canvas__handle" :data-test="`canvas-resize-${item.id}`" @pointerdown.stop="startResize($event, item)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-screen-canvas {
  position: relative;
  width: 100%;
  min-height: 360px;
  background: var(--bms-color-bg, #fff);
}
.bms-screen-canvas__flow {
  width: 100%;
  height: 420px;
}
.bms-screen-canvas__fallback {
  position: relative;
  width: 100%;
  min-height: 360px;
}
.bms-screen-canvas__node {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-md, 4px);
  background: var(--bms-color-bg, #fff);
}
.bms-screen-canvas__node[data-selected='true'] {
  border-color: var(--bms-color-primary, #409eff);
  box-shadow: 0 0 0 1px var(--bms-color-primary, #409eff);
}
.bms-screen-canvas__remove {
  position: absolute;
  top: 2px;
  right: 2px;
  z-index: 2;
  font-size: 12px;
}
.bms-screen-canvas__handle {
  position: absolute;
  right: 0;
  bottom: 0;
  z-index: 2;
  width: 12px;
  height: 12px;
  border-right: 2px solid var(--bms-color-primary, #409eff);
  border-bottom: 2px solid var(--bms-color-primary, #409eff);
  cursor: nwse-resize;
}
</style>
