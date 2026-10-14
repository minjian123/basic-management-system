<script setup lang="ts">
// 报表设计器（08_09_01）：三区（数据集 / 画布 / 配置）+ 工具栏（新建 / 打开 / 添加图表 / 预览 / 保存 / 发布 / 另存为）。
// 对外契约保持 08_01_03 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test / 分包入口不变），仅向后兼容新增可选项。
import { ElButton } from 'element-plus'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import type { BaseAccess, BaseNotice, ChartDatasetResult, ReportChartItem, ReportDataset, ReportJobs } from '@bms/core'

import { useBaseReportDesigner } from '../../composables/useBaseReportDesigner'

// 三区件独立分包（数据集详情 / 画布 / 配置面板）。
const DatasetPanel = defineAsyncComponent(() => import('./DatasetPanel.vue'))
const ReportCanvas = defineAsyncComponent(() => import('./ReportCanvas.vue'))
const ChartConfigPanel = defineAsyncComponent(() => import('./ChartConfigPanel.vue'))

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 报表标识。 */
  reportCode?: string
  /** 报表名称。 */
  reportName?: string
  /** 数据集清单。 */
  datasets?: ReportDataset[]
  /** 图表项。 */
  charts?: ReportChartItem[]
  /** 当前选中图表项标识。 */
  selectedId?: string
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 只读。 */
  readOnly?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 当前数据集标识。 */
  datasetId?: string
  /** 注入处理函数集（注入后驱动真实编排）。 */
  jobs?: ReportJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  reportCode: '',
  reportName: '',
  datasets: () => [],
  charts: () => [],
  selectedId: '',
  dirty: false,
  readOnly: false,
  degradeText: '报表设计器未就绪（占位）',
  datasetId: '',
  jobs: undefined,
  access: undefined,
  notice: undefined,
})

const emit = defineEmits<{
  change: [charts: ReportChartItem[]]
  select: [id: string | null]
  'add-chart': [payload: { datasetId: string; chartType: string }]
  'remove-chart': [id: string]
  save: []
  publish: []
  'save-as': []
  preview: []
  retry: []
  new: []
  open: [{ code: string }]
  loaded: []
  saved: []
  failed: [{ message: string }]
  'dirty-block': [{ action: string }]
  'dataset-change': [datasetId: string]
  'chart-update': [{ id: string; patch: { title?: string; chartType?: string; config?: Record<string, unknown> } }]
}>()

const base = useBaseReportDesigner({
  ready: props.ready,
  reportCode: props.reportCode,
  reportName: props.reportName,
  datasets: props.datasets,
  charts: props.charts,
  selectedId: props.selectedId,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
})

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.datasets,
  (value) => base.setDatasets(value),
)

/** 是否注入处理函数（事件与注入双轨）。 */
const hasJobs = computed(() => props.jobs !== undefined)
/** 数据集清单。 */
const datasetList = computed(() => base.datasets.value)
/** 图表项清单。 */
const chartList = computed(() => base.charts.value)
/** 当前选中标识。 */
const selectedIdValue = computed(() => base.selectedId.value)
/** 脏标记（未注入 jobs 时以宿主受控为准）。 */
const dirtyFlag = computed(() => (hasJobs.value ? base.dirty.value : props.dirty))
/** 只读。 */
const readonly = computed(() => props.readOnly || base.readonly.value)
/** 当前选中图表项。 */
const selectedItem = computed(() => base.selectedItem.value)
/** 当前数据集。 */
const currentDataset = computed(
  () => base.datasets.value.find((dataset) => dataset.id === (base.designer.datasetId !== '' ? base.designer.datasetId : props.datasetId)),
)
/** 设计态预览取数结果。 */
const previewResult = ref<ChartDatasetResult | undefined>(undefined)
/** 预览加载中。 */
const previewLoading = ref(false)
/** 按图表项标识的数据（设计态预览结果分发）。 */
const chartData = computed<Record<string, ChartDatasetResult>>(() => {
  const source = previewResult.value
  if (source === undefined) {
    return {}
  }
  const result: Record<string, ChartDatasetResult> = {}
  for (const item of chartList.value) {
    result[item.id] = source
  }
  return result
})

/**
 * 设计态预览取数（数据集面板 / 配置面板触发）。
 *
 * @param datasetId 数据集标识。
 */
async function onPreviewData(datasetId: string): Promise<void> {
  if (!hasJobs.value) {
    return
  }
  const item = chartList.value.find((chart) => chart.datasetId === datasetId)
  if (item === undefined) {
    return
  }
  previewLoading.value = true
  const result = await base.preview(item.id)
  previewLoading.value = false
  if (result !== undefined) {
    previewResult.value = result
  }
}

/**
 * 点击数据集（事件双轨：始终上抛，注入 jobs 时驱动新增）。
 *
 * @param dataset 数据集。
 */
function onDataset(dataset: ReportDataset): void {
  if (dataset.status !== 'enabled' || readonly.value) {
    return
  }
  emit('add-chart', { datasetId: dataset.id, chartType: 'line' })
  if (hasJobs.value) {
    base.selectDataset(dataset.id)
    base.addChart({ datasetId: dataset.id, chartType: 'line' })
    emit('dataset-change', dataset.id)
  }
}

/**
 * 选中图表项。
 *
 * @param id 标识。
 */
function onSelect(id: string | null): void {
  base.selectChart(id)
  emit('select', id)
}

/**
 * 删除图表项。
 *
 * @param id 标识。
 */
function onRemove(id: string): void {
  emit('remove-chart', id)
  if (hasJobs.value) {
    base.removeChart(id)
  }
}

/**
 * 更新图表项（配置面板联动）。
 *
 * @param payload 变更。
 */
function onChartUpdate(payload: { id: string; patch: { title?: string; chartType?: string; config?: Record<string, unknown> } }): void {
  emit('chart-update', payload)
  if (hasJobs.value) {
    base.updateChart(payload.id, payload.patch)
  }
}

/**
 * 配置面板更新入口。
 *
 * @param payload 变更载荷。
 */
function onConfigUpdate(payload: { patch: { title?: string; chartType?: string; config?: Record<string, unknown> } }): void {
  const item = selectedItem.value
  if (item !== undefined) {
    onChartUpdate({ id: item.id, patch: payload.patch })
  }
}

/** 新建（脏数据时上抛拦截）。 */
function onNew(): void {
  if (base.needsBlock('new')) {
    emit('dirty-block', { action: 'new' })
    return
  }
  emit('new')
}

/**
 * 打开（脏数据时上抛拦截）。
 *
 * @param code 报表编码。
 */
function onOpen(code: string): void {
  if (base.needsBlock('open')) {
    emit('dirty-block', { action: 'open' })
    return
  }
  emit('open', { code })
  if (hasJobs.value) {
    void base.load({ code })
  }
}

/** 保存。 */
function onSave(): void {
  emit('save')
  if (hasJobs.value) {
    void base.save().then((result) => {
      if (result !== undefined) {
        emit('saved')
        emit('change', chartList.value)
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

/** 另存为。 */
function onSaveAs(): void {
  emit('save-as')
}

/** 预览（查看态切换）。 */
function onPreview(): void {
  emit('preview')
}

defineExpose({
  /** 设计器基类实例（开发态核对与宿主调试用）。 */
  designer: base.designer,
  /** 当前图表项。 */
  charts: base.charts,
  /** 是否脏。 */
  dirty: base.dirty,
  /** 是否只读。 */
  readonly: base.readonly,
})

/** 复制图表项。 */
function onDuplicate(id: string): void {
  if (hasJobs.value) {
    base.duplicateChart(id)
  }
}

/** 居中图表项。 */
function onCenter(id: string): void {
  if (hasJobs.value) {
    base.centerChart(id)
  }
}

/**
 * 移动图表项落点。
 *
 * @param payload 落点。
 */
function onMove(payload: { id: string; x: number; y: number }): void {
  if (hasJobs.value) {
    base.moveChart(payload.id, payload.x, payload.y)
  }
}

/**
 * 缩放图表项落点。
 *
 * @param payload 落点。
 */
function onResize(payload: { id: string; w: number; h: number }): void {
  if (hasJobs.value) {
    base.resizeChart(payload.id, payload.w, payload.h)
  }
}
</script>

<template>
  <div
    class="bms-report-designer"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
    :data-readonly="readonly"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-report-designer__toolbar" data-test="toolbar">
          <span class="bms-report-designer__code" data-test="report-code">{{ base.designer.reportCode }}</span>
          <span class="bms-report-designer__name" data-test="report-name">{{ base.designer.reportName }}</span>
          <el-button :disabled="readonly" data-test="new" @click="onNew">新建</el-button>
          <el-button :disabled="readonly" data-test="open" @click="onOpen('')">打开</el-button>
          <el-button :disabled="readonly" data-test="save" @click="onSave">保存</el-button>
          <el-button type="success" :disabled="readonly" data-test="publish" @click="onPublish">发布</el-button>
          <el-button :disabled="readonly" data-test="save-as" @click="onSaveAs">另存为</el-button>
          <el-button type="primary" data-test="preview" @click="onPreview">预览</el-button>
          <span v-if="dirtyFlag" class="bms-report-designer__dirty" data-test="dirty">● 未保存</span>
          <span v-if="!base.validation.value.valid" class="bms-report-designer__invalid" data-test="validation-error">
            {{ base.validation.value.message }}
          </span>
          <span v-if="readonly" class="bms-report-designer__readonly" data-test="readonly-hint">只读</span>
          <slot name="report-list" />
        </div>

        <div class="bms-report-designer__body">
          <section class="bms-report-designer__pane bms-report-designer__dataset" data-test="dataset-panel">
            <h4 class="bms-report-designer__pane-title">数据集</h4>
            <div class="bms-report-designer__pane-body">
              <slot name="dataset-panel" :datasets="datasetList">
                <el-button
                  v-for="dataset in datasets"
                  :key="dataset.id"
                  class="bms-report-designer__dataset-item"
                  :data-test="`dataset-${dataset.id}`"
                  :data-status="dataset.status"
                  :disabled="readonly || dataset.status !== 'enabled'"
                  @click="onDataset(dataset)"
                >
                  {{ dataset.name }}
                </el-button>
              </slot>
              <DatasetPanel
                :dataset="currentDataset"
                :datasets="datasetList"
                :dataset-id="base.designer.datasetId !== '' ? base.designer.datasetId : datasetId"
                :read-only="readonly"
                :preview-columns="previewResult?.columns ?? []"
                :preview-rows="previewResult?.rows ?? []"
                :preview-loading="previewLoading"
                @preview="(payload) => onPreviewData(payload.datasetId)"
              />
            </div>
          </section>

          <section class="bms-report-designer__pane bms-report-designer__canvas" data-test="canvas">
            <h4 class="bms-report-designer__pane-title">报表画布</h4>
            <div class="bms-report-designer__pane-body">
              <slot name="canvas">
                <ReportCanvas
                  :charts="chartList"
                  :selected-id="selectedIdValue"
                  :read-only="readonly"
                  :datasets="datasetList"
                  :chart-data="chartData"
                  @select="onSelect"
                  @remove-chart="onRemove"
                  @duplicate-chart="onDuplicate"
                  @center-chart="onCenter"
                  @move-chart="onMove"
                  @resize-chart="onResize"
                />
              </slot>
            </div>
          </section>

          <section class="bms-report-designer__pane bms-report-designer__config" data-test="config-panel">
            <h4 class="bms-report-designer__pane-title">图表配置</h4>
            <div class="bms-report-designer__pane-body">
              <slot name="config-panel" :item="selectedItem">
                <ChartConfigPanel
                  :item="selectedItem"
                  :fields="base.currentFields.value"
                  :read-only="readonly"
                  @update="onConfigUpdate"
                  @preview-data="() => currentDataset !== undefined && onPreviewData(currentDataset.id)"
                />
              </slot>
            </div>
          </section>
        </div>
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-report-designer {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-report-designer__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-3);
  background: var(--bms-color-fill);
  border-bottom: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}

.bms-report-designer__code {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-report-designer__name {
  color: var(--bms-color-text);
  font-weight: 600;
}

.bms-report-designer__dirty,
.bms-report-designer__invalid {
  color: var(--bms-color-danger);
  font-size: var(--bms-font-size-xs);
}

.bms-report-designer__readonly {
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-xs);
}

/* 三栏（数据集 240 / 画布自适应 / 配置 280），与原型栅格口径一致。 */
.bms-report-designer__body {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 280px;
  gap: var(--bms-space-3);
  align-items: start;
}

.bms-report-designer__pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 420px;
  background: var(--bms-report-panel-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-report-designer__pane-title {
  margin: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-report-designer__pane-body {
  flex: 1;
  min-width: 0;
  padding: var(--bms-space-3);
}

.bms-report-designer__dataset-item {
  display: flex;
  width: 100%;
  margin-bottom: var(--bms-space-1);
}

.bms-report-designer__dataset-item[data-status='disabled'] {
  color: var(--bms-color-text-secondary);
}

.bms-report-designer__canvas .bms-report-designer__pane-body {
  background: var(--bms-report-canvas-bg);
  border-radius: 0 0 var(--bms-radius-md) var(--bms-radius-md);
}

/* 窄容器改单列堆叠（与 `useResponsive` 缺省窄屏阈值一致）。 */
@media (max-width: 992px) {
  .bms-report-designer__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .bms-report-designer__pane {
    min-height: 0;
  }
}
</style>
