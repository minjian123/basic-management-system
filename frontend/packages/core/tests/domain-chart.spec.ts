// kiwi_id: 775
/** 图表领域纯函数用例（07-6）：类型集 / 映射归一 / 令牌主题 / 选项生成 / 合并策略 / 节流 / 脏比对。 */

import { describe, expect, it } from 'vitest'

import {
  buildChartOption,
  buildChartTheme,
  chartConfigEqual,
  chartKindOption,
  CHART_COLOR_TOKENS,
  CHART_CONFIG_VERSION,
  CHART_EMPTY_TEXT,
  CHART_KINDS,
  deepMerge,
  defaultMapping,
  hasChartAxis,
  isChartEmpty,
  isMappingEmpty,
  isNumericField,
  mergeChartOption,
  normalizeChartConfig,
  normalizeChartKind,
  normalizeMapping,
  resolveChartMode,
  rotatePalette,
  serializeChartConfig,
  shouldReplaceOption,
  shouldResize,
  toNumber,
  type ChartConfig,
  type ChartDatasetResult,
} from '../src'

/** 契约字段（文本维度 + 数值度量）。 */
const FIELDS = [
  { name: 'month', type: 'text' },
  { name: 'receipt', type: 'number' },
  { name: 'payment', type: 'number' },
]

/** 契约数据。 */
const RESULT: ChartDatasetResult = {
  columns: FIELDS,
  rows: [
    { month: '1月', receipt: 12000, payment: 8000 },
    { month: '2月', receipt: 18000, payment: 9000 },
  ],
}

/** 契约配置。 */
const CONFIG: ChartConfig = {
  version: CHART_CONFIG_VERSION,
  chartType: 'bar',
  title: '销售趋势',
  mapping: { dimension: 'month', metrics: ['receipt', 'payment'] },
  style: { legend: true, smooth: false, stacked: false, label: false, paletteIndex: 0 },
}

/** 令牌读取器（固定值）。 */
function tokens(name: string): string | undefined {
  if (name === CHART_COLOR_TOKENS[0]) {
    return '#111111'
  }
  if (name === CHART_COLOR_TOKENS[1]) {
    return '#222222'
  }
  return undefined
}

describe('图表类型集', () => {
  it('类型集覆盖 13 类且含数据表与地图', () => {
    expect(CHART_KINDS).toHaveLength(13)
    const kinds = CHART_KINDS.map((item) => item.kind)
    expect(kinds).toContain('table')
    expect(kinds).toContain('map')
    expect(kinds).toContain('stacked_bar')
  })

  it('未知类型回落 line', () => {
    expect(normalizeChartKind('unknown')).toBe('line')
    expect(normalizeChartKind('pie')).toBe('pie')
    expect(chartKindOption('pie').hasAxis).toBe(false)
    expect(hasChartAxis('bar')).toBe(true)
  })

  it('数值字段判定', () => {
    expect(isNumericField('number')).toBe(true)
    expect(isNumericField('decimal')).toBe(true)
    expect(isNumericField('text')).toBe(false)
  })
})

describe('数据映射归一', () => {
  it('默认映射取首个文本维度与全部数值度量', () => {
    expect(defaultMapping(FIELDS)).toEqual({ dimension: 'month', metrics: ['receipt', 'payment'] })
  })

  it('剔除字段清单外的脏引用并去重度量', () => {
    const mapping = normalizeMapping({ dimension: 'ghost', metrics: ['receipt', 'receipt', 'nope'] }, FIELDS)
    expect(mapping.dimension).toBeUndefined()
    expect(mapping.metrics).toEqual(['receipt'])
  })

  it('空映射回落默认映射', () => {
    expect(normalizeMapping(undefined, FIELDS)).toEqual({ dimension: 'month', metrics: ['receipt', 'payment'] })
    expect(isMappingEmpty({ metrics: [] })).toBe(true)
    expect(isMappingEmpty({ dimension: 'month', metrics: [] })).toBe(false)
  })
})

describe('图表配置归一', () => {
  it('缺省项补确定值', () => {
    const config = normalizeChartConfig({ chartType: 'pie' }, FIELDS)
    expect(config.version).toBe(CHART_CONFIG_VERSION)
    expect(config.chartType).toBe('pie')
    expect(config.style).toMatchObject({ legend: true, smooth: false, stacked: false, label: false, paletteIndex: 0 })
    expect(config.override).toBeUndefined()
  })

  it('色板序号夹取到 [0, 7]', () => {
    expect(normalizeChartConfig({ chartType: 'bar', style: { paletteIndex: 99 } }, FIELDS).style?.paletteIndex).toBe(7)
    expect(normalizeChartConfig({ chartType: 'bar', style: { paletteIndex: -5 } }, FIELDS).style?.paletteIndex).toBe(0)
  })
})

describe('图表主题', () => {
  it('按令牌读取口取色，缺省回落兜底', () => {
    const theme = buildChartTheme(tokens, 'light')
    expect(theme.name).toBe('bms-light')
    expect(theme.color[0]).toBe('#111111')
    expect(theme.color[1]).toBe('#222222')
    expect(theme.color[2]).toBeTruthy()
  })

  it('主题模式解析', () => {
    expect(resolveChartMode('auto', true)).toBe('dark')
    expect(resolveChartMode('auto', false)).toBe('light')
    expect(resolveChartMode('dark', false)).toBe('dark')
  })
})

describe('空数据判定', () => {
  it('无结果 / 空行 / 全非数值判空；table 与有效数值判非空', () => {
    const config = normalizeChartConfig(CONFIG, FIELDS)
    expect(isChartEmpty(undefined, config)).toBe(true)
    expect(isChartEmpty({ columns: FIELDS, rows: [] }, config)).toBe(true)
    expect(isChartEmpty({ columns: FIELDS, rows: [{ month: '1月', receipt: 'x', payment: null }] }, config)).toBe(true)
    expect(isChartEmpty(RESULT, config)).toBe(false)
    expect(isChartEmpty({ columns: FIELDS, rows: [{ month: '1月' }] }, normalizeChartConfig({ chartType: 'table' }, FIELDS))).toBe(false)
  })

  it('数值转换', () => {
    expect(toNumber('12')).toBe(12)
    expect(toNumber('')).toBeUndefined()
    expect(toNumber(Number.NaN)).toBeUndefined()
    expect(toNumber(null)).toBeUndefined()
  })
})

describe('选项生成', () => {
  it('柱状图含坐标轴与多度量系列', () => {
    const option = buildChartOption(normalizeChartConfig(CONFIG, FIELDS), RESULT, buildChartTheme(tokens, 'light'))
    expect(option.title).toMatchObject({ text: '销售趋势' })
    expect(Array.isArray(option.series)).toBe(true)
    expect((option.series as unknown[]).length).toBe(2)
    expect(JSON.stringify(option)).toContain('1月')
  })

  it('饼图无坐标轴且单系列含百分比标签', () => {
    const config = normalizeChartConfig({ chartType: 'pie', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS)
    const option = buildChartOption(config, RESULT, buildChartTheme(tokens, 'light'))
    expect(option.xAxis).toBeUndefined()
    expect((option.series as { type: string }[])[0].type).toBe('pie')
  })

  it('地图 / 仪表盘 / 雷达 / 散点各按其类型生成', () => {
    const theme = buildChartTheme(tokens, 'light')
    const map = buildChartOption(normalizeChartConfig({ chartType: 'map', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS), RESULT, theme)
    expect((map.series as { type: string }[])[0].type).toBe('map')
    const gauge = buildChartOption(normalizeChartConfig({ chartType: 'gauge', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS), RESULT, theme)
    expect((gauge.series as { type: string }[])[0].type).toBe('gauge')
    const radar = buildChartOption(normalizeChartConfig({ chartType: 'radar', mapping: { dimension: 'month', metrics: ['receipt', 'payment'] } }, FIELDS), RESULT, theme)
    expect((radar.series as { type: string }[])[0].type).toBe('radar')
    const scatter = buildChartOption(normalizeChartConfig({ chartType: 'scatter', mapping: { metrics: ['receipt', 'payment'] } }, FIELDS), RESULT, theme)
    expect((scatter.series as { type: string }[])[0].type).toBe('scatter')
  })

  it('高级配置覆盖生成结果', () => {
    const config = normalizeChartConfig({ chartType: 'bar', mapping: { dimension: 'month', metrics: ['receipt'] }, override: { yAxis: { name: '金额' } } }, FIELDS)
    const option = buildChartOption(config, RESULT, buildChartTheme(tokens, 'light'))
    expect((option.yAxis as { name: string }).name).toBe('金额')
  })

  it('数据表类型返回空选项', () => {
    const option = buildChartOption(normalizeChartConfig({ chartType: 'table' }, FIELDS), RESULT, buildChartTheme(tokens, 'light'))
    expect(option).toEqual({})
  })
})

describe('合并策略与节流', () => {
  it('类型或映射变化触发全量替换', () => {
    const base = normalizeChartConfig({ chartType: 'bar', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS)
    const same = normalizeChartConfig({ chartType: 'bar', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS)
    const changed = normalizeChartConfig({ chartType: 'pie', mapping: { dimension: 'month', metrics: ['receipt'] } }, FIELDS)
    expect(shouldReplaceOption(base, same)).toBe(false)
    expect(shouldReplaceOption(base, changed)).toBe(true)
    expect(shouldReplaceOption(undefined, base)).toBe(true)
  })

  it('深合并与全量替换', () => {
    expect(mergeChartOption({ a: { b: 1 } }, { a: { c: 2 } }, false)).toEqual({ a: { b: 1, c: 2 } })
    expect(mergeChartOption({ a: 1 }, { b: 2 }, true)).toEqual({ b: 2 })
    expect(deepMerge({ a: 1, b: 2 }, { b: undefined, c: 3 })).toEqual({ a: 1, b: 2, c: 3 })
  })

  it('尺寸节流按间隔放行', () => {
    expect(shouldResize(0, 149)).toBe(false)
    expect(shouldResize(0, 150)).toBe(true)
  })

  it('配置等价（键序无关）', () => {
    const config = normalizeChartConfig(CONFIG, FIELDS)
    expect(chartConfigEqual(config, { ...config })).toBe(true)
    expect(chartConfigEqual(config, undefined)).toBe(false)
    expect(serializeChartConfig(config)).toBe(serializeChartConfig({ ...config }))
  })

  it('色板旋转', () => {
    expect(rotatePalette(['a', 'b', 'c'], 1)).toEqual(['b', 'c', 'a'])
    expect(rotatePalette(['a', 'b', 'c'], 3)).toEqual(['a', 'b', 'c'])
    expect(rotatePalette([], 1)).toEqual([])
  })

  it('空数据文案', () => {
    expect(CHART_EMPTY_TEXT).toBe('暂无数据')
  })
})
