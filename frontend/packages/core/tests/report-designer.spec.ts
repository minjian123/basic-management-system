// kiwi_id: 776
/** 报表设计器能力基类用例（08-9-1）：契约套件 + 能力身份与依赖 + 数据集选择 + 拖拽广播 + 保存发布另存。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseReportDesigner,
  REPORT_DESIGN_PERM,
  validateCapabilityGraph,
  type ReportBlockAction,
  type ReportJobs,
} from '../src'
import {
  createReportJobs,
  describeReportDesignerContract,
  REPORT_CONTRACT_CHARTS,
  REPORT_CONTRACT_DATASETS,
  type ReportDesignerContractTarget,
} from '../testing'

/** 具体报表设计器（可实例化）。 */
class DemoDesigner extends BaseReportDesigner {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 构造持设计权限的权限上下文。 */
function granted(): DemoAccess {
  const access = new DemoAccess()
  access.setCodes([REPORT_DESIGN_PERM])
  return access
}

/** 契约目标工厂（适配器接核心基类）。 */
function makeTarget(): ReportDesignerContractTarget {
  const designer = new DemoDesigner()
  designer.setDatasets(REPORT_CONTRACT_DATASETS)
  designer.setReportCode('sales_report', '销售月报')
  designer.charts = REPORT_CONTRACT_CHARTS.map((item) => ({ ...item, layout: { ...item.layout } }))
  designer.setAccess(granted())
  designer.markBaseline()
  designer.setReady(true)
  return {
    get ready() {
      return designer.ready
    },
    get degraded() {
      return designer.degraded
    },
    get readonly() {
      return designer.readonly
    },
    get busy() {
      return designer.busy
    },
    get dirty() {
      return designer.dirty
    },
    get phase() {
      return designer.phase
    },
    get requestCount() {
      return designer.requestCount
    },
    charts: () => designer.charts,
    selectedId: () => designer.selectedId,
    validation: () => designer.validation,
    setReady: (value) => designer.setReady(value),
    setOperators: (input) => {
      if (input.codes === undefined) {
        designer.setAccess(undefined)
        return
      }
      const access = new DemoAccess()
      access.setCodes(input.codes)
      designer.setAccess(access)
    },
    setJobs: (jobs) => designer.setJobs(jobs as ReportJobs),
    setDatasets: (datasets) => designer.setDatasets(datasets),
    setReportCode: (code, name) => designer.setReportCode(code, name),
    selectDataset: (datasetId) => designer.selectDataset(datasetId),
    addChart: (input) => designer.addChart(input),
    removeChart: (id) => designer.removeChart(id),
    duplicateChart: (id) => designer.duplicateChart(id),
    moveChart: (id, x, y) => designer.moveChart(id, x, y),
    resizeChart: (id, w, h) => designer.resizeChart(id, w, h),
    centerChart: (id) => designer.centerChart(id),
    selectChart: (id) => designer.selectChart(id),
    updateChart: (id, patch) => designer.updateChart(id, patch),
    markBaseline: () => designer.markBaseline(),
    discard: () => designer.discard(),
    needsBlock: (action) => designer.needsBlock(action as ReportBlockAction),
    load: (input) => designer.load(input),
    preview: (chartId, params) => designer.preview(chartId, params),
    save: () => designer.save(),
    publish: () => designer.publish(),
    saveAs: (code, name) => designer.saveAs(code, name),
  }
}

describeReportDesignerContract('报表设计器编排契约（BaseReportDesigner）', makeTarget)

describe('能力身份与依赖', () => {
  it('能力键与依赖登记无环', () => {
    const designer = new DemoDesigner()
    expect(designer.identifier).toBe('report-designer')
    expect(designer.depends).toEqual(['access', 'notice', 'data-state', 'drag-drop', 'async-task'])
    const problems = validateCapabilityGraph().filter((problem) => problem.key === 'report-designer' || problem.detail.includes('report-designer'))
    expect(problems).toEqual([])
  })
})

describe('数据集选择与切换', () => {
  it('停用 / 不存在数据集不可选；切换报表清空编辑态', () => {
    const designer = new DemoDesigner()
    designer.setDatasets(REPORT_CONTRACT_DATASETS)
    designer.setAccess(granted())
    designer.setReady(true)

    expect(designer.selectDataset('d1')).toBe(true)
    expect(designer.datasetId).toBe('d1')
    expect(designer.selectDataset('d2')).toBe(false)
    expect(designer.selectDataset('ghost')).toBe(false)

    designer.charts = [{ ...REPORT_CONTRACT_CHARTS[0] }]
    designer.setReportCode('other', '别的')
    expect(designer.reportCode).toBe('other')
    expect(designer.charts).toHaveLength(0)
    expect(designer.selectedId).toBe('')
  })

  it('setDatasets 使失效的当前数据集重置', () => {
    const designer = new DemoDesigner()
    designer.setDatasets(REPORT_CONTRACT_DATASETS)
    designer.selectDataset('d1')
    designer.setDatasets([REPORT_CONTRACT_DATASETS[1]])
    expect(designer.datasetId).toBe('')
  })
})

describe('拖拽广播与保存发布', () => {
  it('拖拽能力未注入仍完成落点', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.charts = [{ ...REPORT_CONTRACT_CHARTS[0], layout: { ...REPORT_CONTRACT_CHARTS[0].layout } }]
    expect(designer.moveChart('chart-1', 3, 2)).toBe(true)
    expect(designer.charts[0].layout.x).toBe(3)
  })

  it('发布依赖保存成功（件层先保存）；另存为不改当前编码', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setDatasets(REPORT_CONTRACT_DATASETS)
    designer.setReportCode('sales_report', '销售月报')
    designer.charts = [{ ...REPORT_CONTRACT_CHARTS[0], layout: { ...REPORT_CONTRACT_CHARTS[0].layout } }]
    designer.markBaseline()
    const jobs = createReportJobs()
    designer.setJobs(jobs)

    expect(await designer.save()).toEqual({ recordVersion: 3 })
    expect(await designer.publish()).toBe(true)
    await designer.saveAs('copy_report', '副本')
    expect(designer.reportCode).toBe('sales_report')
    expect(jobs.calls).toContain('publish')
    expect(jobs.calls).toContain('saveAs')
  })

  it('保存失败保留脏标记', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setDatasets(REPORT_CONTRACT_DATASETS)
    designer.charts = [{ ...REPORT_CONTRACT_CHARTS[0], layout: { ...REPORT_CONTRACT_CHARTS[0].layout } }]
    designer.markBaseline()
    designer.setJobs(
      createReportJobs(async () => {
        throw new Error('network')
      }),
    )
    designer.addChart({ datasetId: 'd1', chartType: 'bar' })
    expect(designer.dirty).toBe(true)
    expect(await designer.save()).toBeUndefined()
    expect(designer.dirty).toBe(true)
    expect(designer.errorMessage).toBe('network')
  })

  it('needsBlock 与 discard', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setDatasets(REPORT_CONTRACT_DATASETS)
    designer.charts = [{ ...REPORT_CONTRACT_CHARTS[0], layout: { ...REPORT_CONTRACT_CHARTS[0].layout } }]
    designer.markBaseline()
    expect(designer.needsBlock('leave')).toBe(false)
    designer.addChart({ datasetId: 'd1', chartType: 'bar' })
    expect(designer.needsBlock('open')).toBe(true)
    expect(designer.discard()).toBe(true)
    expect(designer.needsBlock('new')).toBe(false)
  })
})
