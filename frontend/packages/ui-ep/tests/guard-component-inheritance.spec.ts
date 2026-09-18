/** 护栏：`ui-ep` 组件须**实质**挂继承链（值引入核心 `Base*` 或基类投影组合式），类型引入不算。 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')

/** 值引入核心基类（如 `import { BaseLayout } from '@bms/core'`）。 */
const VALUE_BASE_PATTERN = /import\s*\{[^}]*\bBase[A-Z]\w*[^}]*\}\s*from\s*'@bms\/core'/
/** 值引入基类投影组合式（如 `import { useBaseLayout } from '../../composables/useBaseLayout'`）。 */
const VALUE_PROJECTION_PATTERN = /import\s*\{[^}]*\buse\w+[^}]*\}\s*from\s*'(?:[^']*composables\/use[^']*|\.{1,2}\/use[^']*)'/
/** 类型引入（`import type ...`）；挂链判定前先剔除。 */
const TYPE_IMPORT_PATTERN = /import\s+type\s*(?:\{[^}]*\}|[A-Za-z_$][\w$]*)\s*from\s*'[^']*'/gs

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

function stripTypeImports(source: string): string {
  return source.replace(TYPE_IMPORT_PATTERN, '')
}

describe('组件继承链护栏', () => {
  it('每个组件都以值引入核心基类或基类投影（类型引入不算挂链）', () => {
    const components = walk(join(SRC, 'components'), '.vue')
    expect(components.length).toBeGreaterThan(10)

    const offenders = components.filter((file) => {
      const source = stripTypeImports(readFileSync(file, 'utf8'))
      return !VALUE_BASE_PATTERN.test(source) && !VALUE_PROJECTION_PATTERN.test(source)
    })
    expect(offenders, `以下组件未实质挂继承链：${offenders.join(', ')}`).toEqual([])
  })

  it('每个组合式都以值引入核心基类或下层基类投影', () => {
    const projections = walk(join(SRC, 'composables'), '.ts')
    const offenders = projections.filter((file) => {
      const source = stripTypeImports(readFileSync(file, 'utf8'))
      return !VALUE_BASE_PATTERN.test(source) && !VALUE_PROJECTION_PATTERN.test(source)
    })
    expect(offenders, `以下组合式未接基类：${offenders.join(', ')}`).toEqual([])
  })
})
