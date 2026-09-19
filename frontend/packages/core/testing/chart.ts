/**
 * 图表契约（`@bms/core/testing`）。
 *
 * 图表卡 / 报表设计器 / 大屏 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、就绪门控、四态结算、引擎调用语义（初始化 / 更新 / 主题重建 / 尺寸 / 导出 / 销毁）。
 */

import { describe, expect, it } from 'vitest'

/** 图表主题（结构化最小面）。 */
export interface ChartContractTheme {
  /** 主题名。 */
  name: string
  /** 亮暗。 */
  mode: string
  /** 序列色板。 */
  color: string[]
}

/** 数据集结果（结构化最小面）。 */
export interface ChartContractResult {
  /** 字段声明。 */
  columns: { name: string; type: string }[]
  /** 数据行。 */
  rows: Record<string, unknown>[]
}

/** 数据映射（结构化最小面）。 */
export interface ChartContractMapping {
  /** 维度字段。 */
  dimension?: string
  /** 度量字段。 */
  metrics: string[]
  /** 系列字段。 */
  series?: string
}

/** 图表配置（结构化最小面）。 */
export interface ChartContractConfig {
  /** 结构版本。 */
  version?: number
  /** 图表类型。 */
  chartType: string
  /** 标题。 */
  title?: string
  /** 数据映射。 */
  mapping: ChartContractMapping
  /** 常用样式。 */
  style?: Record<string, unknown>
}

/** 引擎适配器桩（结构化最小面）。 */
export interface ChartContractEngine {
  /** 初始化。 */
  init?(payload: { theme: ChartContractTheme; renderMode: string }): void
  /** 写入选项。 */
  update?(option: Record<string, unknown>, replace: boolean): void
  /** 主题重建。 */
  applyTheme?(theme: ChartContractTheme, option: Record<string, unknown>): void
  /** 尺寸重算。 */
  resize?(): void
  /** 导出图片。 */
  exportImage?(type: 'png' | 'svg'): string | undefined
  /** 销毁。 */
  dispose?(): void
}

/** 取数处理函数（结构化最小面）。 */
export interface ChartContractJobs {
  /** 取数。 */
  load?: (input: { datasetId: string; params?: Record<string, unknown> }) => Promise<ChartContractResult | undefined>
}

/** 图表契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface ChartContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 数据状态。 */
  readonly state: string
  /** 视图。 */
  readonly view: string
  /** 生成后的选项。 */
  option(): Record<string, unknown> | undefined
  /** 当前主题名。 */
  themeName(): string | undefined
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入令牌读取口。 */
  setTokens(reader: (name: string) => string | undefined): void
  /** 设置深色偏好。 */
  setPrefersDark(value: boolean): void
  /** 注入取数处理函数。 */
  setJobs(jobs: ChartContractJobs): void
  /** 设置配置。 */
  setConfig(config: ChartContractConfig): void
  /** 切换类型。 */
  setChartType(kind: string): void
  /** 设置映射。 */
  setMapping(mapping: ChartContractMapping): void
  /** 设置视图。 */
  setView(view: string): void
  /** 设置主题模式。 */
  setThemeMode(mode: string): void
  /** 设置渲染模式。 */
  setRenderMode(mode: string): void
  /** 设置高度。 */
  setHeight(height: number): void
  /** 注入引擎。 */
  setEngine(engine: ChartContractEngine | undefined): void
  /** 写入数据集结果。 */
  setResult(result: ChartContractResult | undefined): void
  /** 取数。 */
  load(input: { datasetId: string; params?: Record<string, unknown> }): Promise<ChartContractResult | undefined>
  /** 刷新。 */
  refresh(): Promise<ChartContractResult | undefined>
  /** 尺寸自适应。 */
  resize(nowMs?: number): boolean
  /** 导出图片。 */
  exportImage(type?: string): string | undefined
  /** 销毁。 */
  dispose(): void
}

/** 契约数据：类型 `bar`、维度 `month`、度量 `receipt`，两行。 */
export const CHART_CONTRACT_RESULT: ChartContractResult = {
  columns: [
    { name: 'month', type: 'text' },
    { name: 'receipt', type: 'number' },
  ],
  rows: [
    { month: '1月', receipt: 12000 },
    { month: '2月', receipt: 18000 },
  ],
}

/** 契约数据：配置。 */
export const CHART_CONTRACT_CONFIG: ChartContractConfig = {
  chartType: 'bar',
  title: '销售趋势',
  mapping: { dimension: 'month', metrics: ['receipt'] },
}

/** 引擎桩调用轨迹。 */
export interface ChartEngineStub {
  /** 调用记录。 */
  readonly calls: string[]
  /** 引擎适配器。 */
  readonly engine: ChartContractEngine
}

/**
 * 创建引擎桩（记录调用轨迹）。
 *
 * @returns 引擎桩。
 */
export function createChartEngineStub(): ChartEngineStub {
  const calls: string[] = []
  return {
    calls,
    engine: {
      init: () => calls.push('init'),
      update: (_option, replace) => calls.push(`update:${replace ? 'replace' : 'merge'}`),
      applyTheme: () => calls.push('applyTheme'),
      resize: () => calls.push('resize'),
      exportImage: () => {
        calls.push('export')
        return 'data:image/png;base64,stub'
      },
      dispose: () => calls.push('dispose'),
    },
  }
}

/**
 * 图表契约（`07_06` 冻结；真实实现 `07_07` / `08_09` 继续跑同一套件）。
 *
 * 断言：占位态降级且取数零请求；就绪后不再降级；空数据不初始化引擎；
 * 就绪且注引擎后写入选项；类型 / 映射变化全量替换；主题切换重建；尺寸节流；导出；销毁。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeChartContract(name: string, create: () => ChartContractTarget): void {
  describe(name, () => {
    it('未就绪时降级，取数零请求', async () => {
      const target = create()
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.requestCount).toBe(0)

      await target.load({ datasetId: 'd1' })
      await target.refresh()
      expect(target.requestCount).toBe(0)
    })

    it('就绪后不再降级', () => {
      const target = create()
      target.setReady(true)
      expect(target.ready).toBe(true)
      expect(target.degraded).toBe(false)
    })

    it('空数据结算为 empty 且不初始化引擎', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult({ columns: CHART_CONTRACT_RESULT.columns, rows: [] })

      expect(target.state).toBe('empty')
      expect(stub.calls).not.toContain('init')
    })

    it('就绪且注入引擎后初始化并写入选项', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult(CHART_CONTRACT_RESULT)

      expect(target.state).toBe('ready')
      expect(stub.calls).toContain('init')
      expect(stub.calls.some((call) => call.startsWith('update'))).toBe(true)
      expect(target.option()).toBeDefined()
    })

    it('类型变化触发全量替换', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult(CHART_CONTRACT_RESULT)
      target.setChartType('pie')

      expect(stub.calls[stub.calls.length - 1]).toBe('update:replace')
    })

    it('主题切换派发重建并保留色板', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult(CHART_CONTRACT_RESULT)
      target.setTokens((token) => (token === '--bms-chart-color-1' ? '#123456' : undefined))
      target.setThemeMode('dark')

      expect(stub.calls).toContain('applyTheme')
      expect(target.themeName()).toBe('bms-dark')
      const option = target.option()
      expect(JSON.stringify(option)).toContain('#123456')
    })

    it('尺寸自适应节流', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult(CHART_CONTRACT_RESULT)

      expect(target.resize(1000)).toBe(true)
      expect(target.resize(1010)).toBe(false)
      expect(target.resize(1200)).toBe(true)
      expect(stub.calls.filter((call) => call === 'resize')).toHaveLength(2)
    })

    it('导出与销毁', () => {
      const target = create()
      const stub = createChartEngineStub()
      target.setReady(true)
      target.setEngine(stub.engine)
      target.setResult(CHART_CONTRACT_RESULT)

      expect(target.exportImage('png')).toBe('data:image/png;base64,stub')
      target.dispose()
      expect(stub.calls).toContain('dispose')
    })

    it('就绪未注入处理函数零请求；注入后取数成功', async () => {
      const target = create()
      target.setReady(true)
      await target.load({ datasetId: 'd1' })
      expect(target.requestCount).toBe(0)

      target.setJobs({ load: async () => CHART_CONTRACT_RESULT })
      await target.load({ datasetId: 'd1' })
      expect(target.requestCount).toBe(1)
      expect(target.state).toBe('ready')
    })

    it('视图切换', () => {
      const target = create()
      target.setReady(true)
      target.setView('table')
      expect(target.view).toBe('table')
    })
  })
}
