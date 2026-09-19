#!/usr/bin/env node
/**
 * 前端首屏体积预算校验（零依赖，CI 与本地同口径）。
 *
 * 口径：**只统计首屏入口块**——解析 `dist/index.html` 静态引用的 js / css
 * （`<script type="module">` / `<link rel="modulepreload">` / `<link rel="stylesheet">`），
 * 对其 gzip 体积求和与取最大值，和 `budget.json` 的上限比较；超限退出码 1（CI 红）。
 *
 * 路由级 / 组件级 **异步块**（如 `vendor-echarts`）由 `import()` 按需加载，**不计入首屏预算**，
 * 仅打印观察值。上限口径：初次落地取「当前基线 + 20%」，因需求增长需要放宽时，
 * 在 PR 中同步调整 budget.json 并说明原因。
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

// 解析入口块：index.html 静态引用的 js / css（异步块不在其中）。
const html = readFileSync(join(distDir, 'index.html'), 'utf8')
const entryRel = new Set()
for (const match of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)) {
  const url = match[1]
  if (/^https?:/.test(url)) continue
  entryRel.add(url.replace(/^\//, ''))
}
if (entryRel.size === 0) {
  console.error('[budget] 未从 index.html 解析到入口块（js/css）')
  exit(1)
}

const measure = (path) => ({ path: relative(root, path), gzip: gzipSync(readFileSync(path)).length })
const entry = files.filter((path) => entryRel.has(relative(distDir, path).split('\\').join('/'))).map(measure)
const asyncFiles = files.filter((path) => !entryRel.has(relative(distDir, path).split('\\').join('/'))).map(measure)

const total = entry.reduce((sum, item) => sum + item.gzip, 0)
const largest = entry.reduce((max, item) => Math.max(max, item.gzip), 0)
const kb = (bytes) => (bytes / 1024).toFixed(1)

console.log(`[budget] 首屏入口块 ${entry.length} 个（gzip）：`)
for (const item of [...entry].sort((a, b) => b.gzip - a.gzip)) {
  console.log(`  ${kb(item.gzip).padStart(7)} KB  ${item.path}`)
}
console.log(`[budget] 异步块 ${asyncFiles.length} 个（不计入首屏预算）：`)
for (const item of [...asyncFiles].sort((a, b) => b.gzip - a.gzip).slice(0, 5)) {
  console.log(`  ${kb(item.gzip).padStart(7)} KB  ${item.path}`)
}

const problems = []
if (total > budget.totalGzipKb * 1024) {
  problems.push(`首屏合计 ${kb(total)} KB 超预算 ${budget.totalGzipKb} KB`)
}
if (largest > budget.largestGzipKb * 1024) {
  problems.push(`首屏最大单文件 ${kb(largest)} KB 超预算 ${budget.largestGzipKb} KB`)
}

if (problems.length) {
  console.error(`[budget] 不通过：${problems.join('；')}`)
  console.error('[budget] 如需放宽预算，请在 budget.json 调整并说明原因（评审可见）。')
  exit(1)
}
console.log(
  `[budget] 通过：首屏合计 ${kb(total)} KB（预算 ${budget.totalGzipKb} KB），` +
    `首屏最大单文件 ${kb(largest)} KB（预算 ${budget.largestGzipKb} KB）`,
)
