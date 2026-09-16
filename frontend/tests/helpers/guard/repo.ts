/** 护栏仓库索引：文件集 / 片段表 / 基类导出 / 域基类文件 / 清单文本（供四类护栏用例共用）。 */

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { FRAGMENTS } from '@/components/base/fragments'

import type { GuardFile } from './ast'

const here = dirname(fileURLToPath(import.meta.url))
/** 前端仓库根（`tests/helpers/guard` → 上三级） */
export const repoRoot = resolve(here, '../../..')

function walk(dir: string, out: string[]): void {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(path, out)
    } else {
      out.push(path)
    }
  }
}

/** 收集目录下文件（相对仓库根路径 + 源码） */
export function repoFiles(dirs: string[], extensions: string[]): GuardFile[] {
  const files: GuardFile[] = []
  for (const dir of dirs) {
    const paths: string[] = []
    walk(join(repoRoot, dir), paths)
    for (const path of paths) {
      if (!extensions.some((extension) => path.endsWith(extension))) {
        continue
      }
      files.push({
        path: path
          .slice(repoRoot.length + 1)
          .split('\\')
          .join('/'),
        source: readFileSync(path, 'utf8'),
      })
    }
  }
  return files
}

/** 读取《前端基类清单》（monorepo 口径；不存在返回 `undefined`，独立克隆时对账用例跳过） */
export function readManifest(): string | undefined {
  try {
    return readFileSync(resolve(repoRoot, '../bms文档/前端基类清单.md'), 'utf8')
  } catch {
    return undefined
  }
}

/** 仓库索引 */
export interface RepoIndex {
  files: GuardFile[]
  fragmentKeys: string[]
  fragmentDepends: Record<string, string[]>
  /** 片段实现文件名（`useXxx.ts`；不含域基类组合式与上下文机制） */
  fragmentFiles: string[]
  /** `src/base/` 导出类名 */
  baseExports: string[]
  /** 域基类包装路径 */
  domainFiles: string[]
}

/** 构建仓库索引（一次读盘，供护栏用例复用） */
export function buildRepoIndex(): RepoIndex {
  const files = repoFiles(['src/base', 'src/components/base'], ['.ts', '.vue'])

  const fragmentDepends: Record<string, string[]> = {}
  for (const [key, depends] of Object.entries(FRAGMENTS)) {
    fragmentDepends[key] = [...depends]
  }

  const fragmentFiles = files
    .filter((file) => /^src\/components\/base\/[^/]+\/use[A-Za-z0-9]+\.ts$/.test(file.path))
    .map((file) => file.path.split('/').pop() ?? '')
    .filter((name) => name.length > 0 && !/Base\.ts$/.test(name) && name !== 'useFieldContext.ts')

  const baseExports: string[] = []
  for (const file of files) {
    if (!/^src\/base\/.+\.ts$/.test(file.path)) {
      continue
    }
    for (const match of file.source.matchAll(/export\s+(?:abstract\s+)?class\s+([A-Za-z0-9_]+)/g)) {
      const name = match[1]
      if (name && !baseExports.includes(name)) {
        baseExports.push(name)
      }
    }
  }

  const domainFiles = files
    .filter((file) => /^src\/components\/base\/(input|display|tree|editor)\/Base[A-Za-z0-9]+\.vue$/.test(file.path))
    .map((file) => file.path)

  return {
    files,
    fragmentKeys: Object.keys(fragmentDepends),
    fragmentDepends,
    fragmentFiles,
    baseExports,
    domainFiles,
  }
}
