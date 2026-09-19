// kiwi_id: 769
/** 导入领域纯函数用例（08-5-1）：文件校验 / 内容派生幂等键 / 结果归一 / 分页 / 错误文案 / 文件名。 */

import { describe, expect, it } from 'vitest'

import {
  IMPORT_ERROR_DISPLAY_LIMIT,
  checkImportFile,
  deriveImportKey,
  errorReportFileName,
  fileExtension,
  fnv1aHex,
  isFileLevelError,
  normalizeAccept,
  normalizeImportResult,
  paginateImportErrors,
  resolveImportErrorText,
  resolveImportSummary,
  templateFileName,
  type ImportErrorRow,
} from '../src'

describe('文件校验', () => {
  it('扩展名与类型白名单归一', () => {
    expect(fileExtension('users.XLSX')).toBe('.xlsx')
    expect(fileExtension('users')).toBe('')
    expect(normalizeAccept(' .xlsx , .XLS ,, ')).toEqual(['.xlsx', '.xls'])
  })

  it('类型 → 大小 → 空文件顺序短路', () => {
    expect(checkImportFile({ name: 'users.txt', size: 10 })).toEqual({
      valid: false,
      reason: 'type',
      message: '仅支持 .xlsx 文件',
    })
    expect(checkImportFile({ name: 'users.xlsx', size: 21 * 1024 * 1024 }).reason).toBe('size')
    expect(checkImportFile({ name: 'users.xlsx', size: 0 }).reason).toBe('empty')
    expect(checkImportFile({ name: 'users.xlsx', size: 1024 })).toEqual({ valid: true, message: '' })
  })

  it('不限类型与不限大小', () => {
    expect(checkImportFile({ name: 'users.csv', size: 10 }, { accept: '' }).valid).toBe(true)
    expect(checkImportFile({ name: 'users.xlsx', size: 30 * 1024 * 1024 }, { maxSize: 0 }).valid).toBe(true)
  })
})

describe('内容派生幂等键', () => {
  const meta = { name: 'users.xlsx', size: 1024, lastModified: 1_700_000_000_000 }

  it('同内容同键、内容变更换键、业务变更换键', () => {
    const key = deriveImportKey('users', meta)
    expect(key.startsWith('imp:users:')).toBe(true)
    expect(key).toBe(deriveImportKey('users', { ...meta }))
    expect(key).not.toBe(deriveImportKey('users', { ...meta, size: meta.size + 1 }))
    expect(key).not.toBe(deriveImportKey('depts', meta))
    expect(key.endsWith(fnv1aHex(`users|${meta.name}|${meta.size}|${meta.lastModified}`))).toBe(true)
  })

  it('缺省修改时间按 0 参与派生', () => {
    expect(deriveImportKey('users', { name: 'a.xlsx', size: 1 })).toBe(
      deriveImportKey('users', { name: 'a.xlsx', size: 1, lastModified: 0 }),
    )
  })
})

describe('结果归一与汇总态', () => {
  it('省略字段补零、错误行归一、failCount 缺省按错误行数', () => {
    expect(normalizeImportResult(undefined)).toEqual({ total: 0, successCount: 0, failCount: 0, errors: [] })
    expect(normalizeImportResult({ total: 10, successCount: 8, errors: [{ row: 3, column: 'email', message: '非法' }] })).toEqual({
      total: 10,
      successCount: 8,
      failCount: 1,
      errors: [{ row: 3, column: 'email', message: '非法' }],
    })
    expect(normalizeImportResult({ errors: [{ message: '缺行号' }] }).errors[0]).toEqual({ row: 0, message: '缺行号' })
    expect(normalizeImportResult({ errors: [{ row: 2, column: '' }] }).errors[0]).toEqual({ row: 2, message: '' })
  })

  it('汇总态：无数据 / 全部成功 / 部分失败', () => {
    expect(resolveImportSummary({ total: 0, successCount: 0, failCount: 0, errors: [] })).toBe('empty')
    expect(resolveImportSummary({ total: 3, successCount: 3, failCount: 0, errors: [] })).toBe('success')
    expect(resolveImportSummary({ total: 3, successCount: 2, failCount: 1, errors: [] })).toBe('warning')
  })
})

describe('文件级错误与错误文案', () => {
  it('文件段错误码判定', () => {
    expect(isFileLevelError(51001)).toBe(true)
    expect(isFileLevelError(59999)).toBe(true)
    expect(isFileLevelError(30001)).toBe(false)
    expect(isFileLevelError(undefined)).toBe(false)
  })

  it('错误文案：有码给 i18n 键、无码仅兜底文本', () => {
    expect(resolveImportErrorText({ code: 51001, message: '模板列不匹配' })).toEqual({
      i18nKey: 'error.51001',
      text: '模板列不匹配',
    })
    expect(resolveImportErrorText({ message: '网络超时' })).toEqual({ i18nKey: '', text: '网络超时' })
  })
})

describe('错误行分页', () => {
  const rows: ImportErrorRow[] = Array.from({ length: 45 }, (_, index) => ({ row: index + 2, message: '格式非法' }))

  it('页码夹取与每页行数', () => {
    expect(paginateImportErrors(rows, 1).rows).toHaveLength(20)
    expect(paginateImportErrors(rows, 3).rows).toHaveLength(5)
    expect(paginateImportErrors(rows, 99).page).toBe(3)
    expect(paginateImportErrors(rows, -1).page).toBe(1)
    expect(paginateImportErrors(rows, 2).pageCount).toBe(3)
    expect(paginateImportErrors([], 1).pageCount).toBe(1)
  })

  it('超展示上限仅取前 N 行并置截断标记', () => {
    const many: ImportErrorRow[] = Array.from({ length: IMPORT_ERROR_DISPLAY_LIMIT + 5 }, (_, index) => ({
      row: index + 2,
      message: '非法',
    }))
    const page = paginateImportErrors(many, 1)
    expect(page.truncated).toBe(true)
    expect(page.total).toBe(IMPORT_ERROR_DISPLAY_LIMIT + 5)
    expect(page.pageCount).toBe(IMPORT_ERROR_DISPLAY_LIMIT / 20)
    expect(paginateImportErrors(rows, 1).truncated).toBe(false)
  })
})

describe('下载文件名', () => {
  it('模板与错误明细文件名含领域前缀与紧凑时间戳', () => {
    expect(templateFileName('用户')).toBe('用户-导入模板.xlsx')
    expect(errorReportFileName('用户', new Date(2026, 8, 19, 10, 20, 30))).toBe('用户-导入错误明细-20260919102030.xlsx')
  })
})
