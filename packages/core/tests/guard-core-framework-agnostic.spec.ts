/** 护栏：核心框架无关（`packages/core` 不得依赖 Vue / UI 库 / 插件 / 宿主）。 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const coreRoot = resolve(import.meta.dirname, '..')

/** 禁止的 import 来源（渲染框架 / UI 库 / 插件 / 宿主） */
const FORBIDDEN_IMPORT = /(^|[/])(vue|@vue[/]|element-plus|vant|@bms[/](vue|ui-ep|ui-vant)|apps[/])/i

function sourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path))
    } else if (entry.endsWith('.ts')) {
      out.push(path)
    }
  }
  return out
}

/** 扫描源码中的 import 来源，返回违规项 */
export function scanForbiddenImports(files: { path: string; source: string }[]): string[] {
  const problems: string[] = []
  for (const file of files) {
    for (const match of file.source.matchAll(/^\s*(?:import|export)[^'"]*from\s+['"]([^'"]+)['"]/gm)) {
      const specifier = match[1] ?? ''
      if (FORBIDDEN_IMPORT.test(specifier)) {
        problems.push(`${file.path} → ${specifier}`)
      }
    }
  }
  return problems
}

describe('核心框架无关护栏', () => {
  it('① 源码零框架依赖（当前仓库）', () => {
    const files = sourceFiles(join(coreRoot, 'src')).map((path) => ({
      path,
      source: readFileSync(path, 'utf-8'),
    }))
    expect(files.length).toBeGreaterThan(0)
    expect(scanForbiddenImports(files)).toEqual([])
  })

  it('② 包依赖面为空（核心不得声明运行时依赖）', () => {
    const pkg = JSON.parse(readFileSync(join(coreRoot, 'package.json'), 'utf-8')) as Record<string, unknown>
    expect(pkg.dependencies ?? {}).toEqual({})
    expect(pkg.peerDependencies ?? {}).toEqual({})
  })

  it('③ fixture 违规被拦截（vue / 插件 / 宿主）', () => {
    const problems = scanForbiddenImports([
      { path: 'src/probe.ts', source: "import { ref } from 'vue'" },
      { path: 'src/probe2.ts', source: "import { ElButton } from 'element-plus'" },
      { path: 'src/probe3.ts', source: "import { x } from '../../apps/desktop/src/x'" },
    ])
    expect(problems).toHaveLength(3)
  })
})
