<script setup lang="ts">
// 大屏设计器（08_09_02）：三区（组件面板 / 自由画布 / 属性面板）+ 工具栏（新建 / 打开 / 保存 / 发布 / 预览播放 / 多页）。
// 对外契约保持 08_01_03 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test / 分包入口不变），仅向后兼容新增可选项。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import type {
  BaseAccess,
  BaseNotice,
  ChartDatasetResult,
  ReportDataset,
  ScreenCanvasConfig,
  ScreenComponent,
  ScreenComponentType,
  ScreenDesignerJobs,
} from '@bms/core'

import { useBaseDragDrop } from '../../composables/useBaseDragDrop'
import { useBaseScreenDesigner } from '../../composables/useBaseScreenDesigner'
import ComponentPalette from './ComponentPalette.vue'
import ScreenPropertyPanel from './ScreenPropertyPanel.vue'

// 自由画布与播放舞台独立分包（vue-flow / 自适应缩放）。
const ScreenCanvas = defineAsyncComponent(() => import('./ScreenCanvas.vue'))
const ScreenStage = defineAsyncComponent(() => import('./ScreenStage.vue'))

/** 大屏页。 */
export interface ScreenPage {
  /** 页标识。 */
  id: string
  /** 页名。 */
  name: string
  /** 单页停留时长（毫秒，可选）。 */
  duration?: number
}

/** 组件类型（大屏组件库）。 */
export type ScreenComponentTypeAlias = ScreenComponentType

/** 大屏组件（绝对定位）。 */
export type ScreenComponentModel = ScreenComponent

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 大屏标识。 */
  screenCode?: string
  /** 大屏名称。 */
  screenName?: string
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
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 数据集（校验与组件渲染用）。 */
  datasets?: ReportDataset[]
  /** 注入处理函数集（注入后驱动真实编排）。 */
  jobs?: ScreenDesignerJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  screenCode: '',
  screenName: '',
  pages: () => [],
  activePageId: '',
  components: () => [],
  selectedId: '',
  dirty: false,
  readOnly: false,
  degradeText: '大屏设计器未就绪（占位）',
  canvas: undefined,
  datasets: () => [],
  jobs: undefined,
  access: undefined,
  notice: undefined,
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
  new: []
  open: [{ code: string }]
  loaded: []
  saved: []
  failed: [{ message: string }]
  'dirty-block': [{ action: string }]
  'page-add': [{ id: string }]
  'page-remove': [{ id: string }]
  'page-rename': [{ id: string; name: string }]
  'component-update': [{ id: string; patch: Record<string, unknown> }]
  'canvas-change': [canvas: ScreenCanvasConfig]
  'dataset-preview': [{ componentId: string; data: ChartDatasetResult | undefined }]
}>()

const { dragging, dragDrop, emitDrag } = useBaseDragDrop()
const base = useBaseScreenDesigner({
  ready: props.ready,
  screenCode: props.screenCode,
  screenName: props.screenName,
  canvas: props.canvas,
  pages: props.pages,
  componentsByPage: props.pages.length > 0 ? { [props.activePageId]: props.components } : undefined,
  activePageId: props.activePageId,
  selectedId: props.selectedId,
  datasets: props.datasets,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
  drag: dragDrop,
})

/** 受控模式本地选中（未注入处理函数时）。 */
const selectedLocal = ref(props.selectedId)
/** 预览播放中。 */
const previewPlaying = ref(false)
/** 设计态预览取数结果。 */
const previewData = ref<Record<string, ChartDatasetResult>>({})

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.pages,
  (value) => base.setPages(value),
)
watch(
  () => props.selectedId,
  (value) => {
    selectedLocal.value = value
  },
)

/** 是否注入处理函数（事件与注入双轨）。 */
const hasJobs = computed(() => props.jobs !== undefined)
/** 生效页清单。 */
const pagesValue = computed(() => (hasJobs.value ? base.pages.value : props.pages))
/** 生效当前页标识。 */
const activeValue = computed(() => (hasJobs.value ? base.activePageId.value : props.activePageId))
/** 生效当前页组件。 */
const componentsValue = computed<ScreenComponent[]>(() => (hasJobs.value ? base.components.value : props.components))
/** 生效选中标识。 */
const selectedValue = computed(() => (hasJobs.value ? base.selectedId.value : selectedLocal.value))
/** 生效画布配置。 */
const canvasValue = computed<ScreenCanvasConfig>(
  () => (hasJobs.value ? base.canvas.value : (props.canvas ?? { width: 1920, height: 1080, theme: 'auto' })),
)
/** 生效选中组件。 */
const selectedComponentValue = computed(() => componentsValue.value.find((item) => item.id === selectedValue.value))
/** 生效只读。 */
const readonlyFlag = computed(() => props.readOnly || (hasJobs.value ? base.readonly.value : false))
/** 生效脏标记。 */
const dirtyFlag = computed(() => (hasJobs.value ? base.dirty.value : props.dirty))
/** 生效大屏编码。 */
const screenCodeValue = computed(() => (hasJobs.value ? base.designer.screenCode : props.screenCode))

/**
 * 选中组件。
 *
 * @param id 标识。
 */
function onSelect(id: string | null): void {
  selectedLocal.value = id ?? ''
  if (hasJobs.value) {
    base.selectComponent(id)
  }
  emit('select', id)
}

/**
 * 从面板新增组件（事件双轨）。
 *
 * @param type 组件类型。
 */
function onAddComponent(type: ScreenComponentType): void {
  if (readonlyFlag.value) {
    return
  }
  emitDrag({ phase: 'start', source: type })
  emit('add-component', type)
  if (hasJobs.value) {
    base.addComponent({ type })
    emit('change', componentsValue.value)
  }
}

/**
 * 面板拖拽开始。
 *
 * @param type 组件类型。
 */
function onPaletteDrag(type: ScreenComponentType): void {
  emitDrag({ phase: 'start', source: type })
}

/**
 * 删除组件。
 *
 * @param id 标识。
 */
function onRemoveComponent(id: string): void {
  emit('remove-component', id)
  if (hasJobs.value) {
    base.removeComponent(id)
    emit('change', componentsValue.value)
  }
}

/**
 * 切换当前页。
 *
 * @param pageId 页标识。
 */
function onPageChange(pageId: string): void {
  selectedLocal.value = ''
  emit('page-change', pageId)
  if (hasJobs.value) {
    base.selectPage(pageId)
  }
}

/**
 * 移动组件落点。
 *
 * @param payload 落点。
 */
function onMove(payload: { id: string; x: number; y: number }): void {
  if (hasJobs.value) {
    base.moveComponent(payload.id, payload.x, payload.y)
    emit('change', componentsValue.value)
  }
}

/**
 * 缩放组件落点。
 *
 * @param payload 落点。
 */
function onResize(payload: { id: string; w: number; h: number }): void {
  if (hasJobs.value) {
    base.resizeComponent(payload.id, payload.w, payload.h)
    emit('change', componentsValue.value)
  }
}

/**
 * 层级调整。
 *
 * @param payload 载荷。
 */
function onReorder(payload: { id: string; action: 'raise' | 'lower' | 'top' | 'bottom' }): void {
  if (hasJobs.value) {
    base.reorderComponent(payload.id, payload.action)
    emit('change', componentsValue.value)
  }
}

/**
 * 更新组件。
 *
 * @param payload 载荷。
 */
function onUpdateComponent(payload: { id: string; patch: { type?: ScreenComponentType; text?: string; datasetId?: string; chartType?: string } }): void {
  emit('component-update', { id: payload.id, patch: payload.patch as Record<string, unknown> })
  if (hasJobs.value) {
    base.updateComponent(payload.id, payload.patch)
    emit('change', componentsValue.value)
  }
}

/**
 * 更新画布配置。
 *
 * @param patch 画布变更。
 */
function onCanvasUpdate(patch: Partial<ScreenCanvasConfig>): void {
  if (hasJobs.value) {
    base.setCanvas(patch)
    emit('canvas-change', base.canvas.value)
  } else if (props.canvas !== undefined) {
    emit('canvas-change', { ...props.canvas, ...patch })
  }
}

/** 新增页。 */
function onPageAdd(): void {
  if (hasJobs.value) {
    const page = base.addPage()
    emit('page-add', { id: page?.id ?? '' })
  } else {
    emit('page-add', { id: '' })
  }
}

/**
 * 删除页。
 *
 * @param id 页标识。
 */
function onPageRemove(id: string): void {
  if (hasJobs.value) {
    base.removePage(id)
  }
  emit('page-remove', { id })
}

/** 新建（脏数据时上抛拦截）。 */
function onNew(): void {
  if (hasJobs.value && base.needsBlock('new')) {
    emit('dirty-block', { action: 'new' })
    return
  }
  emit('new')
}

/**
 * 打开（脏数据时上抛拦截）。
 *
 * @param code 大屏编码。
 */
function onOpen(code: string): void {
  if (hasJobs.value && base.needsBlock('open')) {
    emit('dirty-block', { action: 'open' })
    return
  }
  emit('open', { code })
  if (hasJobs.value) {
    void base.load({ code }).then((snapshot) => {
      if (snapshot !== undefined) {
        emit('loaded')
      }
    })
  }
}

/** 保存。 */
function onSave(): void {
  emit('save')
  if (hasJobs.value) {
    void base.save().then((result) => {
      if (result !== undefined) {
        emit('saved')
      } else if (base.errorMessage.value !== '') {
        emit('failed', { message: base.errorMessage.value })
      }
    })
  }
}

/** 发布（先保存成功再发布）。 */
async function onPublish(): Promise<void> {
  emit('publish')
  if (hasJobs.value) {
    const saved = await base.save()
    if (saved !== undefined) {
      await base.publish()
    }
  }
}

/** 预览播放。 */
function onPreviewPlay(): void {
  emit('preview-play')
  previewPlaying.value = true
}

/** 关闭预览。 */
function onPreviewClose(): void {
  previewPlaying.value = false
}

/** 设计态预览取数（选中组件）。 */
function onPreviewData(): void {
  const item = selectedComponentValue.value
  if (item === undefined || !hasJobs.value) {
    return
  }
  void base.preview(item.id).then((result) => {
    if (result !== undefined) {
      previewData.value = { ...previewData.value, [item.id]: result }
    }
    emit('dataset-preview', { componentId: item.id, data: result as ChartDatasetResult | undefined })
  })
}

defineExpose({
  /** 设计器基类实例（开发态核对与宿主调试用）。 */
  designer: base.designer,
  /** 当前页组件。 */
  components: base.components,
  /** 多页。 */
  pages: base.pages,
  /** 是否脏。 */
  dirty: base.dirty,
  /** 是否只读。 */
  readonly: base.readonly,
})
</script>

<template>
  <div
    class="bms-screen-designer"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
    :data-dragging="dragging"
    :data-readonly="readonlyFlag"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-screen-designer__toolbar" data-test="toolbar">
          <span data-test="screen-code">{{ screenCodeValue }}</span>
          <span data-test="screen-name">{{ base.designer.screenName }}</span>
          <slot name="toolbar">
            <button type="button" data-test="new" :disabled="readonlyFlag" @click="onNew">新建</button>
            <button type="button" data-test="open" :disabled="readonlyFlag" @click="onOpen('')">打开</button>
            <button type="button" data-test="page-add" :disabled="readonlyFlag" @click="onPageAdd">新增页</button>
            <button v-for="page in pagesValue" :key="page.id" type="button" :data-test="`page-${page.id}`" :data-active="page.id === activeValue || undefined" @click="onPageChange(page.id)">
              {{ page.name }}
            </button>
            <button v-if="activeValue !== ''" type="button" :data-test="`page-remove-${activeValue}`" :disabled="readonlyFlag" @click="onPageRemove(activeValue)">删除页</button>
            <button type="button" data-test="save" :disabled="readonlyFlag" @click="onSave">保存</button>
            <button type="button" data-test="publish" :disabled="readonlyFlag" @click="onPublish">发布</button>
            <button type="button" data-test="preview-play" @click="onPreviewPlay">预览播放</button>
            <span v-if="dirtyFlag" data-test="dirty">未保存</span>
            <span v-if="!readonlyFlag && hasJobs && !base.validation.value.valid" data-test="validation-error">{{ base.validation.value.message }}</span>
            <span v-if="readonlyFlag" data-test="readonly-hint">只读</span>
          </slot>
          <slot name="screen-list" />
        </div>

        <div class="bms-screen-designer__body">
          <div class="bms-screen-designer__panel" data-test="component-panel">
            <slot name="component-panel" :disabled="readonlyFlag">
              <ComponentPalette :read-only="readonlyFlag" :disabled="base.degraded.value" @add="onAddComponent" @drag-start="onPaletteDrag" />
            </slot>
          </div>

          <div class="bms-screen-designer__canvas" data-test="canvas">
            <slot name="canvas">
              <component
                :is="ScreenCanvas"
                :components="componentsValue"
                :selected-id="selectedValue"
                :read-only="readonlyFlag"
                :active-page-id="activeValue"
                :canvas="canvasValue"
                :datasets="datasets"
                :data="previewData"
                @select="onSelect"
                @remove-component="onRemoveComponent"
                @move-component="onMove"
                @resize-component="onResize"
                @reorder-component="onReorder"
              />
            </slot>
          </div>

          <div class="bms-screen-designer__properties" data-test="property-panel">
            <slot name="property-panel" :component="selectedComponentValue">
              <p v-if="selectedComponentValue" data-test="properties-selected">{{ selectedComponentValue.type }}</p>
              <p v-else data-test="properties-empty">未选中组件</p>
              <ScreenPropertyPanel
                :component="selectedComponentValue"
                :canvas="canvasValue"
                :datasets="datasets"
                :read-only="readonlyFlag"
                @move="onMove"
                @resize="onResize"
                @reorder="onReorder"
                @update="onUpdateComponent"
                @canvas-update="onCanvasUpdate"
              />
              <button v-if="selectedComponentValue" type="button" data-test="preview-data" :disabled="readonlyFlag" @click="onPreviewData">预览数据</button>
            </slot>
          </div>
        </div>

        <div v-if="previewPlaying" class="bms-screen-designer__preview" data-test="preview-stage">
          <button type="button" data-test="preview-close" @click="onPreviewClose">关闭预览</button>
          <component
            :is="ScreenStage"
            :active-page-id="activeValue"
            :components="componentsValue"
            :canvas="canvasValue"
            :datasets="datasets"
            :data="previewData"
          />
        </div>
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-screen-designer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-screen-designer__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.bms-screen-designer__body {
  display: grid;
  grid-template-columns: 200px 1fr 260px;
  gap: 8px;
}
.bms-screen-designer__preview {
  border-top: 1px solid var(--bms-color-border);
  padding-top: 8px;
}
</style>
