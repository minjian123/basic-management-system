// kiwi_id: 766
/** 打印与导出 PDF 用例（08_03_03）：契约套件（模板 + 编排）+ 单页纸（页眉/字段/明细/汇总/签章/页脚/水印/黑白）+ 预览壳（纸张/方向/黑白/缩放/水印/多页/空态/打印/导出占位/批量/失败重试）+ 入口件（下拉、权限过滤、占位提示）。 */

import {
  BaseWatermark,
  buildPrintPages,
  resolvePaperSize,
  type PaperName,
  type PaperOrientation,
  type PrintTemplateDef,
} from '@bms/core'
import {
  describePrintContract,
  type PrintContractHandler,
  type PrintContractTarget,
  type PrintContractTemplate,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PrintButton, PrintPreview, PrintSheet, useBasePrint } from '../src'

/** 样例模板集（`order` 三列 + 每页 2 行；`label` 单列）。 */
const TEMPLATES: PrintTemplateDef[] = [
  {
    key: 'order',
    title: '销售订单',
    subtitle: 'SO-20260919-0007',
    rowsPerPage: 2,
    summaryKey: 'amount',
    summaryLabel: '合计',
    footerNote: '本单据为电子凭证',
    fields: [
      { key: 'customer', label: '客户' },
      { key: 'remark', label: '备注' },
    ],
    columns: [
      { key: 'name', label: '商品' },
      { key: 'qty', label: '数量', format: 'number' },
      { key: 'amount', label: '金额', format: 'amount' },
    ],
    signLabels: ['制单', '审核', '客户签收'],
  },
  { key: 'label', title: '标签', columns: [{ key: 'name', label: '名称' }] },
]

/** 五行明细。 */
const ROWS = [
  { name: '螺栓', qty: 200, amount: 700 },
  { name: '垫片', qty: 500, amount: 600 },
  { name: '法兰', qty: 40, amount: 2720 },
  { name: '线缆', qty: 10, amount: 120 },
  { name: '支架', qty: 8, amount: 80 },
]

/** 字段数据（`remark` 缺失）。 */
const FIELDS = { customer: '华东制造有限公司' }

/** 水印能力样例。 */
class SampleWatermark extends BaseWatermark {}

/**
 * 在独立作用域内执行（组合式投影需要活动作用域）。
 *
 * @param factory 工厂函数。
 */
function scoped<T>(factory: () => T): T {
  const scope = effectScope()
  const result = scope.run(factory)
  if (result === undefined) {
    throw new Error('effectScope 未返回结果')
  }
  return result
}

/** 打印契约目标（`useBasePrint` 投影）。 */
function printTarget(): PrintContractTarget {
  return scoped(() => {
    const watermark = new SampleWatermark()
    watermark.setUser('张三')
    watermark.setTenant('租户一')
    const api = useBasePrint({ templates: TEMPLATES, data: { fields: FIELDS, rows: ROWS }, watermark })
    return {
      get templateKey() {
        return api.templateKey.value
      },
      get paperSize() {
        return api.paperSize.value
      },
      get rowsPerPage() {
        return api.rowsPerPage.value
      },
      get pageCount() {
        return api.pages.value.length
      },
      get mono() {
        return api.mono.value
      },
      get watermarkText() {
        return api.watermarkText.value
      },
      get zoom() {
        return api.zoom.value
      },
      get previewVisible() {
        return api.previewVisible.value
      },
      get phase() {
        return api.phase.value
      },
      get batchMode() {
        return api.batchMode.value
      },
      get canExport() {
        return api.canExport.value
      },
      setTemplates: (templates: PrintContractTemplate[]) => api.setTemplates(templates),
      selectTemplate: (key: string) => api.selectTemplate(key),
      setData: (data) => api.setData(data),
      setPaper: (paper: string, orientation: string) =>
        api.setPaper(paper as PaperName, orientation as PaperOrientation),
      setTone: (tone: string) => api.setTone(tone === 'mono' ? 'mono' : 'color'),
      setWatermarkLabel: (label: string) => api.setWatermarkLabel(label),
      setZoom: (value: number) => api.setZoom(value),
      setBatchMode: (mode: string) => api.setBatchMode(mode === 'merged' ? 'merged' : 'separate'),
      setAllowExport: (value: boolean) => api.setAllowExport(value),
      setExportHandler: (handler: PrintContractHandler | undefined) => {
        api.print.jobs =
          handler === undefined
            ? {}
            : {
                exportPdf: async (_payload, report) => {
                  const result = await handler((current, total) => report({ current, total }))
                  return { ...result }
                },
              }
      },
      open: () => api.open(),
      close: () => api.close(),
      pageRows: () => api.pages.value.map((page) => page.rows.length),
      pageIndexes: () => api.pages.value.map((page) => page.index),
      fieldText: (key: string) => {
        const field = api.template.value?.fields?.find((item) => item.key === key)
        return field === undefined ? '' : api.print.fieldValue(field)
      },
      exportPdf: async () => {
        const result = await api.exportPdf()
        return result === undefined ? undefined : { fileId: result.fileId }
      },
      retry: async () => {
        const result = await api.retry()
        return result === undefined ? undefined : { fileId: result.fileId }
      },
    }
  })
}

describePrintContract('打印契约（模板 + 编排）', printTarget)

describe('PrintSheet 单页纸', () => {
  /** 页面（三页）。 */
  const pages = buildPrintPages({
    template: TEMPLATES[0] as PrintTemplateDef,
    data: { rows: ROWS },
    paperSize: resolvePaperSize('A4'),
    printedAt: '2026-09-19 10:00',
    printedBy: '张三',
  })

  it('渲染页眉、标题、字段区、明细表（每页表头重复）、汇总、签章与页脚', () => {
    const wrapper = mount(PrintSheet, {
      props: {
        template: TEMPLATES[0] as PrintTemplateDef,
        page: pages[0]!,
        fields: FIELDS,
        rows: ROWS,
        brand: { name: 'BMS 控制台', logo: 'B' },
      },
    })
    const sheet = wrapper.get('[data-test="print-sheet"]')
    expect(sheet.attributes('data-page')).toBe('1')
    expect(sheet.attributes('data-total')).toBe('3')
    expect(sheet.attributes('data-mono')).toBe('false')
    expect(wrapper.get('[data-test="print-sheet-header"]').text()).toContain('BMS 控制台')
    expect(wrapper.get('[data-test="print-sheet-subtitle"]').text()).toBe('SO-20260919-0007')
    expect(wrapper.get('[data-test="print-sheet-title"]').text()).toBe('销售订单')

    const rows = wrapper.findAll('[data-test="print-sheet-field-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0]?.findAll('[data-field]')).toHaveLength(2)
    expect(wrapper.get('[data-field="customer"]').text()).toContain('华东制造有限公司')
    expect(wrapper.get('[data-field="remark"]').text()).toContain('—')

    expect(wrapper.get('[data-test="print-sheet-table"]').findAll('thead th')).toHaveLength(3)
    expect(wrapper.findAll('[data-test="print-sheet-row"]')).toHaveLength(2)
    expect(wrapper.get('[data-test="print-sheet-summary"]').text()).toContain('4,220.00')
    expect(wrapper.get('[data-test="print-sheet-sign"]').text()).toContain('客户签收')
    expect(wrapper.get('[data-test="print-sheet-footer"]').text()).toContain('第 1 页 / 共 3 页')
    expect(wrapper.get('[data-test="print-sheet-footer"]').text()).toContain('打印人 张三')
  })

  it('末页余量与黑白置灰、水印层', () => {
    const wrapper = mount(PrintSheet, {
      props: {
        template: TEMPLATES[0] as PrintTemplateDef,
        page: pages[2]!,
        watermark: '作废 · 张三 / 租户一',
        mono: true,
      },
    })
    expect(wrapper.get('[data-test="print-sheet"]').attributes('data-mono')).toBe('true')
    expect(wrapper.findAll('[data-test="print-sheet-row"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="print-sheet-watermark"]').text()).toContain('作废')
  })

  it('无水印文案时不渲染水印层；空明细渲染占位行', () => {
    const empty = buildPrintPages({
      template: TEMPLATES[0] as PrintTemplateDef,
      paperSize: resolvePaperSize('A4'),
    })
    const wrapper = mount(PrintSheet, {
      props: { template: TEMPLATES[0] as PrintTemplateDef, page: empty[0]! },
    })
    expect(wrapper.find('[data-test="print-sheet-watermark"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="print-sheet-empty-row"]').text()).toBe('—')
  })

  it('纸张方向切换影响纸面尺寸', () => {
    const wrapper = mount(PrintSheet, {
      props: { template: TEMPLATES[0] as PrintTemplateDef, page: pages[0]!, orientation: 'landscape' as const },
    })
    expect(wrapper.get('[data-test="print-sheet"]').attributes('data-orientation')).toBe('landscape')
  })
})

describe('PrintPreview 预览壳', () => {
  let printSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    printSpy = vi.fn()
    Object.defineProperty(window, 'print', { value: printSpy, writable: true, configurable: true })
  })

  /**
   * 挂载预览壳。
   *
   * @param props 覆盖属性。
   */
  function mountPreview(props: Record<string, unknown> = {}) {
    return mount(PrintPreview, {
      props: {
        visible: true,
        templates: TEMPLATES,
        data: { fields: FIELDS, rows: ROWS },
        watermark: '作废',
        watermarkLabel: '作废',
        ...props,
      },
    })
  }

  it('受控显隐：隐藏时不渲染，打开后渲染多页纸面', async () => {
    const hidden = mountPreview({ visible: false })
    expect(hidden.find('[data-test="print-preview"]').exists()).toBe(false)

    const wrapper = mountPreview()
    expect(wrapper.findAll('[data-test="print-sheet"]')).toHaveLength(3)
    expect(
      wrapper.get('[data-test="print-preview"]').findAll('[data-test="print-sheet"]')[0]?.attributes('data-page'),
    ).toBe('1')
  })

  it('无明细数据时渲染空态', () => {
    const wrapper = mountPreview({ data: { fields: FIELDS, rows: [] } })
    expect(wrapper.find('[data-test="print-preview-empty"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="print-sheet"]')).toHaveLength(0)
  })

  it('工具栏：纸张 / 方向 / 黑白 / 缩放上抛受控事件', async () => {
    const wrapper = mountPreview()
    await wrapper.get('[data-test="print-preview-paper-A5"]').trigger('click')
    expect(wrapper.emitted('update:paper')?.[0]).toEqual(['A5'])

    await wrapper.get('[data-test="print-preview-orientation"]').trigger('click')
    expect(wrapper.emitted('update:orientation')?.[0]).toEqual(['landscape'])

    await wrapper.get('[data-test="print-preview-tone"]').trigger('click')
    expect(wrapper.emitted('update:tone')?.[0]).toEqual(['mono'])
    expect(wrapper.get('[data-test="print-preview-tone"]').text()).toBe('黑白')

    await wrapper.get('[data-test="print-preview-zoom-in"]').trigger('click')
    expect(wrapper.emitted('update:zoom')?.[0]).toEqual([1.1])
    expect(wrapper.get('[data-test="print-preview-zoom"]').text()).toBe('110%')
  })

  it('浏览器打印：上抛事件并调起 window.print', async () => {
    const wrapper = mountPreview()
    await wrapper.get('[data-test="print-preview-print"]').trigger('click')
    expect(wrapper.emitted('print')).toHaveLength(1)
    expect(printSpy).toHaveBeenCalledTimes(1)
  })

  it('导出占位：未注入处理时提示且不动作', async () => {
    const wrapper = mountPreview()
    expect(wrapper.find('[data-test="print-preview-placeholder"]').exists()).toBe(true)
    await wrapper.get('[data-test="print-preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')).toBeUndefined()
  })

  it('导出注入后上抛结果；失败上抛 failed 且可重试', async () => {
    let fail = true
    const jobs = {
      exportPdf: async () => {
        if (fail) {
          throw new Error('服务端渲染失败')
        }
        return { fileId: 'f1', message: '已生成 PDF' }
      },
    }
    const wrapper = mountPreview({ jobs })
    await wrapper.get('[data-test="print-preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('failed')?.[0]?.[0]).toEqual({ phase: 'failed', message: '服务端渲染失败' })
    expect(wrapper.get('[data-test="print-preview-error"]').text()).toContain('服务端渲染失败')

    fail = false
    await wrapper.get('[data-test="print-preview-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')?.[0]?.[0]).toEqual({ fileId: 'f1', message: '已生成 PDF' })
  })

  it('批量打印：按单据键上抛结果', async () => {
    const jobs = { batchPrint: async (payload: { keys: string[] }) => ({ fileId: `batch-${payload.keys.length}` }) }
    const wrapper = mountPreview({ jobs, batchKeys: ['a', 'b', 'c'] })
    await wrapper.get('[data-test="print-preview-batch"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('batch-printed')?.[0]?.[0]).toEqual({ fileId: 'batch-3' })
  })

  it('权限过滤：无导出权限时不动作', async () => {
    const wrapper = mountPreview({
      jobs: { exportPdf: async () => ({ fileId: 'f9' }) },
      exportPerm: 'order.export',
      permChecker: () => false,
    })
    expect(wrapper.get('[data-test="print-preview-export"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="print-preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')).toBeUndefined()
  })
})

describe('PrintButton 入口件', () => {
  let printSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    printSpy = vi.fn()
    Object.defineProperty(window, 'print', { value: printSpy, writable: true, configurable: true })
  })

  /**
   * 挂载入口件。
   *
   * @param props 覆盖属性。
   */
  function mountButton(props: Record<string, unknown> = {}) {
    return mount(PrintButton, {
      props: {
        templates: TEMPLATES,
        data: { fields: FIELDS, rows: ROWS },
        watermarkLabel: '作废',
        ...props,
      },
    })
  }

  it('下拉展开与打印预览上抛', async () => {
    const wrapper = mountButton()
    expect(wrapper.find('[data-test="print-button-menu"]').exists()).toBe(false)

    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    expect(wrapper.find('[data-test="print-button-menu"]').exists()).toBe(true)

    await wrapper.get('[data-test="print-button-preview"]').trigger('click')
    expect(wrapper.emitted('preview')).toHaveLength(1)
    expect(wrapper.find('[data-test="print-button-menu"]').exists()).toBe(false)
  })

  it('浏览器打印上抛事件并调起 window.print', async () => {
    const wrapper = mountButton()
    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    await wrapper.get('[data-test="print-button-print"]').trigger('click')
    expect(wrapper.emitted('print')).toHaveLength(1)
    expect(printSpy).toHaveBeenCalledTimes(1)
  })

  it('导出未注入处理时展示占位提示且导出项禁用', async () => {
    const wrapper = mountButton()
    expect(wrapper.get('[data-test="print-button-hint"]').text()).toContain('占位')
    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    const item = wrapper.get('[data-test="print-button-export"]')
    expect(item.attributes('disabled')).toBeDefined()
    await item.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')).toBeUndefined()
  })

  it('导出注入后上抛结果', async () => {
    const wrapper = mountButton({ jobs: { exportPdf: async () => ({ fileId: 'f7' }) } })
    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    await wrapper.get('[data-test="print-button-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')?.[0]?.[0]).toEqual({ fileId: 'f7' })
  })

  it('批量项按选中单据存在性渲染', async () => {
    const empty = mountButton()
    await empty.get('[data-test="print-button-trigger"]').trigger('click')
    expect(empty.find('[data-test="print-button-batch"]').exists()).toBe(false)

    const wrapper = mountButton({
      jobs: { batchPrint: async () => ({ fileId: 'b' }) },
      batchKeys: ['a', 'b'],
    })
    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    const batch = wrapper.get('[data-test="print-button-batch"]')
    expect(batch.text()).toContain('2')
    await batch.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('batch-printed')?.[0]?.[0]).toEqual({ fileId: 'b' })
  })

  it('无导出权限时不渲染导出项', async () => {
    const wrapper = mountButton({
      jobs: { exportPdf: async () => ({ fileId: 'f8' }) },
      exportPerm: 'order.export',
      permChecker: () => false,
    })
    await wrapper.get('[data-test="print-button-trigger"]').trigger('click')
    expect(wrapper.find('[data-test="print-button-export"]').exists()).toBe(false)
  })
})
