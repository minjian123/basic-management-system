// kiwi_id: 766
/** 打印模板与编排用例（08_03_03）：模板与数据装配 / 纸张与黑白 / 水印 / 打印上下文 / 分页 / 预览与缩放 / 导出与批量阶段（含占位、进度、失败重试、异步协作与权限过滤）。 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseAsyncTask,
  BaseLocale,
  BaseNotice,
  BasePrint,
  BasePrintTemplate,
  BaseWatermark,
  PRINT_JOB_PLACEHOLDER,
  configureBase,
  resetBaseSinks,
  validateCapabilityGraph,
  type PrintColumnDef,
  type PrintFieldDef,
  type PrintJobHandler,
  type PrintJobResult,
  type PrintTemplateDef,
} from '../src'

/** 具体打印模板件（可实例化）。 */
class Template extends BasePrintTemplate {}

/** 具体打印编排件（可实例化）。 */
class Print extends BasePrint {}

/** 水印能力样例。 */
class SampleWatermark extends BaseWatermark {}

/** 提示通知能力样例。 */
class SampleNotice extends BaseNotice {}

/** 语言上下文能力样例。 */
class SampleLocale extends BaseLocale {}

/** 权限上下文样例（仅含给定权限码）。 */
class SampleAccess extends BaseAccess {
  /**
   * 构造权限上下文。
   *
   * @param codes 权限码。
   */
  constructor(codes: string[]) {
    super()
    this.setCodes(codes)
  }
}

/** 异步任务样例。 */
class SampleTask extends BaseAsyncTask<PrintJobResult> {}

/** 样例模板集（`order` 三列 + 每页 2 行；`label` 单列）。 */
const TEMPLATES: PrintTemplateDef[] = [
  {
    key: 'order',
    title: '销售订单',
    subtitle: 'SO-20260919-0007',
    fields: [
      { key: 'customer', label: '客户' },
      { key: 'signedAt', label: '签订日期', format: 'date' },
      { key: 'amount', label: '订单金额', format: 'amount' },
      { key: 'remark', label: '备注' },
    ],
    columns: [
      { key: 'name', label: '商品' },
      { key: 'qty', label: '数量', format: 'number' },
      { key: 'amount', label: '金额', format: 'amount' },
    ],
    signLabels: ['制单', '审核', '客户签收'],
    footerNote: '本单据为电子凭证',
    summaryKey: 'amount',
    rowsPerPage: 2,
  },
  { key: 'label', title: '标签', columns: [{ key: 'name', label: '名称' }] },
]

/** 五行明细样例。 */
const ROWS = [
  { name: '螺栓', qty: 200, amount: 700 },
  { name: '垫片', qty: 500, amount: 600 },
  { name: '法兰', qty: 40, amount: 2720 },
  { name: '线缆', qty: 10, amount: 120 },
  { name: '支架', qty: 8, amount: 80 },
]

/**
 * 构造挂好模板与数据的打印件。
 *
 * @param data 单据数据（缺省用样例）。
 */
function makePrint(data: Record<string, unknown> = { customer: '华东制造有限公司' }): Print {
  const print = new Print()
  print.setTemplates(TEMPLATES)
  print.setData({ fields: data, rows: ROWS })
  return print
}

/**
 * 构造导出处理函数（回传进度）。
 *
 * @param result 返回结果。
 * @param progress 上报进度（缺省不上报）。
 */
function exportHandler(result: PrintJobResult, progress?: { current: number; total: number }): PrintJobHandler {
  return async (payload, report) => {
    if (progress !== undefined) {
      report(progress)
    }
    return { ...result, message: `${result.message ?? '导出完成'}:${payload.templateKey}` }
  }
}

describe('能力登记', () => {
  it('新增两条打印能力链登记合规（依赖已登记 / 无环）', () => {
    expect(validateCapabilityGraph()).toEqual([])
    expect(new Template().identifier).toBe('print-template')
    expect(new Print().identifier).toBe('print')
  })
})

describe('BasePrintTemplate 模板与数据装配', () => {
  it('模板集与选择（键不存在时不生效）', () => {
    const print = new Template()
    expect(print.template).toBeUndefined()

    print.setTemplates(TEMPLATES)
    expect(print.templateKey).toBe('order')
    expect(print.template?.title).toBe('销售订单')

    print.selectTemplate('label')
    expect(print.templateKey).toBe('label')
    expect(print.template?.title).toBe('标签')

    print.selectTemplate('absent')
    expect(print.templateKey).toBe('label')

    print.setTemplates([TEMPLATES[1] as PrintTemplateDef])
    expect(print.templateKey).toBe('label')
  })

  it('字段渲染：值格式、内联值优先、缺失占位', () => {
    const print = makePrint({ customer: '华东制造有限公司', signedAt: '2026-09-19', amount: 4220 })
    const fields = print.template?.fields ?? []
    expect(print.fieldValue(fields[0] as PrintFieldDef)).toBe('华东制造有限公司')
    expect(print.fieldValue(fields[1] as PrintFieldDef)).toContain('2026')
    expect(print.fieldValue(fields[2] as PrintFieldDef)).toContain('4,220.00')
    expect(print.fieldValue(fields[3] as PrintFieldDef)).toBe('—')
    expect(print.fieldValue({ key: 'inline', label: '来源', value: '销售录入' })).toBe('销售录入')
    expect(print.missingText).toBe('—')
  })

  it('明细单元格按列格式渲染', () => {
    const print = makePrint()
    const columns = print.template?.columns ?? []
    const row = ROWS[0] as Record<string, unknown>
    expect(print.cellText(columns[0] as PrintColumnDef, row)).toBe('螺栓')
    expect(print.cellText(columns[2] as PrintColumnDef, row)).toContain('700.00')
    expect(print.cellText({ key: 'absent', label: '缺' }, row)).toBe('—')
  })

  it('语言上下文影响格式化', () => {
    const locale = new SampleLocale()
    locale.setLocale('en-US')
    locale.setTimezone('UTC')
    const print = makePrint({ signedAt: '2026-09-19' })
    print.locale = locale
    expect(print.fieldValue({ key: 'signedAt', label: '签订日期', format: 'date' })).toContain('Sep')
    expect(print.formatContext).toEqual({ locale: 'en-US', timezone: 'UTC' })
  })

  it('纸张、方向与自定义尺寸', () => {
    const print = makePrint()
    expect(print.paperSize).toEqual({ width: 210, height: 297 })

    print.setPaper('A5', 'landscape')
    expect(print.paperSize).toEqual({ width: 210, height: 148 })

    print.setPaper('custom', 'portrait')
    print.setCustomSize({ width: 100, height: 200 })
    expect(print.paperSize).toEqual({ width: 100, height: 200 })
  })

  it('黑白切换与样式变量名', () => {
    const print = makePrint()
    expect(print.mono).toBe(false)
    expect(print.toggleTone()).toBe('mono')
    expect(print.mono).toBe(true)
    expect(print.styleVars['margin']).toBe('--bms-print-margin')
  })

  it('水印：单据级标签 + 用户 / 租户信息，可关闭', () => {
    const print = makePrint()
    const watermark = new SampleWatermark()
    watermark.setUser('张三')
    watermark.setTenant('租户一')
    print.watermark = watermark
    expect(print.hasWatermark).toBe(true)
    expect(print.watermarkText).toBe('张三 / 租户一')

    print.setWatermarkLabel('作废')
    expect(print.watermarkText).toBe('作废 · 张三 / 租户一')

    print.setWatermarkEnabled(false)
    expect(print.hasWatermark).toBe(false)
    expect(print.watermarkText).toBe('')
  })

  it('分页与汇总、页脚（打印上下文）', () => {
    const print = makePrint()
    expect(print.rowsPerPage).toBe(2)
    expect(print.pages.map((page) => page.rows.length)).toEqual([2, 2, 1])
    expect(print.summary).toBe(4220)
    expect(print.summaryText).toContain('合计')
    expect(print.summaryText).toContain('4,220.00')
    expect(print.fieldRows).toHaveLength(2)

    print.setContext({ printedAt: '2026-09-19 10:00', printedBy: '张三' })
    expect(print.pages[0]?.footer).toContain('打印人 张三')
    expect(print.pages[2]?.footer).toContain('本单据为电子凭证')

    print.setTemplates([TEMPLATES[1] as PrintTemplateDef])
    expect(print.summary).toBe(0)
    expect(print.summaryText).toBe('')
  })
})

describe('BasePrint 预览与编排', () => {
  let print: Print

  beforeEach(() => {
    configureBase({ reporter: () => {} })
    print = makePrint()
  })

  afterEach(() => {
    resetBaseSinks()
  })

  it('预览显隐与缩放夹取（含步进与幂等）', () => {
    expect(print.previewVisible).toBe(false)
    print.open()
    expect(print.previewVisible).toBe(true)
    expect(print.togglePreview()).toBe(false)

    expect(print.setZoom(2)).toBe(1.2)
    expect(print.setZoom(0.1)).toBe(0.6)
    expect(print.setZoom(Number.NaN)).toBe(0.6)

    print.setZoom(1)
    expect(print.zoomOut()).toBe(0.9)
    expect(print.zoomIn()).toBe(1)
    print.close()
    expect(print.previewVisible).toBe(false)
  })

  it('批量模式与导出许可', () => {
    expect(print.batchMode).toBe('separate')
    print.setBatchMode('merged')
    expect(print.batchMode).toBe('merged')

    print.setAllowExport(false)
    expect(print.canExport).toBe(false)
    print.setAllowExport(true)
    expect(print.canExport).toBe(true)
  })

  it('权限过滤：无权时不可打印 / 不可导出', async () => {
    print.access = new SampleAccess(['order.print'])
    print.printPerm = 'order.print'
    print.exportPerm = 'order.export'
    expect(print.canPrint).toBe(true)
    expect(print.canExport).toBe(false)
    await expect(print.exportPdf()).resolves.toBeUndefined()
    expect(print.phase).toBe('idle')
  })

  it('浏览器打印：阶段推进与结果', () => {
    print.beginPrint()
    expect(print.phase).toBe('printing')
    expect(print.busy).toBe(true)

    const result = print.finishPrint()
    expect(print.phase).toBe('done')
    expect(print.busy).toBe(false)
    expect(result.message).toBe('已调起浏览器打印')
    expect(print.lastResult).toEqual(result)

    print.reset()
    expect(print.phase).toBe('idle')
  })

  it('导出占位：未注入处理不动作（不产生请求）', async () => {
    expect(print.exportReady).toBe(false)
    await expect(print.exportPdf()).resolves.toBeUndefined()
    expect(print.phase).toBe('idle')
    expect(print.errorMessage).toBe(PRINT_JOB_PLACEHOLDER)
    await expect(print.retry()).resolves.toBeUndefined()
  })

  it('导出成功：阶段、结果与进度', async () => {
    print.jobs = { exportPdf: exportHandler({ fileId: 'f1' }, { current: 1, total: 1 }) }
    expect(print.exportReady).toBe(true)

    await expect(print.exportPdf()).resolves.toEqual({ fileId: 'f1', message: '导出完成:order' })
    expect(print.phase).toBe('done')
    expect(print.progress).toEqual({ current: 1, total: 1 })
    expect(print.lastResult?.fileId).toBe('f1')
  })

  it('导出失败置 failed 并保留文案，retry 可恢复', async () => {
    let fail = true
    print.jobs = {
      exportPdf: async () => {
        if (fail) {
          throw new Error('服务端渲染失败')
        }
        return { fileId: 'f2' }
      },
    }

    await expect(print.exportPdf()).resolves.toBeUndefined()
    expect(print.phase).toBe('failed')
    expect(print.errorMessage).toBe('服务端渲染失败')

    fail = false
    await expect(print.retry()).resolves.toEqual({ fileId: 'f2' })
    expect(print.phase).toBe('done')
    expect(print.errorMessage).toBe('')
  })

  it('导出中重复请求不动作（防重复提交）', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    print.jobs = {
      exportPdf: async () => {
        await gate
        return { fileId: 'f3' }
      },
    }

    const pending = print.exportPdf()
    expect(print.phase).toBe('exporting')
    expect(print.busy).toBe(true)
    await expect(print.exportPdf()).resolves.toBeUndefined()
    await expect(print.batchPrint(['a'])).resolves.toBeUndefined()

    release()
    await expect(pending).resolves.toEqual({ fileId: 'f3' })
    expect(print.phase).toBe('done')
  })

  it('批量打印：占位、空单据键、进度总量与结果', async () => {
    expect(print.batchReady).toBe(false)
    expect(print.canBatch).toBe(false)
    await expect(print.batchPrint(['a'])).resolves.toBeUndefined()
    expect(print.phase).toBe('idle')

    const seen: string[][] = []
    print.jobs = {
      batchPrint: async (payload, report) => {
        seen.push(payload.keys)
        report({ current: payload.keys.length, total: payload.keys.length })
        return { fileId: 'batch-1', message: `批量完成:${payload.mode}` }
      },
    }
    expect(print.batchReady).toBe(true)
    expect(print.canBatch).toBe(true)
    await expect(print.batchPrint([])).resolves.toBeUndefined()

    const result = await print.batchPrint(['a', 'b', 'c'])
    expect(result).toEqual({ fileId: 'batch-1', message: '批量完成:separate' })
    expect(seen).toEqual([['a', 'b', 'c']])
    expect(print.progress).toEqual({ current: 3, total: 3 })
    expect(print.phase).toBe('done')
  })

  it('经异步任务协作：进度回传与失败处置', async () => {
    const task = new SampleTask()
    print.task = task
    print.jobs = { exportPdf: exportHandler({ fileId: 'f4' }, { current: 1, total: 2 }) }

    await expect(print.exportPdf()).resolves.toEqual({ fileId: 'f4', message: '导出完成:order' })
    expect(task.status).toBe('done')
    expect(task.progress?.value).toBe(1)
    expect(print.progress).toEqual({ current: 1, total: 2 })

    print.reset()
    print.jobs = {
      exportPdf: async () => {
        throw new Error('任务失败')
      },
    }
    await expect(print.exportPdf()).resolves.toBeUndefined()
    expect(print.phase).toBe('failed')
    expect(print.errorMessage).toBe('任务失败')
    expect(task.status).toBe('error')
  })

  it('结果提示经提示能力上抛（注入时）', async () => {
    const notice = new SampleNotice()
    print.notice = notice
    print.jobs = { exportPdf: exportHandler({ fileId: 'f5', message: '已生成 PDF' }) }

    await print.exportPdf()
    expect(notice.queue.map((item) => item.content)).toEqual(['已生成 PDF:order'])

    print.jobs = {
      exportPdf: async () => {
        throw new Error('导出失败')
      },
    }
    print.reset()
    await print.exportPdf()
    expect(notice.queue.map((item) => item.type)).toEqual(['success', 'error'])
  })
})
