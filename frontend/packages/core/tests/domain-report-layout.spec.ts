// kiwi_id: 776
/** 报表布局领域纯函数用例（08-9-1）：图表项 / 网格布局 / 序列化 / 校验 / 脏比对。 */

import { describe, expect, it } from 'vitest'

import {
  addChartItem,
  buildItemConfig,
  centerChartItem,
  collectUsedDatasets,
  countCharts,
  datasetOptions,
  duplicateChartItem,
  fieldsOf,
  findChartItem,
  hasOverlap,
  isReportDirty,
  moveChartItem,
  nextChartId,
  normalizeCell,
  normalizeChartItem,
  normalizeReportCharts,
  removeChartItem,
  reportChartsEqual,
  resizeChartItem,
  resolveChartTitle,
  serializeChartConfigs,
  serializeReport,
  serializeReportLayout,
  updateChartItem,
  validateReport,
  type ReportChartItem,
  type ReportDataset,
} from '../src'

/** 数据集。 */
const datasets: ReportDataset[] = [
  {
    id: 'd1',
    code: 'sales',
    name: '销售',
    status: 'enabled',
    fields: [
      { name: 'month', type: 'text' },
      { name: 'receipt', type: 'number' },
    ],
  },
  { id: 'd2', code: 'stopped', name: '停用', status: 'disabled', fields: [{ name: 'region', type: 'text' }] },
]

/** 图表项。 */
const charts: ReportChartItem[] = [
  { id: 'chart-1', datasetId: 'd1', chartType: 'bar', title: '销售趋势', layout: { x: 0, y: 0, w: 6, h: 4 } },
]

describe('尺寸与图表项归一', () => {
  it('尺寸夹取到 min/max', () => {
    expect(normalizeCell({ w: 99, h: 99 })).toEqual({ w: 12, h: 12 })
    expect(normalizeCell({ w: 1, h: 1 })).toEqual({ w: 2, h: 2 })
    expect(normalizeCell(undefined)).toEqual({ w: 6, h: 4 })
  })

  it('图表项归一：未知类型回落 line、脏字段不抛错、无标识丢弃', () => {
    const item = normalizeChartItem({ id: 'c1', datasetId: 'd1', chartType: 'unknown', layout: { x: 3, y: 2, w: 6, h: 4 } })
    expect(item?.chartType).toBe('line')
    expect(item?.layout).toEqual({ x: 3, y: 2, w: 6, h: 4 })
    expect(normalizeChartItem({ datasetId: 'd1' })).toBeUndefined()
    expect(normalizeReportCharts([{ id: 'a', datasetId: 'd1' }, { datasetId: 'd1' }])).toHaveLength(1)
  })

  it('标识递增不冲突', () => {
    expect(nextChartId([])).toBe('chart-1')
    expect(nextChartId([{ id: 'chart-1', datasetId: 'd1', chartType: 'bar', layout: { x: 0, y: 0, w: 6, h: 4 } }])).toBe(
      'chart-2',
    )
  })
})

describe('结构操作', () => {
  it('新增自动落位且不可变', () => {
    const next = addChartItem(charts, { datasetId: 'd1', chartType: 'pie' })
    expect(next).toHaveLength(2)
    expect(charts).toHaveLength(1)
    expect(next[1].layout.w).toBe(6)
  })

  it('移除幂等', () => {
    expect(removeChartItem(charts, 'chart-1')).toHaveLength(0)
    expect(removeChartItem(charts, 'ghost')).toHaveLength(1)
  })

  it('移动 / 缩放夹取到网格内', () => {
    const moved = moveChartItem(charts, 'chart-1', 99, 3)
    expect(moved[0].layout).toEqual({ x: 6, y: 3, w: 6, h: 4 })
    const resized = resizeChartItem(charts, 'chart-1', 99, 1)
    expect(resized[0].layout).toEqual({ x: 0, y: 0, w: 12, h: 2 })
  })

  it('居中与更新', () => {
    expect(centerChartItem(charts, 'chart-1')[0].layout.x).toBe(3)
    const updated = updateChartItem(charts, 'chart-1', { title: '改名', chartType: 'line' })
    expect(updated[0].title).toBe('改名')
    expect(updated[0].chartType).toBe('line')
  })

  it('复制生成新项与副本标题', () => {
    const next = duplicateChartItem(charts, 'chart-1')
    expect(next).toHaveLength(2)
    expect(next[1].id).not.toBe('chart-1')
    expect(next[1].title).toContain('副本')
  })

  it('重叠检测与选中查找', () => {
    const overlapped = addChartItem(charts, { datasetId: 'd1', chartType: 'bar' })
    const first = findChartItem(charts, 'chart-1')
    expect(first).toBeDefined()
    expect(hasOverlap(overlapped, overlapped[1].id)).toBe(false)
    expect(countCharts(charts)).toBe(1)
    expect(collectUsedDatasets([...charts, { ...charts[0], id: 'x' }])).toEqual(['d1'])
  })
})

describe('字段与选项', () => {
  it('字段清单与停用数据集选项', () => {
    expect(fieldsOf(datasets, 'd1')).toHaveLength(2)
    expect(fieldsOf(datasets, 'ghost')).toEqual([])
    expect(datasetOptions(datasets)[1]).toMatchObject({ value: 'd2', disabled: true })
  })

  it('配置生成与标题解析', () => {
    const config = buildItemConfig(charts[0], fieldsOf(datasets, 'd1'))
    expect(config.chartType).toBe('bar')
    expect(config.mapping.metrics).toEqual(['receipt'])
    expect(resolveChartTitle(charts[0])).toBe('销售趋势')
    expect(resolveChartTitle({ ...charts[0], title: undefined })).toBe('图表 chart-1')
  })
})

describe('校验与序列化', () => {
  it('空报表 / 不存在 / 停用 / 缺映射 / 重叠', () => {
    expect(validateReport([], datasets).errors[0].kind).toBe('empty')
    expect(validateReport([{ ...charts[0], datasetId: 'ghost' }], datasets).errors.some((issue) => issue.kind === 'unknown-dataset')).toBe(true)
    expect(validateReport([{ ...charts[0], datasetId: 'd2' }], datasets).errors.some((issue) => issue.kind === 'disabled-dataset')).toBe(true)
    const missing = [{ ...charts[0], config: { mapping: { metrics: [] } } as Record<string, unknown> }]
    expect(validateReport(missing, datasets).errors.some((issue) => issue.kind === 'missing-mapping')).toBe(true)
    expect(validateReport(charts, datasets).valid).toBe(true)
  })

  it('序列化结构稳定，脏比对键序无关', () => {
    const layout = serializeReportLayout(charts)
    expect(layout.columns).toBe(12)
    expect((layout.items as unknown[])[0]).toMatchObject({ id: 'chart-1' })
    expect((serializeChartConfigs(charts).items as unknown[])[0]).toMatchObject({ datasetId: 'd1' })
    expect(typeof serializeReport('r1', '报一', charts)).toBe('string')
    expect(reportChartsEqual(charts, [{ ...charts[0], config: {} }])).toBe(false)
    expect(isReportDirty(charts, chunksClone())).toBe(false)
    expect(isReportDirty(charts, undefined)).toBe(false)
    expect(isReportDirty(addChartItem(charts, { datasetId: 'd1' }), charts)).toBe(true)
  })
})

/** 图表项深拷贝（键序不同但等价）。 */
function chunksClone(): ReportChartItem[] {
  return charts.map((item) => ({ id: item.id, datasetId: item.datasetId, chartType: item.chartType, title: item.title, layout: { ...item.layout } }))
}
