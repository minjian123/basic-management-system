/** 图表组件基类投影：把核心组件基类 `BaseChart` 投影为组合式（配置 / 选项 / 主题 / 四态 / 取数）。 */

import {
  BaseChart,
  normalizeChartConfig,
  type ChartConfig,
  type ChartDatasetResult,
  type ChartEngineAdapter,
  type ChartJobs,
  type ChartKind,
  type ChartMapping,
  type ChartRenderMode,
  type ChartTheme,
  type ChartThemeMode,
  type ChartTokenReader,
  type ChartView,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体图表件（可实例化）。 */
class ChartState extends BaseChart {}

/** 选项。 */
export interface UseBaseChartOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 图表配置（优先）。 */
  config?: ChartConfig
  /** 完整选项直给（优先于配置生成）。 */
  option?: Record<string, unknown>
  /** 便捷图表类型（无配置时生效）。 */
  chartType?: ChartKind
  /** 数据映射。 */
  mapping?: ChartMapping
  /** 数据集结果。 */
  result?: ChartDatasetResult
  /** 视图。 */
  view?: ChartView
  /** 主题模式。 */
  themeMode?: ChartThemeMode
  /** 渲染模式。 */
  renderMode?: ChartRenderMode
  /** 容器高度（px）。 */
  height?: number
  /** 令牌读取口。 */
  tokens?: ChartTokenReader
  /** 深色偏好。 */
  prefersDark?: boolean
  /** 取数处理函数（未注入即占位）。 */
  jobs?: ChartJobs
  /** 引擎适配器（由渲染件注入）。 */
  engine?: ChartEngineAdapter
}

/** `useBaseChart` 返回面。 */
export interface UseBaseChartResult {
  /** 图表基类实例。 */
  chart: BaseChart
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 数据状态（响应式）。 */
  state: Ref<string>
  /** 视图（响应式）。 */
  view: Ref<ChartView>
  /** 图表配置（响应式）。 */
  config: Ref<ChartConfig>
  /** 生成后的选项（响应式）。 */
  option: Ref<Record<string, unknown> | undefined>
  /** 当前主题（响应式）。 */
  theme: Ref<ChartTheme | undefined>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入令牌读取口。 */
  setTokens: (reader: ChartTokenReader | undefined) => void
  /** 设置深色偏好。 */
  setPrefersDark: (value: boolean) => void
  /** 注入取数处理函数。 */
  setJobs: (jobs: ChartJobs) => void
  /** 设置图表配置。 */
  setConfig: (config: ChartConfig) => void
  /** 完整选项直给。 */
  setRawOption: (option: Record<string, unknown> | undefined) => void
  /** 切换图表类型。 */
  setChartType: (kind: ChartKind) => void
  /** 设置数据映射。 */
  setMapping: (mapping: ChartMapping) => void
  /** 设置视图。 */
  setView: (view: ChartView) => void
  /** 设置主题模式。 */
  setThemeMode: (mode: ChartThemeMode) => void
  /** 设置渲染模式。 */
  setRenderMode: (mode: ChartRenderMode) => void
  /** 设置容器高度。 */
  setHeight: (height: number) => void
  /** 注入引擎适配器。 */
  setEngine: (engine: ChartEngineAdapter | undefined) => void
  /** 写入数据集结果。 */
  setResult: (result: ChartDatasetResult | undefined) => void
  /** 取数。 */
  load: (input: { datasetId: string; params?: Record<string, unknown> }) => Promise<ChartDatasetResult | undefined>
  /** 刷新。 */
  refresh: () => Promise<ChartDatasetResult | undefined>
  /** 尺寸自适应。 */
  resize: (nowMs?: number) => boolean
  /** 导出图片。 */
  exportImage: (type?: 'png' | 'svg') => string | undefined
}

/**
 * 使用图表组件基类投影。
 *
 * @param options 选项。
 * @returns 图表基类实例与响应式面。
 */
export function useBaseChart(options: UseBaseChartOptions = {}): UseBaseChartResult {
  const chart = new ChartState()
  if (options.config !== undefined) {
    chart.setConfig(normalizeChartConfig(options.config, options.result?.columns))
  } else {
    chart.setChartType(options.chartType ?? 'line')
    if (options.mapping !== undefined) {
      chart.setMapping(options.mapping)
    }
  }
  if (options.result !== undefined) {
    chart.setResult(options.result)
  }
  if (options.option !== undefined) {
    chart.setRawOption(options.option)
  }
  if (options.view !== undefined) {
    chart.setView(options.view)
  }
  if (options.themeMode !== undefined) {
    chart.setThemeMode(options.themeMode)
  }
  if (options.renderMode !== undefined) {
    chart.setRenderMode(options.renderMode)
  }
  if (options.height !== undefined) {
    chart.setHeight(options.height)
  }
  if (options.tokens !== undefined) {
    chart.setTokens(options.tokens)
  }
  chart.setPrefersDark(options.prefersDark ?? false)
  if (options.jobs !== undefined) {
    chart.setJobs(options.jobs)
  }
  if (options.engine !== undefined) {
    chart.setEngine(markRaw(toRaw(options.engine)))
  }
  chart.setReady(options.ready ?? false)

  const ready = ref(chart.ready)
  const degraded = ref(chart.degraded)
  const state = ref<string>(chart.state)
  const view = ref<ChartView>(chart.view)
  const config = ref<ChartConfig>(chart.config)
  const option = ref<Record<string, unknown> | undefined>(chart.option)
  const theme = ref<ChartTheme | undefined>(chart.theme)
  const requestCount = ref(chart.requestCount)
  const errorMessage = ref(chart.errorMessage)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = chart.ready
    degraded.value = chart.degraded
    state.value = chart.state
    view.value = chart.view
    config.value = chart.config
    option.value = chart.option
    theme.value = chart.theme
    requestCount.value = chart.requestCount
    errorMessage.value = chart.errorMessage
  }

  const off = chart.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    chart.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    chart,
    ready,
    degraded,
    state,
    view,
    config,
    option,
    theme,
    requestCount,
    errorMessage,
    setReady: (value) => run(() => chart.setReady(value)),
    setTokens: (reader) => run(() => chart.setTokens(reader)),
    setPrefersDark: (value) => run(() => chart.setPrefersDark(value)),
    setJobs: (jobs) => run(() => chart.setJobs(jobs)),
    setConfig: (value) => run(() => chart.setConfig(normalizeChartConfig(value))),
    setRawOption: (value) => run(() => chart.setRawOption(value)),
    setChartType: (kind) => run(() => chart.setChartType(kind)),
    setMapping: (mapping) => run(() => chart.setMapping(mapping)),
    setView: (next) => run(() => chart.setView(next)),
    setThemeMode: (mode) => run(() => chart.setThemeMode(mode)),
    setRenderMode: (mode) => run(() => chart.setRenderMode(mode)),
    setHeight: (height) => run(() => chart.setHeight(height)),
    setEngine: (engine) => run(() => chart.setEngine(engine === undefined ? undefined : markRaw(toRaw(engine)))),
    setResult: (result) => run(() => chart.setResult(result)),
    load: async (input) => {
      const value = await chart.load(input)
      sync()
      return value
    },
    refresh: async () => {
      const value = await chart.refresh()
      sync()
      return value
    },
    resize: (nowMs) => run(() => chart.resize(nowMs)),
    exportImage: (type) => chart.exportImage(type),
  }
}
