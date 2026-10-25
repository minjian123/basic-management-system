/** 报表设计器投影：把核心能力基类 `BaseReportDesigner` 投影为组合式（数据集 / 图表项 / 布局 / 脏基线 / 保存发布）。 */

import {
  BaseReportDesigner,
  type BaseAccess,
  type BaseAsyncTask,
  type BaseDataState,
  type BaseDragDrop,
  type BaseNotice,
  type ReportBlockAction,
  type ReportChartItem,
  type ReportDataset,
  type ReportJobs,
  type ReportPhase,
  type ReportPreviewResult,
  type ReportSaveResult,
  type ReportSnapshot,
  type ReportValidationResult,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体报表设计器件（可实例化）。 */
class ReportDesignerState extends BaseReportDesigner {}

/** 选项。 */
export interface UseBaseReportDesignerOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 报表编码。 */
  reportCode?: string
  /** 报表名称。 */
  reportName?: string
  /** 数据集清单。 */
  datasets?: readonly ReportDataset[]
  /** 图表项。 */
  charts?: readonly ReportChartItem[]
  /** 当前选中图表项标识。 */
  selectedId?: string
  /** 注入处理函数集（未注入即占位）。 */
  jobs?: ReportJobs
  /** 权限上下文（未注入视为有权）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 数据状态能力（预览取数）。 */
  dataState?: BaseDataState
  /** 拖拽能力（布局广播）。 */
  drag?: BaseDragDrop
  /** 异步任务能力。 */
  asyncTask?: BaseAsyncTask
}

/** `useBaseReportDesigner` 返回面。 */
export interface UseBaseReportDesignerResult {
  /** 报表设计器基类实例。 */
  designer: BaseReportDesigner
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 是否只读（响应式）。 */
  readonly: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 是否脏（响应式）。 */
  dirty: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<ReportPhase>
  /** 数据集清单（响应式）。 */
  datasets: Ref<ReportDataset[]>
  /** 图表项清单（响应式）。 */
  charts: Ref<ReportChartItem[]>
  /** 当前选中标识（响应式）。 */
  selectedId: Ref<string>
  /** 当前选中图表项（响应式）。 */
  selectedItem: Ref<ReportChartItem | undefined>
  /** 当前数据集字段（响应式）。 */
  currentFields: Ref<{ name: string; type: string }[]>
  /** 校验结果（响应式）。 */
  validation: Ref<ReportValidationResult>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: ReportJobs) => void
  /** 设置数据集清单。 */
  setDatasets: (datasets: readonly ReportDataset[]) => void
  /** 切换报表。 */
  setReportCode: (code: string, name?: string) => boolean
  /** 选择数据集。 */
  selectDataset: (datasetId: string) => boolean
  /** 新增图表项。 */
  addChart: (input?: { datasetId?: string; chartType?: string }) => ReportChartItem | undefined
  /** 移除图表项。 */
  removeChart: (id: string) => boolean
  /** 复制图表项。 */
  duplicateChart: (id: string) => boolean
  /** 移动图表项。 */
  moveChart: (id: string, x: number, y: number) => boolean
  /** 缩放图表项。 */
  resizeChart: (id: string, w: number, h: number) => boolean
  /** 居中图表项。 */
  centerChart: (id: string) => boolean
  /** 选中图表项。 */
  selectChart: (id: string | null) => void
  /** 更新图表项。 */
  updateChart: (id: string, patch: { title?: string; config?: Record<string, unknown>; chartType?: string }) => boolean
  /** 记脏基线。 */
  markBaseline: () => void
  /** 撤销。 */
  discard: () => boolean
  /** 是否拦截。 */
  needsBlock: (action: ReportBlockAction) => boolean
  /** 取数。 */
  load: (input?: { code?: string }) => Promise<ReportSnapshot | undefined>
  /** 预览取数。 */
  preview: (chartId: string, params?: Record<string, unknown>) => Promise<ReportPreviewResult | undefined>
  /** 保存。 */
  save: () => Promise<ReportSaveResult | undefined>
  /** 发布。 */
  publish: () => Promise<boolean>
  /** 另存为。 */
  saveAs: (code: string, name?: string) => Promise<ReportSaveResult | undefined>
}

/**
 * 使用报表设计器投影。
 *
 * @param options 选项。
 * @returns 报表设计器基类实例与响应式面。
 */
export function useBaseReportDesigner(options: UseBaseReportDesignerOptions = {}): UseBaseReportDesignerResult {
  const designer = new ReportDesignerState()
  designer.setReady(options.ready ?? false)
  if (options.reportCode !== undefined) {
    designer.reportCode = options.reportCode
  }
  if (options.reportName !== undefined) {
    designer.reportName = options.reportName
  }
  if (options.datasets !== undefined) {
    designer.setDatasets(options.datasets)
  }
  if (options.charts !== undefined) {
    designer.charts = options.charts.map((item) => ({ ...item, layout: { ...item.layout } }))
  }
  if (options.selectedId !== undefined) {
    designer.selectedId = options.selectedId
  }
  if (options.jobs !== undefined) {
    designer.jobs = options.jobs
  }
  if (options.access !== undefined) {
    designer.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    designer.notice = markRaw(toRaw(options.notice))
  }
  if (options.dataState !== undefined) {
    designer.dataState = markRaw(toRaw(options.dataState))
  }
  if (options.drag !== undefined) {
    designer.drag = markRaw(toRaw(options.drag))
  }
  if (options.asyncTask !== undefined) {
    designer.asyncTask = markRaw(toRaw(options.asyncTask))
  }

  const ready = ref(designer.ready)
  const degraded = ref(designer.degraded)
  const readonly = ref(designer.readonly)
  const busy = ref(designer.busy)
  const dirty = ref(designer.dirty)
  const phase = ref<ReportPhase>(designer.phase)
  const datasets = ref<ReportDataset[]>([...designer.datasets])
  const charts = ref<ReportChartItem[]>(designer.charts)
  const selectedId = ref(designer.selectedId)
  const selectedItem = ref<ReportChartItem | undefined>(designer.selectedItem)
  const currentFields = ref<{ name: string; type: string }[]>(designer.currentFields)
  const validation = ref<ReportValidationResult>(designer.validation)
  const errorMessage = ref(designer.errorMessage)
  const requestCount = ref(designer.requestCount)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = designer.ready
    degraded.value = designer.degraded
    readonly.value = designer.readonly
    busy.value = designer.busy
    dirty.value = designer.dirty
    phase.value = designer.phase
    datasets.value = [...designer.datasets]
    charts.value = designer.charts
    selectedId.value = designer.selectedId
    selectedItem.value = designer.selectedItem
    currentFields.value = designer.currentFields
    validation.value = designer.validation
    errorMessage.value = designer.errorMessage
    requestCount.value = designer.requestCount
  }

  const off = designer.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    designer.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    designer,
    ready,
    degraded,
    readonly,
    busy,
    dirty,
    phase,
    datasets,
    charts,
    selectedId,
    selectedItem,
    currentFields,
    validation,
    errorMessage,
    requestCount,
    setReady: (value) => run(() => designer.setReady(value)),
    setJobs: (jobs) => run(() => designer.setJobs(jobs)),
    setDatasets: (value) => run(() => designer.setDatasets(value)),
    setReportCode: (code, name) => run(() => designer.setReportCode(code, name)),
    selectDataset: (datasetId) => run(() => designer.selectDataset(datasetId)),
    addChart: (input) => run(() => designer.addChart(input)),
    removeChart: (id) => run(() => designer.removeChart(id)),
    duplicateChart: (id) => run(() => designer.duplicateChart(id)),
    moveChart: (id, x, y) => run(() => designer.moveChart(id, x, y)),
    resizeChart: (id, w, h) => run(() => designer.resizeChart(id, w, h)),
    centerChart: (id) => run(() => designer.centerChart(id)),
    selectChart: (id) => run(() => designer.selectChart(id)),
    updateChart: (id, patch) => run(() => designer.updateChart(id, patch)),
    markBaseline: () => run(() => designer.markBaseline()),
    discard: () => run(() => designer.discard()),
    needsBlock: (action) => designer.needsBlock(action),
    load: async (input) => {
      const value = await designer.load(input)
      sync()
      return value
    },
    preview: async (chartId, params) => {
      const value = await designer.preview(chartId, params)
      sync()
      return value
    },
    save: async () => {
      const value = await designer.save()
      sync()
      return value
    },
    publish: async () => {
      const value = await designer.publish()
      sync()
      return value
    },
    saveAs: async (code, name) => {
      const value = await designer.saveAs(code, name)
      sync()
      return value
    },
  }
}
