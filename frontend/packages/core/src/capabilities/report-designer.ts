/**
 * 报表设计器编排能力基类：数据集选择 / 图表项增删改 / 网格布局 / 脏基线 / 预览取数 / 保存发布另存。
 *
 * 组合权限、提示、数据状态、拖拽与异步任务能力基类；取数 / 保存 / 发布 / 另存 / 预览处理函数由宿主注入，
 * 未注入即占位（不请求、返回 `undefined` / `false`）；判定落在 `domain/report-layout.ts`。
 */

import { BaseComponent } from '../base/BaseComponent'
import { BaseAccess } from './access'
import { BaseAsyncTask } from './async-task'
import { BaseDataState } from './data-state'
import { BaseDragDrop } from './drag-drop'
import { BaseNotice } from './notice'
import {
  addChartItem,
  centerChartItem,
  duplicateChartItem,
  findChartItem,
  isReportDirty,
  moveChartItem,
  normalizeReportCharts,
  removeChartItem,
  resizeChartItem,
  updateChartItem,
  validateReport,
  type ReportChartItem,
  type ReportDataset,
  type ReportDefinition,
  type ReportField,
  type ReportValidationResult,
  REPORT_DESIGN_PERM,
} from '../domain/report-layout'

/** 设计阶段。 */
export type ReportPhase = 'idle' | 'loading' | 'saving' | 'publishing' | 'done' | 'failed'
/** 取数快照。 */
export interface ReportSnapshot {
  /** 报表编码。 */
  code: string
  /** 报表名称。 */
  name: string
  /** 图表项。 */
  charts?: readonly ReportChartItem[]
}
/** 保存结果。 */
export interface ReportSaveResult {
  /** 记录版本。 */
  recordVersion?: number
}
/** 预览取数结果。 */
export interface ReportPreviewResult {
  /** 字段声明。 */
  columns: ReportField[]
  /** 数据行。 */
  rows: Record<string, unknown>[]
}
/** 注入的处理函数集（未注入即占位不请求）。 */
export interface ReportJobs {
  /** 取数。 */
  load?: (input: { code?: string }) => Promise<ReportSnapshot | undefined>
  /** 保存。 */
  save?: (input: ReportDefinition) => Promise<ReportSaveResult | undefined>
  /** 发布。 */
  publish?: (input: { code: string }) => Promise<void>
  /** 另存为。 */
  saveAs?: (input: ReportDefinition) => Promise<ReportSaveResult | undefined>
  /** 设计态预览取数（只读从库口径）。 */
  preview?: (input: { chartId: string; datasetId: string; params?: Record<string, unknown> }) => Promise<ReportPreviewResult | undefined>
}
/** 脏数据拦截场景。 */
export type ReportBlockAction = 'new' | 'open' | 'leave'

/** 报表设计器编排能力基类（抽象）。 */
export abstract class BaseReportDesigner extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'report-designer'
  /** 依赖登记。 */
  override readonly depends = ['access', 'notice', 'data-state', 'drag-drop', 'async-task']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 占位态请求计数（占位态恒 0）。 */
  requestCount = 0
  /** 报表编码。 */
  reportCode = ''
  /** 报表名称。 */
  reportName = ''
  /** 数据集清单。 */
  datasets: ReportDataset[] = []
  /** 当前选中数据集标识。 */
  datasetId = ''
  /** 图表项清单。 */
  charts: ReportChartItem[] = []
  /** 脏基线图表项清单。 */
  baseline: ReportChartItem[] | undefined = undefined
  /** 当前选中图表项标识。 */
  selectedId = ''
  /** 当前阶段。 */
  phase: ReportPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 注入的处理函数集。 */
  jobs: ReportJobs = {}
  /** 权限上下文。 */
  access: BaseAccess | undefined = undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined = undefined
  /** 数据状态能力（预览取数）。 */
  dataState: BaseDataState | undefined = undefined
  /** 拖拽能力（布局广播）。 */
  drag: BaseDragDrop | undefined = undefined
  /** 异步任务能力。 */
  asyncTask: BaseAsyncTask | undefined = undefined
  /** 是否进行中。 */
  #busy = false

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否只读（占位 / 无权限）。 */
  get readonly(): boolean {
    return this.degraded || !this.#hasDesign()
  }

  /** 是否可编辑。 */
  get canEdit(): boolean {
    return !this.readonly && !this.#busy
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.#busy
  }

  /** 是否脏。 */
  get dirty(): boolean {
    return isReportDirty(this.charts, this.baseline)
  }

  /** 是否可保存。 */
  get canSave(): boolean {
    return this.canEdit && this.validation.valid
  }

  /** 校验结果。 */
  get validation(): ReportValidationResult {
    return validateReport(this.charts, this.datasets)
  }

  /** 当前选中图表项。 */
  get selectedItem(): ReportChartItem | undefined {
    return findChartItem(this.charts, this.selectedId)
  }

  /** 当前数据集。 */
  get currentDataset(): ReportDataset | undefined {
    return this.datasets.find((dataset) => dataset.id === this.datasetId)
  }

  /** 当前数据集字段清单。 */
  get currentFields(): ReportField[] {
    return this.currentDataset?.fields !== undefined ? [...this.currentDataset.fields] : []
  }

  /**
   * 切换就绪态。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    this.notifyLifecycle('update')
  }

  /**
   * 注入处理函数集。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ReportJobs): void {
    this.jobs = jobs
    this.notifyLifecycle('update')
  }

  /**
   * 注入权限上下文。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.notifyLifecycle('update')
  }

  /**
   * 注入提示通知。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.notifyLifecycle('update')
  }

  /**
   * 注入数据状态能力。
   *
   * @param state 数据状态能力。
   */
  setDataState(state: BaseDataState | undefined): void {
    this.dataState = state
    this.notifyLifecycle('update')
  }

  /**
   * 注入拖拽能力。
   *
   * @param drag 拖拽能力。
   */
  setDrag(drag: BaseDragDrop | undefined): void {
    this.drag = drag
    this.notifyLifecycle('update')
  }

  /**
   * 注入异步任务能力。
   *
   * @param task 异步任务能力。
   */
  setAsyncTask(task: BaseAsyncTask | undefined): void {
    this.asyncTask = task
    this.notifyLifecycle('update')
  }

  /**
   * 设置数据集清单（当前数据集失效时重置）。
   *
   * @param datasets 数据集清单。
   */
  setDatasets(datasets: readonly ReportDataset[]): void {
    this.datasets = [...datasets]
    if (this.datasetId !== '' && !this.datasets.some((dataset) => dataset.id === this.datasetId)) {
      this.datasetId = ''
    }
    this.notifyLifecycle('update')
  }

  /**
   * 切换报表（脏数据时不切换并返回 `false`）。
   *
   * @param code 报表编码。
   * @param name 报表名称。
   * @returns 是否切换成功。
   */
  setReportCode(code: string, name = ''): boolean {
    if (this.dirty) {
      return false
    }
    this.reportCode = code
    this.reportName = name
    this.selectedId = ''
    this.datasetId = ''
    this.charts = []
    this.baseline = undefined
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 选择数据集（停用 / 不存在不可选）。
   *
   * @param datasetId 数据集标识。
   * @returns 是否选中成功。
   */
  selectDataset(datasetId: string): boolean {
    if (this.readonly) {
      return false
    }
    const dataset = this.datasets.find((entry) => entry.id === datasetId)
    if (dataset === undefined || dataset.status !== 'enabled') {
      return false
    }
    this.datasetId = datasetId
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 新增图表项。
   *
   * @param input 新增入参。
   * @returns 新增图表项（只读 / 无数据集返回 `undefined`）。
   */
  addChart(input: { datasetId?: string; chartType?: string } = {}): ReportChartItem | undefined {
    if (!this.canEdit) {
      return undefined
    }
    const datasetId = input.datasetId ?? this.datasetId
    const dataset = this.datasets.find((entry) => entry.id === datasetId)
    if (dataset === undefined || dataset.status !== 'enabled') {
      return undefined
    }
    const next = addChartItem(this.charts, { datasetId, chartType: input.chartType })
    const created = next[next.length - 1]
    this.charts = next
    this.selectedId = created.id
    if (this.datasetId !== datasetId) {
      this.datasetId = datasetId
    }
    this.notifyLifecycle('update')
    return created
  }

  /**
   * 移除图表项。
   *
   * @param id 标识。
   * @returns 是否生效。
   */
  removeChart(id: string): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = removeChartItem(this.charts, id)
    if (this.selectedId === id) {
      this.selectedId = ''
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 复制图表项。
   *
   * @param id 标识。
   * @returns 是否生效。
   */
  duplicateChart(id: string): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = duplicateChartItem(this.charts, id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 移动图表项（网格落点）。
   *
   * @param id 标识。
   * @param x 目标列。
   * @param y 目标行。
   * @returns 是否生效。
   */
  moveChart(id: string, x: number, y: number): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = moveChartItem(this.charts, id, x, y)
    this.#emitDrop(id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 缩放图表项。
   *
   * @param id 标识。
   * @param w 宽（列）。
   * @param h 高（行）。
   * @returns 是否生效。
   */
  resizeChart(id: string, w: number, h: number): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = resizeChartItem(this.charts, id, w, h)
    this.#emitDrop(id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 居中图表项。
   *
   * @param id 标识。
   * @returns 是否生效。
   */
  centerChart(id: string): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = centerChartItem(this.charts, id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 选中图表项。
   *
   * @param id 标识（`null` 清空）。
   */
  selectChart(id: string | null): void {
    this.selectedId = id ?? ''
    this.notifyLifecycle('update')
  }

  /**
   * 更新图表项（标题 / 类型 / 配置）。
   *
   * @param id 标识。
   * @param patch 变更。
   * @returns 是否生效。
   */
  updateChart(id: string, patch: { title?: string; config?: Record<string, unknown>; chartType?: string }): boolean {
    if (!this.canEdit || findChartItem(this.charts, id) === undefined) {
      return false
    }
    this.charts = updateChartItem(this.charts, id, patch)
    this.notifyLifecycle('update')
    return true
  }

  /** 记脏基线。 */
  markBaseline(): void {
    this.baseline = this.charts.map((item) => ({ ...item, layout: { ...item.layout } }))
    this.notifyLifecycle('update')
  }

  /**
   * 撤销未保存变更（回到基线）。
   *
   * @returns 是否发生回滚。
   */
  discard(): boolean {
    if (this.baseline === undefined || !this.dirty) {
      return false
    }
    this.charts = this.baseline.map((item) => ({ ...item, layout: { ...item.layout } }))
    this.selectedId = findChartItem(this.charts, this.selectedId) !== undefined ? this.selectedId : ''
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 是否需要拦截（脏数据）。
   *
   * @param action 动作。
   * @returns 是否拦截。
   */
  needsBlock(action: ReportBlockAction): boolean {
    void action
    return this.dirty
  }

  /**
   * 取数（占位 / 未注入处理函数时零请求）。
   *
   * @param input 入参。
   * @returns 快照（占位 / 失败返回 `undefined`）。
   */
  async load(input: { code?: string } = {}): Promise<ReportSnapshot | undefined> {
    if (this.degraded || this.jobs.load === undefined || this.#busy) {
      return undefined
    }
    this.#busy = true
    this.errorMessage = ''
    this.requestCount += 1
    this.phase = 'loading'
    const token = this.dataState?.begin()
    this.notifyLifecycle('update')
    try {
      const snapshot = await this.jobs.load(input)
      if (snapshot !== undefined) {
        this.reportCode = snapshot.code
        this.reportName = snapshot.name
        this.charts = normalizeReportCharts(snapshot.charts)
        this.selectedId = ''
        this.markBaseline()
      }
      if (token !== undefined) {
        this.dataState?.settle(token, 'ready')
      }
      this.phase = 'done'
      this.notifyLifecycle('update')
      return snapshot
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseReportDesigner.load' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 设计态预览取数（只读从库口径）。
   *
   * @param chartId 图表项标识。
   * @param params 查询参数。
   * @returns 取数结果（占位 / 失败返回 `undefined`）。
   */
  async preview(chartId: string, params?: Record<string, unknown>): Promise<ReportPreviewResult | undefined> {
    if (this.degraded || this.jobs.preview === undefined || this.#busy) {
      return undefined
    }
    const item = findChartItem(this.charts, chartId)
    if (item === undefined) {
      return undefined
    }
    this.requestCount += 1
    const token = this.dataState?.begin()
    try {
      const result = await this.jobs.preview({ chartId, datasetId: item.datasetId, params })
      if (token !== undefined) {
        this.dataState?.settle(token, result !== undefined ? 'ready' : 'empty')
      }
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.reportError(error, { scope: 'BaseReportDesigner.preview' })
      return undefined
    }
  }

  /**
   * 保存（覆盖式提交）。
   *
   * @returns 保存结果（不可保存 / 未注入返回 `undefined`）。
   */
  async save(): Promise<ReportSaveResult | undefined> {
    if (!this.canSave || this.jobs.save === undefined) {
      return undefined
    }
    this.#busy = true
    this.errorMessage = ''
    this.phase = 'saving'
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.save(this.#definition())
      this.markBaseline()
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseReportDesigner.save' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 发布（依赖保存成功，由件层先保存）。
   *
   * @returns 是否发布成功。
   */
  async publish(): Promise<boolean> {
    if (this.degraded || this.jobs.publish === undefined || this.#busy) {
      return false
    }
    this.#busy = true
    this.phase = 'publishing'
    this.notifyLifecycle('update')
    try {
      await this.jobs.publish({ code: this.reportCode })
      this.phase = 'done'
      this.notifyLifecycle('update')
      return true
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseReportDesigner.publish' })
      this.notifyLifecycle('update')
      return false
    } finally {
      this.#busy = false
    }
  }

  /**
   * 另存为（以当前图表项新建报表定义）。
   *
   * @param code 新报表编码。
   * @param name 新报表名称。
   * @returns 保存结果（未注入返回 `undefined`）。
   */
  async saveAs(code: string, name = ''): Promise<ReportSaveResult | undefined> {
    if (this.degraded || this.jobs.saveAs === undefined || this.#busy) {
      return undefined
    }
    this.#busy = true
    this.phase = 'saving'
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.saveAs({ code, name, charts: this.charts })
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseReportDesigner.saveAs' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /** 当前保存载荷。 */
  #definition(): ReportDefinition {
    return { code: this.reportCode, name: this.reportName, charts: this.charts.map((item) => ({ ...item, layout: { ...item.layout } })) }
  }

  /** 是否持设计权限。 */
  #hasDesign(): boolean {
    return this.access === undefined || this.access.has(REPORT_DESIGN_PERM)
  }

  /**
   * 广播布局落点（拖拽能力未注入仍完成落点）。
   *
   * @param id 标识。
   */
  #emitDrop(id: string): void {
    this.drag?.emitDrag({ phase: 'drop', source: id, crossZone: false })
  }
}
