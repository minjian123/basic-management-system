/** 图表引擎注册表与内建实现登记（ECharts 经工厂动态装载，独立分包；第三方库单一落点）。 */

import { ChartEngineProvider, ChartEngineRegistry, type ChartEngineOptions, type BaseChartEngine } from '@bms/core'

/** 图表引擎注册表（默认实例；宿主可登记定制实现或覆盖内建键）。 */
export const chartEngineRegistry = new ChartEngineRegistry()

/**
 * 登记图表引擎实现。
 *
 * @param key 引擎键。
 * @param create 引擎工厂。
 */
export function registerChartEngine(
  key: string,
  create: (options: ChartEngineOptions) => BaseChartEngine | Promise<BaseChartEngine>,
): void {
  chartEngineRegistry.register(new ChartEngineProvider(key, create))
}

registerChartEngine('echarts', async (options) => {
  const { createEchartsEngine } = await import('./echartsKernel')
  return createEchartsEngine({
    container: options.container as () => HTMLElement | undefined,
    renderMode: options.renderMode,
    theme: options.theme,
  })
})
