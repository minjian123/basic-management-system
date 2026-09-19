// kiwi_id: 766
/** 打印领域纯函数用例（08_03_03）：纸张解析 / 行容量 / 预分页 / 字段分行 / 汇总 / 页脚 / 色调 / 单元格格式化 / 样式变量名。 */

import { describe, expect, it } from 'vitest'

import {
  PAPER_SIZES,
  PRINT_MISSING_TEXT,
  PRINT_STYLE_VARS,
  buildPrintPages,
  computeRowsPerPage,
  distributeFields,
  formatCellValue,
  formatPageFooter,
  paginateRows,
  resolvePaperSize,
  resolvePrintTone,
  resolveRowsPerPage,
  sumNumeric,
  type PrintTemplateDef,
} from '../src'

/** 分页样例模板（每页 2 行）。 */
const TEMPLATE: PrintTemplateDef = {
  key: 'order',
  title: '销售订单',
  rowsPerPage: 2,
  columns: [{ key: 'amount', label: '金额', format: 'amount' }],
  footerNote: '本单据为电子凭证',
}

/** 五行明细样例。 */
const ROWS = [
  { name: '螺栓', amount: 700 },
  { name: '垫片', amount: 600 },
  { name: '法兰', amount: 2720 },
  { name: '线缆', amount: 120 },
  { name: '支架', amount: 80 },
]

describe('domain/print 纸张解析', () => {
  it('内置纸张纵向与横向（横向交换宽高）', () => {
    expect(resolvePaperSize('A4')).toEqual({ width: 210, height: 297 })
    expect(resolvePaperSize('A4', 'landscape')).toEqual({ width: 297, height: 210 })
    expect(resolvePaperSize('A5', 'landscape')).toEqual({ width: 210, height: 148 })
    expect(PAPER_SIZES.A5).toEqual({ width: 148, height: 210 })
  })

  it('自定义尺寸：合法取用，缺失或非法回落 A4', () => {
    expect(resolvePaperSize('custom', 'portrait', { width: 100, height: 150 })).toEqual({ width: 100, height: 150 })
    expect(resolvePaperSize('custom')).toEqual(PAPER_SIZES.A4)
    expect(resolvePaperSize('custom', 'portrait', { width: 0, height: 150 })).toEqual(PAPER_SIZES.A4)
    expect(resolvePaperSize('custom', 'portrait', { width: Number.NaN, height: 150 })).toEqual(PAPER_SIZES.A4)
  })
})

describe('domain/print 行容量与分页', () => {
  it('行容量按纸张高减去占位高度计算，至少 1 行', () => {
    expect(computeRowsPerPage({ paperHeight: 297, rowHeight: 8, chromeHeight: 60 })).toBe(29)
    expect(computeRowsPerPage({ paperHeight: 60, rowHeight: 8, chromeHeight: 60 })).toBe(1)
    expect(computeRowsPerPage({ paperHeight: 297, rowHeight: 0, chromeHeight: 60 })).toBe(237)
    expect(computeRowsPerPage({ paperHeight: Number.NaN, rowHeight: 8, chromeHeight: 60 })).toBe(1)
  })

  it('分页保序；容量非法按 1；空输入返回空数组', () => {
    expect(paginateRows([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]])
    expect(paginateRows([1, 2], 0)).toEqual([[1], [2]])
    expect(paginateRows([], 3)).toEqual([])
  })

  it('模板级行容量优先，其次按纸张与行高计算', () => {
    expect(resolveRowsPerPage(TEMPLATE, PAPER_SIZES.A4)).toBe(2)
    expect(resolveRowsPerPage({ key: 'k', title: 't', rowsPerPage: 0 }, PAPER_SIZES.A4)).toBe(29)
    expect(resolveRowsPerPage({ key: 'k', title: 't', rowHeight: 10, chromeHeight: 50 }, PAPER_SIZES.A5)).toBe(16)
  })

  it('字段区按列数分行（保持顺序）', () => {
    expect(distributeFields(['a', 'b', 'c'], 2)).toEqual([['a', 'b'], ['c']])
    expect(distributeFields(['a', 'b'], 2)).toEqual([['a', 'b']])
    expect(distributeFields(['a', 'b'], 0)).toEqual([['a'], ['b']])
    expect(distributeFields([], 2)).toEqual([])
  })
})

describe('domain/print 汇总、页脚与色调', () => {
  it('数值列汇总仅累加有限数值', () => {
    expect(sumNumeric(ROWS, 'amount')).toBe(4220)
    expect(sumNumeric([{ amount: '3' }, { amount: null }, { amount: '' }, { amount: 'x' }], 'amount')).toBe(3)
    expect(sumNumeric([], 'amount')).toBe(0)
  })

  it('页脚含页码与打印信息，缺失项不输出', () => {
    expect(formatPageFooter({ index: 1, total: 3 })).toBe('第 1 页 / 共 3 页')
    expect(
      formatPageFooter({ index: 2, total: 3, printedAt: '2026-09-19 10:00', printedBy: '张三', note: '电子凭证' }),
    ).toBe('第 2 页 / 共 3 页 · 打印时间 2026-09-19 10:00 · 打印人 张三 · 电子凭证')
    expect(formatPageFooter({ index: 0, total: 0 })).toBe('第 1 页 / 共 1 页')
  })

  it('色调解析：黑白给置灰滤镜，彩色为空', () => {
    expect(resolvePrintTone('mono')).toEqual({ mono: true, filter: 'grayscale(1)' })
    expect(resolvePrintTone('color')).toEqual({ mono: false, filter: '' })
  })

  it('样式变量名以打印令牌前缀命名', () => {
    for (const name of Object.values(PRINT_STYLE_VARS)) {
      expect(name.startsWith('--bms-print-')).toBe(true)
    }
  })
})

describe('domain/print 构建打印页', () => {
  it('按容量分页：页码连续、首页末页标记、页脚带打印信息', () => {
    const pages = buildPrintPages({
      template: TEMPLATE,
      data: { rows: ROWS },
      paperSize: PAPER_SIZES.A4,
      printedAt: '2026-09-19 10:00',
      printedBy: '张三',
    })
    expect(pages.map((page) => page.rows.length)).toEqual([2, 2, 1])
    expect(pages.map((page) => page.index)).toEqual([1, 2, 3])
    expect(pages.every((page) => page.total === 3)).toBe(true)
    expect(pages[0]?.isFirst).toBe(true)
    expect(pages[2]?.isLast).toBe(true)
    expect(pages[1]?.isFirst).toBe(false)
    expect(pages[0]?.footer).toContain('第 1 页 / 共 3 页')
    expect(pages[2]?.footer).toContain('打印人 张三')
    expect(pages[2]?.footer).toContain('本单据为电子凭证')
  })

  it('空明细返回单页空页（空数据打印仍可行）', () => {
    const pages = buildPrintPages({ template: TEMPLATE, paperSize: PAPER_SIZES.A4 })
    expect(pages).toHaveLength(1)
    expect(pages[0]?.rows).toEqual([])
    expect(pages[0]?.isFirst).toBe(true)
    expect(pages[0]?.isLast).toBe(true)
    expect(pages[0]?.footer).toBe('第 1 页 / 共 1 页 · 本单据为电子凭证')
  })

  it('无声明容量时按纸张高与行高计算（A5 横向）', () => {
    const pages = buildPrintPages({
      template: { key: 'label', title: '标签', rowHeight: 10, chromeHeight: 0 },
      data: { rows: ROWS },
      paperSize: resolvePaperSize('A5', 'landscape'),
    })
    expect(pages).toHaveLength(1)
    expect(pages[0]?.rows).toHaveLength(5)
  })
})

describe('domain/print 单元格格式化', () => {
  it('按格式渲染，空值与非法值回落占位', () => {
    expect(formatCellValue('华东制造有限公司')).toBe('华东制造有限公司')
    expect(formatCellValue(1234.5, 'amount')).toContain('1,234.50')
    expect(formatCellValue(1234.5, 'number')).toContain('1,234.5')
    expect(formatCellValue('2026-09-19', 'date')).toContain('2026')
    expect(formatCellValue('2026-09-19 10:00', 'datetime')).toContain('2026')
    expect(formatCellValue('abc', 'amount')).toBe('abc')
    expect(formatCellValue(undefined)).toBe(PRINT_MISSING_TEXT)
    expect(formatCellValue(null, 'amount')).toBe(PRINT_MISSING_TEXT)
    expect(formatCellValue('')).toBe(PRINT_MISSING_TEXT)
  })

  it('格式化上下文影响语言与时区', () => {
    expect(formatCellValue('2026-09-19', 'date', { locale: 'en-US', timezone: 'UTC' })).toContain('Sep')
  })
})
