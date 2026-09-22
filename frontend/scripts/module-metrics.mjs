#!/usr/bin/env node
/**
 * 模块产物体积计量（零依赖 ESM；单一实现）。
 *
 * 口径（与模块工程预算脚本同源）：**容器入口块** = 远端加载必下的块闭包，自 `dist/remoteEntry.js`
 * 出发解析引用得到——种子块（`remoteEntry.js`）追「静态引用（`from`）」与「动态引用（`import()`）」，
 * 其余块只追静态引用（页面 / 工具块经动态 `import()` 引用，不进入口闭包）。
 *
 * 供**三处复用**：模块工程预算校验（`modules/<模块名>/scripts/check-bundle-budget.mjs`）、
 * 模块发布记录（`release-module.mjs`）、清单 / 体积护栏（`check-module-manifest.mjs`）。
 *
 * 用法：
 *     import { measureModuleDist } from '../../scripts/module-metrics.mjs'
 *     const size = measureModuleDist(moduleDir)
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'
import { gzipSync } from 'node:zlib'

/** 远端容器入口文件名（与契约常量 `MODULE_REMOTE_ENTRY_FILE` 同值）。 */
export const REMOTE_ENTRY_FILE = 'remoteEntry.js'

/**
 * 递归收集产物目录下的 JS / CSS 文件。
 *
 * @param distDir 产物目录。
 * @returns 绝对路径清单。
 */
export function walkDistFiles(distDir) {
  const files = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) walk(path)
      else if (/\.(js|css)$/.test(entry.name)) files.push(path)
    }
  }
  walk(distDir)
  return files
}

/**
 * 引用名归一（`./assets/x.js` → `assets/x.js`）。
 *
 * @param ref 引用串。
 * @returns 归一后的产物内路径。
 */
function normalizeRef(ref) {
  return ref.replace(/^\.?\//, '').split('?')[0]
}

/**
 * 静态引用（`from './assets/x.js'`）。
 *
 * @param text 产物文本。
 * @returns 引用名集合。
 */
function staticRefs(text) {
  const refs = new Set()
  for (const match of text.matchAll(/\bfrom\s*["']([^"'\s]+\.(?:js|css))["']/g)) {
    refs.add(normalizeRef(match[1]))
  }
  return refs
}

/**
 * 动态引用（`import('./assets/x.js')`）。
 *
 * @param text 产物文本。
 * @returns 引用名集合。
 */
function dynamicRefs(text) {
  const refs = new Set()
  for (const match of text.matchAll(/\bimport\s*\(\s*["'`]([^"'`\s]+\.(?:js|css))["'`]\s*\)/g)) {
    refs.add(normalizeRef(match[1]))
  }
  return refs
}

/**
 * 收集容器入口闭包（自 `remoteEntry.js` 出发；种子块追静态 + 动态引用，其余只追静态引用）。
 *
 * @param distDir 产物目录。
 * @returns 闭包内相对文件名集合（缺入口返回空集）。
 */
export function collectEntryClosure(distDir) {
  const files = walkDistFiles(distDir)
  const byName = new Map(files.map((path) => [relative(distDir, path).split('\\').join('/'), path]))
  if (!byName.has(REMOTE_ENTRY_FILE)) return new Set()
  const textOf = (name) => readFileSync(byName.get(name), 'utf8')
  const closure = new Set()
  const queue = [REMOTE_ENTRY_FILE]
  while (queue.length > 0) {
    const name = queue.shift()
    if (closure.has(name) || !byName.has(name)) continue
    closure.add(name)
    const text = textOf(name)
    const refs = name === REMOTE_ENTRY_FILE ? [...staticRefs(text), ...dynamicRefs(text)] : [...staticRefs(text)]
    for (const ref of refs) {
      if (!closure.has(ref) && byName.has(ref)) queue.push(ref)
    }
  }
  return closure
}

/**
 * 测量模块产物体积（入口闭包口径）。
 *
 * @param moduleDir 模块工程目录（含 `dist/`）。
 * @returns `{ entryFiles, entryGzipKb, largestGzipKb, asyncChunkCount }`（缺产物入口返回 `undefined`）。
 */
export function measureModuleDist(moduleDir) {
  const distDir = join(moduleDir, 'dist')
  if (!existsSync(join(distDir, REMOTE_ENTRY_FILE))) return undefined
  const closure = collectEntryClosure(distDir)
  const sizes = [...closure].map((name) => gzipSync(readFileSync(join(distDir, name))).length)
  const total = sizes.reduce((sum, bytes) => sum + bytes, 0)
  const largest = sizes.reduce((max, bytes) => Math.max(max, bytes), 0)
  const allJs = walkDistFiles(distDir).filter((path) => path.endsWith('.js'))
  const asyncChunkCount = allJs.filter((path) => !closure.has(relative(distDir, path).split('\\').join('/'))).length
  return {
    entryFiles: closure.size,
    entryGzipKb: Number((total / 1024).toFixed(1)),
    largestGzipKb: Number((largest / 1024).toFixed(1)),
    asyncChunkCount,
  }
}
