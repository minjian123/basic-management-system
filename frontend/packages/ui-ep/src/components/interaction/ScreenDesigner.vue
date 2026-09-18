<script setup lang="ts">
// 大屏设计器（占位版，08_01_03）：契约先行冻结；数据通路未就绪时不请求、编辑禁用 + 降级提示。自由画布独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseDragDrop } from '../../composables/useBaseDragDrop'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 自由画布独立分包（vue-flow / 拖拽内核，真实实现 08_09 接入）。
const ScreenCanvas = defineAsyncComponent(() => import('./ScreenCanvas.vue'))

/** 大屏页。 */
export interface ScreenPage {
  /** 页标识。 */
  id: string
  /** 页名。 */
  name: string
}

/** 组件类型（大屏组件库）。 */
export type ScreenComponentType = 'chart' | 'table' | 'metric' | 'text' | 'image' | 'time' | 'decor'

/** 大屏组件（绝对定位）。 */
export interface ScreenComponent {
  /** 组件标识。 */
  id: string
  /** 组件类型。 */
  type: ScreenComponentType
  /** x 坐标。 */
  x: number
  /** y 坐标。 */
  y: number
  /** 宽。 */
  w: number
  /** 高。 */
  h: number
  /** 层级。 */
  z: number
  /** 引用数据集标识。 */
  datasetId?: string
  /** 图表类型。 */
  chartType?: string
  /** 文本内容。 */
  text?: string
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 大屏标识。 */
  screenCode?: string
  /** 多页。 */
  pages?: ScreenPage[]
  /** 当前页标识。 */
  activePageId?: string
  /** 当前页组件。 */
  components?: ScreenComponent[]
  /** 当前选中组件标识。 */
  selectedId?: string
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 只读。 */
  readOnly?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  screenCode: '',
  pages: () => [],
  activePageId: '',
  components: () => [],
  selectedId: '',
  dirty: false,
  readOnly: false,
  degradeText: '大屏设计器未就绪（占位）',
})

const emit = defineEmits<{
  change: [components: ScreenComponent[]]
  select: [id: string | null]
  'add-component': [type: ScreenComponentType]
  'remove-component': [id: string]
  'page-change': [pageId: string]
  save: []
  publish: []
  'preview-play': []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { dragging, emitDrag } = useBaseDragDrop()
const selected = ref(props.selectedId)

/** 组件面板（大屏组件库）。 */
const palette: ScreenComponentType[] = ['chart', 'table', 'metric', 'text', 'image', 'time', 'decor']

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
  { immediate: true },
)

watch(
  () => props.selectedId,
  (id) => {
    selected.value = id ?? ''
  },
)

/** 当前选中组件。 */
const selectedComponent = computed(() => props.components.find((item) => item.id === selected.value))

/** 从组件面板拖入组件（占位：广播拖拽并透传事件）。 */
function addComponent(type: ScreenComponentType): void {
  if (placeholder.disabled.value || props.readOnly) {
    return
  }
  emitDrag({ phase: 'start', source: type })
  emit('add-component', type)
}

/** 画布选中联动属性面板。 */
function onSelect(id: string): void {
  selected.value = id
  emit('select', id)
}
</script>

<template>
  <div
    class="bms-screen-designer"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-dragging="dragging"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-screen-designer__toolbar" data-test="toolbar">
          <span data-test="screen-code">{{ screenCode }}</span>
          <button
            v-for="page in pages"
            :key="page.id"
            type="button"
            :data-test="`page-${page.id}`"
            :data-active="page.id === activePageId || undefined"
            @click="emit('page-change', page.id)"
          >
            {{ page.name }}
          </button>
          <button type="button" data-test="save" :disabled="placeholder.disabled.value || readOnly" @click="emit('save')">保存</button>
          <button type="button" data-test="publish" :disabled="placeholder.disabled.value || readOnly" @click="emit('publish')">
            发布
          </button>
          <button type="button" data-test="preview-play" @click="emit('preview-play')">预览播放</button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </div>

        <div class="bms-screen-designer__body">
          <div class="bms-screen-designer__panel" data-test="component-panel">
            <slot name="component-panel" :disabled="readOnly">
              <button
                v-for="item in palette"
                :key="item"
                type="button"
                :data-test="`palette-${item}`"
                :disabled="readOnly"
                @click="addComponent(item)"
              >
                {{ item }}
              </button>
            </slot>
          </div>

          <div class="bms-screen-designer__canvas" data-test="canvas">
            <component
              :is="ScreenCanvas"
              :components="components"
              :selected-id="selected"
              :read-only="readOnly"
              :active-page-id="activePageId"
              @select="onSelect"
              @remove-component="emit('remove-component', $event)"
            />
          </div>

          <div class="bms-screen-designer__properties" data-test="property-panel">
            <slot name="property-panel" :component="selectedComponent">
              <p v-if="selectedComponent" data-test="properties-selected">{{ selectedComponent.type }}</p>
              <p v-else data-test="properties-empty">未选中组件</p>
            </slot>
          </div>
        </div>
      </slot>
    </template>
  </div>
</template>
