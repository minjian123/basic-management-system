/**
 * ECharts 内核适配（独立分包入口）：动态 `import()` ECharts 内核并按需注册图表 / 组件 / 渲染器，
 * 注册令牌主题与地图地理数据，向 `ChartRenderer` 提供 `ChartEngineAdapter`。
 *
 * 浏览器 API 与 ECharts 只出现在本工具与图表件；核心与投影不触 DOM / 第三方。
 */

import { BaseChartEngine, shouldResize, type ChartRenderMode, type ChartTheme } from '@bms/core'

/** ECharts 实例最小面。 */
interface EchartsInstance {
  /** 写入配置。 */
  setOption: (option: Record<string, unknown>, notMerge?: boolean) => void
  /** 重算尺寸。 */
  resize: () => void
  /** 销毁实例。 */
  dispose: () => void
  /** 导出 dataURL。 */
  getDataURL: (opts?: Record<string, unknown>) => string
  /** 注册事件。 */
  on: (event: string, handler: (params: unknown) => void) => void
  /** 解绑事件。 */
  off: (event: string) => void
}

/** ECharts 内核最小面。 */
interface EchartsCore {
  /** 注册扩展。 */
  use: (modules: unknown[]) => void
  /** 注册主题。 */
  registerTheme: (name: string, theme: Record<string, unknown>) => void
  /** 注册地图。 */
  registerMap: (name: string, geo: unknown) => void
  /** 初始化实例。 */
  init: (el: HTMLElement, theme?: string, opts?: { renderer?: ChartRenderMode }) => EchartsInstance
}

/** 引擎装载选项。 */
export interface EchartsEngineOptions {
  /** 容器读取口（延迟取，容器挂载后才有效）。 */
  container: () => HTMLElement | undefined
  /** 渲染模式（缺省 `canvas`）。 */
  renderMode?: ChartRenderMode
  /** 初始主题。 */
  theme?: ChartTheme
}

/** 内核装载 Promise（单例，多个图表共享）。 */
let corePromise: Promise<EchartsCore> | undefined

/**
 * 装载并注册 ECharts 内核（单例）。
 *
 * @returns 内核最小面。
 */
async function loadCore(): Promise<EchartsCore> {
  if (corePromise === undefined) {
    corePromise = (async () => {
      const core = (await import('echarts/core')) as unknown as EchartsCore
      const charts = await import('echarts/charts')
      const components = await import('echarts/components')
      const renderers = await import('echarts/renderers')
      const features = await import('echarts/features')
      core.use([
        charts.LineChart,
        charts.BarChart,
        charts.PieChart,
        charts.ScatterChart,
        charts.FunnelChart,
        charts.RadarChart,
        charts.GaugeChart,
        charts.MapChart,
        components.GridComponent,
        components.TooltipComponent,
        components.LegendComponent,
        components.TitleComponent,
        components.ToolboxComponent,
        components.DataZoomComponent,
        components.MarkLineComponent,
        components.RadarComponent,
        components.GeoComponent,
        renderers.CanvasRenderer,
        renderers.SVGRenderer,
        features.LabelLayout,
        features.UniversalTransition,
      ])
      return core
    })()
  }
  return corePromise
}

/**
 * 把令牌主题转换为 ECharts 主题对象。
 *
 * @param theme 令牌主题。
 * @returns ECharts 主题对象。
 */
function toEchartsTheme(theme: ChartTheme): Record<string, unknown> {
  return {
    color: theme.color,
    textStyle: { color: theme.text },
    categoryAxis: {
      axisLine: { lineStyle: { color: theme.axis } },
      axisLabel: { color: theme.text },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    valueAxis: {
      axisLine: { lineStyle: { color: theme.axis } },
      axisLabel: { color: theme.text },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    legend: { textStyle: { color: theme.text } },
    tooltip: { backgroundColor: theme.tooltipBg, borderColor: theme.axis, textStyle: { color: theme.tooltipText } },
  }
}

/**
 * 创建 ECharts 引擎（插件基类 `BaseChartEngine` 的内建实现，动态装载内核 / 独立分包）。
 *
 * @param options 装载选项。
 * @returns 引擎插件实例。
 */
export async function createEchartsEngine(options: EchartsEngineOptions): Promise<BaseChartEngine> {
  const core = await loadCore()
  let instance: EchartsInstance | undefined
  let observer: ResizeObserver | undefined
  let theme: ChartTheme = options.theme ?? {
    name: 'bms-light',
    mode: 'light',
    color: [],
    axis: '',
    grid: '',
    text: '',
    tooltipBg: '',
    tooltipText: '',
  }
  let renderMode: ChartRenderMode = options.renderMode ?? 'canvas'
  let pendingOption: Record<string, unknown> | undefined
  let lastResizeMs = 0
  const handlers = new Map<string, (params: unknown) => void>()

  /**
   * 初始化实例（容器可见且宽高 > 0 才初始化）。
   *
   * @returns 实例（不可用时 `undefined`）。
   */
  const ensure = (): EchartsInstance | undefined => {
    if (instance !== undefined) {
      return instance
    }
    const el = options.container()
    if (el === undefined || el.clientWidth === 0 || el.clientHeight === 0) {
      return undefined
    }
    core.registerTheme(theme.name, toEchartsTheme(theme))
    instance = core.init(el, theme.name, { renderer: renderMode })
    for (const [event, handler] of handlers) {
      instance.on(event, handler)
    }
    observer = new ResizeObserver(() => {
      if (instance === undefined) {
        return
      }
      const now = Date.now()
      if (shouldResize(lastResizeMs, now)) {
        lastResizeMs = now
        instance.resize()
      }
    })
    observer.observe(el)
    if (pendingOption !== undefined) {
      instance.setOption(pendingOption, true)
      pendingOption = undefined
    }
    return instance
  }

  /** ECharts 图表引擎（插件基类内建实现）。 */
  class EchartsChartEngine extends BaseChartEngine {
    /** 实现名。 */
    override readonly pluginName = 'echarts'

    /**
     * 初始化实例。
     *
     * @param payload 主题与渲染模式。
     */
    override init(payload: { theme: ChartTheme; renderMode: ChartRenderMode }): void {
      theme = payload.theme
      renderMode = payload.renderMode
      ensure()
    }

    /**
     * 写入选项。
     *
     * @param option 选项。
     * @param replace 是否全量替换。
     */
    override update(option: Record<string, unknown>, replace: boolean): void {
      const target = ensure()
      if (target === undefined) {
        pendingOption = option
        return
      }
      target.setOption(option, replace)
    }

    /**
     * 主题切换重建。
     *
     * @param nextTheme 主题。
     * @param option 选项。
     */
    override applyTheme(nextTheme: ChartTheme, option: Record<string, unknown>): void {
      theme = nextTheme
      observer?.disconnect()
      observer = undefined
      instance?.dispose()
      instance = undefined
      const target = ensure()
      if (target !== undefined) {
        target.setOption(option, true)
      }
    }

    /** 重算尺寸。 */
    override resize(): void {
      instance?.resize()
    }

    /**
     * 导出图片。
     *
     * @param type 图片类型。
     * @returns dataURL。
     */
    override exportImage(type: 'png' | 'svg' = 'png'): string | undefined {
      if (instance === undefined) {
        return undefined
      }
      return instance.getDataURL({ type, pixelRatio: 2 })
    }

    /**
     * 注册事件。
     *
     * @param event 事件名。
     * @param handler 处理器。
     */
    override on(event: string, handler: (params: unknown) => void): void {
      handlers.set(event, handler)
      instance?.on(event, handler)
    }

    /** 全量解绑。 */
    override offAll(): void {
      for (const event of handlers.keys()) {
        instance?.off(event)
      }
      handlers.clear()
    }

    /** 销毁（幂等）。 */
    override dispose(): void {
      observer?.disconnect()
      observer = undefined
      instance?.dispose()
      instance = undefined
      pendingOption = undefined
    }
  }

  return new EchartsChartEngine()
}

/** 地图地理数据加载器（按需分包；新增地区在此登记）。 */
const MAP_LOADERS: Record<string, () => Promise<{ default: unknown }>> = {
  china: () => import('../assets/maps/china'),
}

/**
 * 懒加载并注册地图地理数据。
 *
 * @param name 地图名。
 * @returns 是否成功（未登记 / 加载失败返回 `false`）。
 */
export async function loadChartMap(name: string): Promise<boolean> {
  const loader = MAP_LOADERS[name]
  if (loader === undefined) {
    return false
  }
  try {
    const core = await loadCore()
    const module = await loader()
    core.registerMap(name, module.default)
    return true
  } catch {
    return false
  }
}
