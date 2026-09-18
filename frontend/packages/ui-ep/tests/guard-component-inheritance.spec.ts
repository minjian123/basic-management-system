/** 护栏：`ui-ep` 组件须经基类（直接引核心基类或基类投影组合式），禁链外自由挂接。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')
const CORE_BASE_PATTERN = /@bms\/core/
const PROJECTION_PATTERN = /use(Base|ModalShell|Feedback|TabNav|SideMenu)/

function walk(dir: string, suffix: string): string[] {
  const result: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      result.push(...walk(path, suffix))
    } else if (path.endsWith(suffix)) {
      result.push(path)
    }
  }
  return result
}

describe('组件继承链护栏', () => {
  it('每个组件都经核心基类或基类投影组合式', () => {
    const components = walk(join(SRC, 'components'), '.vue')
    expect(components.length).toBeGreaterThan(10)

    const offenders = components.filter((file) => {
      const source = readFileSync(file, 'utf8')
      return !CORE_BASE_PATTERN.test(source) && !PROJECTION_PATTERN.test(source)
    })
    expect(offenders, `以下组件未挂继承链：${offenders.join(', ')}`).toEqual([])
  })

  it('每个基类投影组合式都从核心引入基类', () => {
    const projections = walk(join(SRC, 'composables'), '.ts')
    const offenders = projections.filter((file) => {
      const source = readFileSync(file, 'utf8')
      return !CORE_BASE_PATTERN.test(source)
    })
    expect(offenders, `以下组合式未引入核心基类：${offenders.join(', ')}`).toEqual([])
  })
})
