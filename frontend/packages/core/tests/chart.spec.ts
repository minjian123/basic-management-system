// kiwi_id: 775
/** 图表组件基类用例（07-6）：契约套件 + 能力身份与依赖 + 占位门控 + 引擎调用 + 四态与释放。 */

import { describe, expect, it } from 'vitest'

import {
  BaseChart,
  CHART_CONFIG_VERSION,
  normalizeChartConfig,
  validateCapabilityGraph,
  type ChartEngineAdapter,
} from '../src'
import {
  CHART_CONTRACT_CONFIG,
  CHART_CONTRACT_RESULT,
  createChartEngineStub,
  describeChartContract,
  type ChartContractConfig,
  type ChartContractTarget,
} from '../testing'

/** 具体图表基类（可实例化）。 */
class DemoChart extends BaseChart {}

/** 图表契约目标工厂（适配器接核心基类）。 */
function makeChartTarget(): ChartContractTarget {
  const chart = new DemoChart()
  chart.setConfig(normalizeChartConfig(CHART_CONTRACT_CONFIG as unknown, CHART_CONTRACT_RESULT.columns))
  return {
    get ready() {
      return chart.ready
    },
    get degraded() {
      return chart.degraded
    },
    get requestCount() {
      return chart.requestCount
    },
    get state() {
      return chart.state
    },
    get view() {
      return chart.view
    },
    option: () => chart.option,
    themeName: () => chart.theme?.name,
    setReady: (value) => chart.setReady(value),
    setTokens: (reader) => chart.setTokens(reader),
    setPrefersDark: (value) => chart.setPrefersDark(value),
    setJobs: (jobs) => {
      chart.setJobs({ load: jobs.load })
    },
    setConfig: (config) => chart.setConfig(normalizeChartConfig(config as unknown, CHART_CONTRACT_RESULT.columns)),
    setChartType: (kind) => chart.setChartType(kind as Parameters<DemoChart['setChartType']>[0]),
    setMapping: (mapping) => chart.setMapping(mapping),
    setView: (view) => chart.setView(view as Parameters<DemoChart['setView']>[0]),
    setThemeMode: (mode) => chart.setThemeMode(mode as Parameters<DemoChart['setThemeMode']>[0]),
    setRenderMode: (mode) => chart.setRenderMode(mode as Parameters<DemoChart['setRenderMode']>[0]),
    setHeight: (height) => chart.setHeight(height),
    setEngine: (engine) => chart.setEngine(engine as ChartEngineAdapter | undefined),
    setResult: (result) => chart.setResult(result),
    load: (input) => chart.load(input),
    refresh: () => chart.refresh(),
    resize: (nowMs) => chart.resize(nowMs),
    exportImage: (type) => chart.exportImage(type as 'png' | undefined),
    dispose: () => chart.dispose(),
  }
}

describeChartContract('图表契约（BaseChart 适配）', makeChartTarget)

describe('能力身份与依赖', () => {
  it('能力键为 chart，依赖登记无环且已登记', () => {
    const chart = new DemoChart()
    expect(chart.identifier).toBe('chart')
    expect(chart.depends).toEqual(['data-state'])
    const problems = validateCapabilityGraph().filter((problem) => problem.key === 'chart' || problem.detail.includes('chart'))
    expect(problems).toEqual([])
  })

  it('默认配置为折线且版本确定', () => {
    const chart = new DemoChart()
    expect(chart.config.chartType).toBe('line')
    expect(chart.config.version).toBe(CHART_CONFIG_VERSION)
    expect(chart.view).toBe('chart')
    expect(chart.themeMode).toBe('auto')
  })
})

describe('占位与就绪门控', () => {
  it('未就绪时取数零请求且不写引擎', async () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setEngine(stub.engine as ChartEngineAdapter)
    await chart.load({ datasetId: 'd1' })
    expect(chart.requestCount).toBe(0)
    expect(stub.calls).toEqual([])
  })

  it('未就绪时导出返回 undefined', () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setEngine(stub.engine as ChartEngineAdapter)
    expect(chart.exportImage()).toBeUndefined()
  })
})

describe('四态与引擎', () => {
  it('空数据结算 empty 且不初始化实例', () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setConfig(normalizeChartConfig(CHART_CONTRACT_CONFIG as unknown, CHART_CONTRACT_RESULT.columns))
    chart.setReady(true)
    chart.setEngine(stub.engine as ChartEngineAdapter)
    chart.setResult({ columns: CHART_CONTRACT_RESULT.columns, rows: [] })
    expect(chart.state).toBe('empty')
    expect(stub.calls).toEqual([])
  })

  it('取数成功置 ready 并写入引擎', async () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setConfig(normalizeChartConfig(CHART_CONTRACT_CONFIG as unknown, CHART_CONTRACT_RESULT.columns))
    chart.setReady(true)
    chart.setEngine(stub.engine as ChartEngineAdapter)
    chart.setJobs({ load: async () => CHART_CONTRACT_RESULT })
    const result = await chart.load({ datasetId: 'd1' })
    expect(result).toEqual(CHART_CONTRACT_RESULT)
    expect(chart.state).toBe('ready')
    expect(chart.requestCount).toBe(1)
    expect(stub.calls).toContain('init')
  })

  it('取数失败置 error 并可重试', async () => {
    const chart = new DemoChart()
    chart.setConfig(normalizeChartConfig(CHART_CONTRACT_CONFIG as unknown, CHART_CONTRACT_RESULT.columns))
    chart.setReady(true)
    chart.setJobs({
      load: async () => {
        throw new Error('90003')
      },
    })
    await chart.load({ datasetId: 'd1' })
    expect(chart.state).toBe('error')
    expect(chart.errorMessage).toBe('90003')
  })

  it('数据表类型不初始化图表引擎', () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setConfig(normalizeChartConfig({ chartType: 'table', mapping: { metrics: [] } }))
    chart.setReady(true)
    chart.setEngine(stub.engine as ChartEngineAdapter)
    chart.setResult(CHART_CONTRACT_RESULT)
    expect(chart.option).toBeUndefined()
    expect(stub.calls).toEqual([])
  })

  it('销毁释放引擎', () => {
    const chart = new DemoChart()
    const stub = createChartEngineStub()
    chart.setConfig(normalizeChartConfig(CHART_CONTRACT_CONFIG as unknown, CHART_CONTRACT_RESULT.columns))
    chart.setReady(true)
    chart.setEngine(stub.engine as ChartEngineAdapter)
    chart.setResult(CHART_CONTRACT_RESULT)
    chart.dispose()
    expect(stub.calls).toContain('dispose')
  })

  it('视图与主题模式设置', () => {
    const chart = new DemoChart()
    chart.setView('table')
    expect(chart.view).toBe('table')
    chart.setThemeMode('dark')
    chart.setPrefersDark(true)
    expect(chart.theme?.mode).toBe('dark')
  })
})

describe('契约配置类型导出', () => {
  it('契约配置可被核心归一', () => {
    const config: ChartContractConfig = CHART_CONTRACT_CONFIG
    expect(normalizeChartConfig(config as unknown, CHART_CONTRACT_RESULT.columns).mapping.dimension).toBe('month')
  })
})
