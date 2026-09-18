#!/usr/bin/env node
/**
 * 前端构建体积预算校验（零依赖，CI 与本地同口径）。
 *
 * 统计 `dist/` 下 js / css 产物的 gzip 体积，与 `budget.json` 中的上限比较；
 * 超限退出码 1（CI 红）。上限口径：初次落地取「当前基线 + 20%」，
 * 因需求增长需要放宽时，在 PR 中同步调整 budget.json 并说明原因。
 *
 * 用法：
 *     npm run build && npm run budget
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { exit } from 'node:process'

const root = fileURLToPath(new URL('..', import.meta.url))
const budget = JSON.parse(readFileSync(join(root, 'budget.json'), 'utf8'))
const distDir = join(root, budget.distDir ?? 'dist')

function walk(dir) {
  const files = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...walk(path))
    else if (/\.(js|css)$/.test(entry.name)) files.push(path)
  }
  return files
}

let files
try {
  files = walk(distDir)
} catch {
  console.error(`[budget] 未找到构建产物目录：${distDir}（请先执行 npm run build）`)
  exit(1)
}

const measured = files
  .map((path) => ({ path: relative(root, path), gzip: gzipSync(readFileSync(path)).length }))
  .sort((a, b) => b.gzip - a.gzip)

const total = measured.reduce((sum, item) => sum + item.gzip, 0)
const largest = measured[0]?.gzip ?? 0
const kb = (bytes) => (bytes / 1024).toFixed(1)

console.log(`[budget] 统计 ${measured.length} 个 js/css 产物（gzip）：`)
for (const item of measured.slice(0, 5)) {
  console.log(`  ${kb(item.gzip).padStart(7)} KB  ${item.path}`)
}
if (measured.length > 5) console.log(`  ...（其余 ${measured.length - 5} 个）`)

const problems = []
if (total > budget.totalGzipKb * 1024) {
  problems.push(`合计 ${kb(total)} KB 超预算 ${budget.totalGzipKb} KB`)
}
if (largest > budget.largestGzipKb * 1024) {
  problems.push(`最大单文件 ${kb(largest)} KB 超预算 ${budget.largestGzipKb} KB`)
}

if (problems.length) {
  console.error(`[budget] 不通过：${problems.join('；')}`)
  console.error('[budget] 如需放宽预算，请在 budget.json 调整并说明原因（评审可见）。')
  exit(1)
}
console.log(
  `[budget] 通过：合计 ${kb(total)} KB（预算 ${budget.totalGzipKb} KB），` +
    `最大单文件 ${kb(largest)} KB（预算 ${budget.largestGzipKb} KB）`,
)
