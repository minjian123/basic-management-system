// kiwi_id: 2396
/**
 * 护栏（雪花 ID）：前端源码禁止把 ID 交给 `Number()` / `parseInt()` / `parseFloat()`
 * 或断言为 `number`——126 位 ID 超出 JS 安全整数，数值化会静默截断。
 *
 * 覆盖范围：桌面端 `src`、`packages/ui_ep/src`、各 `modules/*\/src` 手写源码；
 * 生成类型（`packages/api_types`）由契约保证为字符串，不在扫描范围。
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const FRONTEND = resolve(process.cwd(), '../..')
const SOURCES = [
  join(FRONTEND, 'apps/desktop/src'),
  join(FRONTEND, 'packages/ui_ep/src'),
  join(FRONTEND, 'modules'),
]

/** 可能被数值化的 ID 标识符（`jobId` / `job_id` / `xxx.id` 的后半段）。 */
const ID_IDENT = /\b[A-Za-z_$][\w$]*(?:Id|_id)\b/
/** 数值化调用。 */
const NUMERIC_CALL = /\b(?:Number|parseInt|parseFloat)\s*\(/
/** 类型断言。 */
const NUMBER_CAST = /\bas\s+number\b/

/**
 * 判断单行是否违规（注释行跳过）。
 *
 * @param line 源码行。
 * @returns 是否命中违规。
 */
export function isBigIdRisk(line: string): boolean {
  const trimmed = line.trim()
  if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) {
    return false
  }
  if (NUMERIC_CALL.test(line) && ID_IDENT.test(line)) {
    return true
  }
  return ID_IDENT.test(line) && NUMBER_CAST.test(line)
}

/**
 * 扫描源码清单。
 *
 * @param files 文件路径与内容。
 * @returns 违规明细（文件:行号:内容）。
 */
export function scanBigIdGuards(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    file.source.split('\n').forEach((line, index) => {
      if (isBigIdRisk(line)) {
        problems.push(`${file.path}:${index + 1}: ${line.trim()}`)
      }
    })
  }
  return problems
}

/**
 * 递归收集源码文件。
 *
 * @param dir 目录。
 * @param out 结果累加。
 * @returns 文件清单。
 */
function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue
      walk(path, out)
    } else if (/\.(ts|tsx|vue)$/.test(path)) {
      out.push(path)
    }
  }
  return out
}

describe('雪花 ID 前端护栏（kiwi 2396）', () => {
  it('识别 Number()/parseInt()/as number 的 ID 数值化', () => {
    expect(isBigIdRisk('const n = Number(row.job_id)')).toBe(true)
    expect(isBigIdRisk('const n = parseInt(payload.userId, 10)')).toBe(true)
    expect(isBigIdRisk('const n = item.tenantId as number')).toBe(true)
    expect(isBigIdRisk('const n = Number(row.count)')).toBe(false)
    expect(isBigIdRisk('// Number(row.job_id)')).toBe(false)
    expect(isBigIdRisk('const id: string = row.job_id')).toBe(false)
  })

  it('手写源码无大 ID 数值化', () => {
    const files = SOURCES.flatMap((dir) => walk(dir)).map((path) => ({
      path,
      source: readFileSync(path, 'utf8'),
    }))
    expect(files.length).toBeGreaterThan(0)
    expect(scanBigIdGuards(files)).toEqual([])
  })
})
