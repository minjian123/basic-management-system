/**
 * 图表组件基类：实例生命周期 / 尺寸自适应 / 主题令牌适配 / 四态与空态 / 导出。
 *
 * 组合数据状态能力基类 `BaseDataState`；图表引擎（ECharts 实例、容器、ResizeObserver）经
 * `ChartEngineAdapter` **注入**（渲染插件实现），核心只维护状态与调用语义，保持框架无关。
 * 图表卡、报表设计器、大屏与移动端经本基类派生取得统一行为，不在链外自由挂接。
 */

import { BaseDataState } from './data-state'
import {
  buildChartOption,
  buildChartTheme,
  CHART_EMPTY_TEXT,
  isChartEmpty,
  normalizeChartConfig,
  normalizeChartKind,
  resolveChartMode,
  shouldReplaceOption,
  shouldResize,
  type ChartConfig,
  type ChartDatasetResult,
  type ChartKind,
  type ChartMapping,
  type ChartRenderMode,
  type ChartTheme,
  type ChartThemeMode,
  type ChartTokenReader,
  type ChartView,
} from '../domain/chart'

/** 图表引擎适配器（由渲染插件实现：ECharts 实例 / 容器 / 尺寸监听全在此）。 */
export interface ChartEngineAdapter {
  /** 初始化实例。 */
  init?(payload: { theme: ChartTheme; renderMode: ChartRenderMode }): void
  /** 写入选项（`replace` 为真全量替换）。 */
  update?(option: Record<string, unknown>, replace: boolean): void
  /** 主题切换重建（图实例主题固化，需销毁重建）。 */
  applyTheme?(theme: ChartTheme, option: Record<string, unknown>): void
  /** 重算尺寸。 */
  resize?(): void
  /** 导出图片（dataURL）。 */
  exportImage?(type: 'png' | 'svg'): string | undefined
  /** 事件注册。 */
  on?(event: string, handler: (payload: unknown) => void): void
  /** 全量解绑。 */
  offAll?(): void
  /** 销毁（幂等）。 */
  dispose?(): void
}

/** 图表卡取数处理函数集（使用方注入；未注入即占位不请求）。 */
export interface ChartJobs {
  /** 数据集取数：返回 `{ columns, rows }`。 */
  load?: (input: { datasetId: string; params?: Record<string, unknown> }) => Promise<ChartDatasetResult | undefined>
}

/** 取数入参。 */
export interface ChartLoadInput {
  /** 数据集标识。 */
  datasetId: string
  /** 查询参数。 */
  params?: Record<string, unknown>
}

/** 图表组件基类（抽象）。 */
export abstract class BaseChart extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'chart'
  /** 依赖登记（数据状态能力基类）。 */
  override readonly depends = ['data-state']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 占位态请求计数（占位态恒 0）。 */
  requestCount = 0
  /** 图表配置。 */
  config: ChartConfig
  /** 数据集结果。 */
  result: ChartDatasetResult | undefined = undefined
  /** 完整选项直给（优先于由配置生成；高级用法）。 */
  rawOption: Record<string, unknown> | undefined = undefined
  /** 视图（图表 / 数据表）。 */
  view: ChartView = 'chart'
  /** 主题模式。 */
  themeMode: ChartThemeMode = 'auto'
  /** 渲染模式。 */
  renderMode: ChartRenderMode = 'canvas'
  /** 容器高度（px，0 表示由容器决定）。 */
  height = 0
  /** 已解析主题。 */
  theme: ChartTheme | undefined = undefined
  /** 引擎适配器（渲染件注入）。 */
  engine: ChartEngineAdapter | undefined = undefined
  /** 令牌读取口（宿主注入）。 */
  tokens: ChartTokenReader | undefined = undefined
  /** 是否偏好深色（宿主注入）。 */
  prefersDark = false
  /** 取数处理函数（使用方注入）。 */
  jobs: ChartJobs = {}
  /** 错误文案。 */
  errorMessage = ''
  /** 引擎是否已初始化。 */
  #mounted = false
  /** 是否正在取数。 */
  #loading = false
  /** 上次尺寸重算时间戳。 */
  #lastResizeMs = 0
  /** 最近一次取数入参。 */
  #lastInput: ChartLoadInput | undefined = undefined

  /**
   * 构造图表基类。
   *
   * @param namespace 命名空间。
   * @param version 版本。
   */
  constructor(namespace = 'bms', version = '0.0.0') {
    super(namespace, version)
    this.config = normalizeChartConfig(undefined)
    this.theme = buildChartTheme((name) => (this.tokens !== undefined ? this.tokens(name) : undefined), 'light')
  }

  /** 是否处于降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否空数据。 */
  get isEmpty(): boolean {
    return this.state === 'empty'
  }

  /** 是否加载中。 */
  get isLoading(): boolean {
    return this.state === 'loading' || this.#loading
  }

  /** 是否错误态。 */
  get isError(): boolean {
    return this.state === 'error'
  }

  /** 是否正在取数。 */
  get busy(): boolean {
    return this.#loading
  }

  /** 生成后的图表选项（`table` 类型返回 `undefined`）。 */
  get option(): Record<string, unknown> | undefined {
    if (this.rawOption !== undefined) {
      return this.rawOption
    }
    if (this.config.chartType === 'table' || this.theme === undefined) {
      return undefined
    }
    return buildChartOption(this.config, this.result, this.theme)
  }

  /** 当前生效主题。 */
  get activeTheme(): ChartTheme | undefined {
    return this.theme
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
   * 注入令牌读取口。
   *
   * @param reader 令牌读取口。
   */
  setTokens(reader: ChartTokenReader | undefined): void {
    this.tokens = reader
    this.#refreshTheme()
  }

  /**
   * 设置系统深色偏好。
   *
   * @param value 是否偏好深色。
   */
  setPrefersDark(value: boolean): void {
    if (this.prefersDark === value) {
      return
    }
    this.prefersDark = value
    this.#refreshTheme()
  }

  /**
   * 注入取数处理函数。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ChartJobs): void {
    this.jobs = jobs
    this.notifyLifecycle('update')
  }

  /**
   * 设置图表配置。
   *
   * @param config 图表配置。
   */
  setConfig(config: ChartConfig): void {
    const replace = shouldReplaceOption(this.config, config)
    this.config = config
    this.#writeOption(replace)
  }

  /**
   * 切换图表类型。
   *
   * @param kind 图表类型。
   */
  setChartType(kind: ChartKind): void {
    const next = normalizeChartKind(kind)
    if (this.config.chartType === next) {
      return
    }
    this.setConfig({ ...this.config, chartType: next })
  }

  /**
   * 设置数据映射。
   *
   * @param mapping 数据映射。
   */
  setMapping(mapping: ChartMapping): void {
    this.setConfig({ ...this.config, mapping })
  }

  /**
   * 设置视图。
   *
   * @param view 视图。
   */
  setView(view: ChartView): void {
    if (this.view === view) {
      return
    }
    this.view = view
    this.notifyLifecycle('update')
  }

  /**
   * 设置主题模式。
   *
   * @param mode 主题模式。
   */
  setThemeMode(mode: ChartThemeMode): void {
    if (this.themeMode === mode) {
      return
    }
    this.themeMode = mode
    this.#refreshTheme()
  }

  /**
   * 设置渲染模式。
   *
   * @param mode 渲染模式。
   */
  setRenderMode(mode: ChartRenderMode): void {
    if (this.renderMode === mode) {
      return
    }
    this.renderMode = mode
    this.#refreshTheme()
  }

  /**
   * 设置容器高度。
   *
   * @param height 高度（px）。
   */
  setHeight(height: number): void {
    const next = Number.isFinite(height) && height > 0 ? Math.floor(height) : 0
    if (this.height === next) {
      return
    }
    this.height = next
    this.notifyLifecycle('update')
  }

  /**
   * 注入图表引擎适配器。
   *
   * @param engine 引擎适配器。
   */
  setEngine(engine: ChartEngineAdapter | undefined): void {
    this.engine = engine
    if (engine === undefined) {
      this.#mounted = false
      this.notifyLifecycle('update')
      return
    }
    this.#mount()
  }

  /**
   * 写入数据集结果（就绪门控；未就绪只记录不初始化）。
   *
   * @param result 数据集结果。
   */
  setResult(result: ChartDatasetResult | undefined): void {
    const token = this.begin()
    this.#applyResult(result, token)
  }

  /**
   * 完整选项直给（优先于配置生成）。
   *
   * @param option 完整选项。
   */
  setRawOption(option: Record<string, unknown> | undefined): void {
    this.rawOption = option
    const token = this.begin()
    this.settle(token, option === undefined ? 'empty' : 'ready')
    this.#writeOption(true)
  }

  /**
   * 取数（占位 / 未注入处理函数时零请求）。
   *
   * @param input 取数入参。
   * @returns 数据集结果（占位 / 失败返回 `undefined`）。
   */
  async load(input: ChartLoadInput): Promise<ChartDatasetResult | undefined> {
    if (this.degraded || this.jobs.load === undefined || this.busy) {
      return undefined
    }
    this.#lastInput = input
    return this.#run()
  }

  /**
   * 刷新（复用最近一次取数入参）。
   *
   * @returns 数据集结果（占位 / 失败返回 `undefined`）。
   */
  async refresh(): Promise<ChartDatasetResult | undefined> {
    if (this.#lastInput === undefined) {
      return undefined
    }
    return this.load(this.#lastInput)
  }

  /**
   * 尺寸自适应（节流）。
   *
   * @param nowMs 当前时间戳（缺省取当前时间）。
   * @returns 是否触发重算。
   */
  resize(nowMs: number = Date.now()): boolean {
    if (this.degraded || this.engine === undefined) {
      return false
    }
    if (!shouldResize(this.#lastResizeMs, nowMs)) {
      return false
    }
    this.#lastResizeMs = nowMs
    this.engine.resize?.()
    return true
  }

  /**
   * 导出图片。
   *
   * @param type 图片类型。
   * @returns dataURL（占位 / 无引擎返回 `undefined`）。
   */
  exportImage(type: 'png' | 'svg' = 'png'): string | undefined {
    if (this.degraded || this.engine === undefined) {
      return undefined
    }
    return this.engine.exportImage?.(type)
  }

  /** 空数据文案。 */
  get emptyText(): string {
    return CHART_EMPTY_TEXT
  }

  /** 释放：销毁引擎实例。 */
  protected override onDispose(): void {
    this.engine?.dispose?.()
    this.#mounted = false
    super.onDispose()
  }

  /**
   * 执行一次取数（内部）。
   *
   * @returns 数据集结果。
   */
  async #run(): Promise<ChartDatasetResult | undefined> {
    this.#loading = true
    this.errorMessage = ''
    this.requestCount += 1
    const token = this.begin()
    try {
      const result = await this.jobs.load?.({ datasetId: this.#lastInput?.datasetId ?? '', params: this.#lastInput?.params })
      if (result !== undefined) {
        this.#applyResult(result, token)
      } else {
        this.settle(token, 'empty')
      }
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.settle(token, 'error')
      this.reportError(error, { scope: 'BaseChart.load' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#loading = false
    }
  }

  /**
   * 应用数据集结果并按空判定结算状态。
   *
   * @param result 数据集结果。
   * @param token 竞态令牌。
   */
  #applyResult(result: ChartDatasetResult | undefined, token: number): void {
    this.result = result
    const empty = this.rawOption === undefined && isChartEmpty(result, this.config)
    this.settle(token, empty ? 'empty' : 'ready')
    if (!this.degraded && !empty) {
      this.#writeOption(true)
    }
    this.notifyLifecycle('update')
  }

  /**
   * 写入选项到引擎（未就绪 / 无引擎 / 空数据不初始化）。
   *
   * @param replace 是否全量替换。
   */
  #writeOption(replace: boolean): void {
    if (this.degraded) {
      return
    }
    this.#mount(replace)
  }

  /**
   * 装载引擎并写入当前选项（未就绪 / 无引擎 / 空数据不初始化）。
   *
   * @param replace 是否全量替换。
   */
  #mount(replace = true): void {
    if (this.degraded || this.engine === undefined || this.config.chartType === 'table') {
      return
    }
    if (this.rawOption === undefined && isChartEmpty(this.result, this.config)) {
      return
    }
    const option = this.option
    if (option === undefined) {
      return
    }
    const theme = this.theme
    if (theme === undefined) {
      return
    }
    if (!this.#mounted) {
      this.engine.init?.({ theme, renderMode: this.renderMode })
      this.#mounted = true
    }
    this.engine.update?.(option, replace)
  }

  /** 重算主题并在引擎已装载时重建（主题切换）。 */
  #refreshTheme(): void {
    const mode = resolveChartMode(this.themeMode, this.prefersDark)
    const reader: ChartTokenReader = (name) => (this.tokens !== undefined ? this.tokens(name) : undefined)
    this.theme = buildChartTheme(reader, mode)
    if (this.#mounted && this.engine !== undefined) {
      this.engine.applyTheme?.(this.theme, this.option ?? {})
    }
    this.notifyLifecycle('update')
  }
}
