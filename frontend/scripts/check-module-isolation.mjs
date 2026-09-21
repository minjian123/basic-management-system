#!/usr/bin/env node
/**
 * 模块隔离扫描（零依赖；源码面 + 产物面；平台侧护栏，本地与 CI 同口径）。
 *
 * 依据《前端开发规范》「运行时模块隔离（强制）」节与任务 03_01 详细设计 §3.2 / §3.3：
 *   - **源码面**：模块工程 `frontend/modules/<模块名>/src/**` 与宿主内构建期合并模块目录
 *     `frontend/apps/desktop/src/modules/**`——样式作用域 / 令牌消费 / 全局污染五类 / 运行时约束；
 *     独立预览壳（`standalone.ts`）与令牌定义源（`tokens.scss`）豁免；
 *   - **产物面**：模块远端产物 `frontend/modules/<模块名>/dist/**`——全部 CSS（选择器须作用域化、
 *     禁全局选择器、禁硬编码色值）与**模块自有 JS 块**（暴露块 + 页面块；全局污染与持久化特征）；
 *     MF 运行时 / 平台辅助块 / 第三方依赖块不在扫描面（避免误报）。
 *
 * 用法：
 *     node frontend/scripts/check-module-isolation.mjs                    # 源码面（缺省）
 *     node frontend/scripts/check-module-isolation.mjs --product          # 产物面（须先构建）
 *     node frontend/scripts/check-module-isolation.mjs --module frontend/modules/demo
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { basename, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exit } from 'node:process'

/**
 * `frontend/` 目录（本文件位于 `frontend/scripts/`）。
 *
 * Node 直跑按脚本位置推断；经 Vite / Vitest 载入时 `import.meta.url` 非 `file:` 协议，
 * 回退按测试工程目录（`apps/desktop` / `modules/<模块名>` 均为 `frontend/` 下两级）推断；
 * 测试与调用方亦可显式传入目录（导出函数首参）。
 */
const FRONTEND_DIR = (() => {
  if (import.meta.url.startsWith('file:')) return resolve(fileURLToPath(import.meta.url), '..', '..')
  return resolve(process.cwd(), '..', '..')
})()

/** 源码扫描扩展名。 */
const SOURCE_EXTENSIONS = ['.ts', '.mts', '.vue', '.js', '.mjs', '.scss', '.css']

/** 样式文件扩展名（`.vue` 的 `<style>` 块另取）。 */
const STYLE_FILE_EXTENSIONS = ['.scss', '.css']

/** 源码豁免文件（独立预览壳 / 令牌定义源）。 */
const SOURCE_EXEMPT_FILES = ['standalone.ts', 'tokens.scss']

/** 规则判据（去注释后匹配）。 */
const PATTERNS = {
  /** G1 全局原型改写（含 `__proto__`）。 */
  prototype: /(Object|Array|String|Number|Boolean|Function|Symbol)\s*\.\s*prototype|__proto__/,
  /** G2 全局事件挂接。 */
  globalEvent: /\b(window|document|globalThis|self)\s*\.\s*addEventListener\s*\(/,
  /** G3 全局变量赋值（属性链赋值如 `window.location.href =` 不在此列）。 */
  globalAssign: /\b(window|globalThis|self)\s*\.\s*[A-Za-z_$][\w$]*\s*=(?!=)/,
  /** G4 根节点直控。 */
  documentRoot: /document\s*\.\s*(documentElement|body)\b/,
  /** R1 自建宿主级实例。 */
  hostInstance: /\b(createPinia|createRouter)\s*\(/,
  /** R2 持久化 API。 */
  persist: /\b(localStorage|sessionStorage)\b|document\s*\.\s*cookie\b/,
  /** S2 `:global`。 */
  globalFlag: /:global/,
  /** S3 全局选择器（选择器段以 `:root` / `html` / `body` / `*` 起始）。 */
  globalSelector: /(^|[,{}])\s*(:root|html|body|\*)\s*[,{]/,
  /** S4 脚本引全局样式（`?inline` 除外，见 `hasStyleImport`）。 */
  styleImport: /import\s+(?:[^'"]*from\s+)?['"]([^'"]+\.(?:css|scss|sass|less))(?:\?[^'"]*)?['"]/g,
  /** S5 / P3 色值字面量。 */
  colorLiteral: /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(/,
}

/** 色值豁免：动态计算值（与既有 `guard-tokens` 同口径）。 */
const COLOR_ALLOWED = [/hsl\(\$\{/, /rgb\(\$\{/]

/**
 * 去注释（块注释 + 行注释；行注释避开 `://` 协议串）。
 *
 * @param source 源码。
 * @returns 去注释后的源码。
 */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:/])\/\/[^\n]*/g, '$1')
}

/**
 * 递归收集指定扩展名的文件。
 *
 * @param dir 目录。
 * @param extensions 扩展名清单。
 * @returns 文件绝对路径清单。
 */
function walkFiles(dir, extensions) {
  const result = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) result.push(...walkFiles(path, extensions))
    else if (extensions.some((extension) => path.endsWith(extension))) result.push(path)
  }
  return result
}

/**
 * `.vue` 的 `<style>` 标签清单。
 *
 * @param source 源码。
 * @returns 标签串清单。
 */
function styleTagsOf(source) {
  return [...source.matchAll(/<style[^>]*>/gi)].map((match) => match[0])
}

/**
 * `.vue` 的 `<style>` 块内容清单。
 *
 * @param source 源码。
 * @returns 样式内容清单。
 */
function styleBlocksOf(source) {
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1])
}

/**
 * 是否引入样式文件（`?inline` 除外）。
 *
 * @param source 源码。
 * @returns 是否命中。
 */
function hasStyleImport(source) {
  for (const match of source.matchAll(PATTERNS.styleImport)) {
    if (!match[0].includes('?inline')) return true
  }
  return false
}

/**
 * 提取 CSS 规则的选择器（跳过多层 `@` 前奏与关键帧步进）。
 *
 * @param source 压缩或未压缩 CSS。
 * @returns 选择器段清单。
 */
function cssSelectors(source) {
  const selectors = []
  let start = 0
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (char === '{') {
      const prelude = source.slice(start, index).trim()
      if (prelude.length > 0 && !prelude.startsWith('@') && !/^(from|to|\d+(\.\d+)?%)$/.test(prelude)) {
        for (const part of prelude.split(',')) {
          if (part.trim().length > 0) selectors.push(part.trim())
        }
      }
      start = index + 1
    } else if (char === '}' || char === ';') {
      start = index + 1
    }
  }
  return selectors
}

/**
 * 收集模块工程源码文件。
 *
 * @param frontendDir `frontend/` 目录（缺省按脚本位置推断）。
 * @returns 待检文件清单（展示路径相对 `frontend/`）。
 */
export function collectModuleSourceFiles(frontendDir = FRONTEND_DIR) {
  const targets = []
  for (const moduleDir of listModuleDirs(frontendDir)) {
    targets.push(...sourceFilesOf(join(moduleDir, 'src'), frontendDir))
  }
  const localModules = join(frontendDir, 'apps/desktop/src/modules')
  if (existsSync(localModules)) targets.push(...sourceFilesOf(localModules, frontendDir))
  return targets
}

/**
 * 收集目录下源码文件（目录不存在返回空）。
 *
 * @param dir 目录。
 * @param root 展示路径基准。
 * @returns 待检文件清单。
 */
function sourceFilesOf(dir, root) {
  if (!existsSync(dir)) return []
  return walkFiles(dir, SOURCE_EXTENSIONS).map((path) => ({
    path: relative(root, path).split('\\').join('/'),
    source: readFileSync(path, 'utf8'),
  }))
}

/**
 * 模块工程目录清单（`frontend/modules/*`，含 `package.json` 者）。
 *
 * @param frontendDir `frontend/` 目录。
 * @returns 模块工程目录清单。
 */
export function listModuleDirs(frontendDir = FRONTEND_DIR) {
  const modulesDir = join(frontendDir, 'modules')
  if (!existsSync(modulesDir)) return []
  return readdirSync(modulesDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && existsSync(join(modulesDir, entry.name, 'package.json')))
    .map((entry) => join(modulesDir, entry.name))
    .sort()
}

/**
 * 扫描一组源码文件（纯函数，供 fixture 断言）。
 *
 * @param files 待检文件清单。
 * @returns 违规项（空数组为通过）。
 */
export function scanSourceFiles(files) {
  const problems = []
  for (const file of files) {
    if (SOURCE_EXEMPT_FILES.includes(basename(file.path))) continue
    const source = stripComments(file.source)
    const isVue = file.path.endsWith('.vue')
    const isStyleFile = STYLE_FILE_EXTENSIONS.some((extension) => file.path.endsWith(extension))

    if (isVue) {
      for (const tag of styleTagsOf(source)) {
        if (!/\bscoped\b/.test(tag)) problems.push(`${file.path}：<style> 未 scoped（S1）`)
      }
    }

    const styleText = isVue ? styleBlocksOf(source).join('\n') : isStyleFile ? source : ''
    if (styleText.length > 0) {
      if (PATTERNS.globalFlag.test(styleText)) problems.push(`${file.path}：样式使用 :global（S2）`)
      const selector = styleText.match(PATTERNS.globalSelector)
      if (selector !== null) problems.push(`${file.path}：全局样式选择器 ${selector[2]}（S3）`)
      const color = styleText.match(PATTERNS.colorLiteral)
      if (color !== null && !COLOR_ALLOWED.some((pattern) => pattern.test(styleText))) {
        problems.push(`${file.path}：硬编码色值 ${color[0]}（S5）`)
      }
    }

    if (!isStyleFile) {
      if (PATTERNS.prototype.test(source)) problems.push(`${file.path}：改全局原型（G1）`)
      if (PATTERNS.globalEvent.test(source)) problems.push(`${file.path}：挂全局事件（G2）`)
      if (PATTERNS.globalAssign.test(source)) problems.push(`${file.path}：改全局变量（G3）`)
      if (PATTERNS.documentRoot.test(source)) problems.push(`${file.path}：直控根节点（G4）`)
      if (PATTERNS.hostInstance.test(source)) problems.push(`${file.path}：自建宿主级实例（R1）`)
      if (PATTERNS.persist.test(source)) problems.push(`${file.path}：使用持久化 API（R2）`)
      if (hasStyleImport(source)) problems.push(`${file.path}：脚本引全局样式（S4）`)
    }
  }
  return problems
}

/**
 * 收集单个模块工程的远端产物扫描目标（CSS 全部 + 模块自有 JS 块）。
 *
 * @param moduleDir 模块工程目录。
 * @returns `{ css, js }` 待检文件清单。
 */
export function collectProductTargets(moduleDir) {
  const distDir = join(moduleDir, 'dist')
  if (!existsSync(distDir)) {
    throw new Error(`模块产物目录不存在：${distDir}（请先构建：npm run build）`)
  }
  const files = walkFiles(distDir, ['.js', '.css'])
  const display = (path) => relative(moduleDir, path).split('\\').join('/')
  const distName = (path) => relative(distDir, path).split('\\').join('/')
  const toFile = (path) => ({ path: display(path), source: readFileSync(path, 'utf8') })

  const remoteEntry = files.find((path) => distName(path) === 'remoteEntry.js')
  if (remoteEntry === undefined) {
    throw new Error(`缺少远端容器入口 remoteEntry.js：${distDir}（产物形态与模块契约不符）`)
  }
  const budgetPath = join(moduleDir, 'budget.json')
  if (!existsSync(budgetPath)) {
    throw new Error(`缺少模块预算配置 budget.json：${budgetPath}（无法识别模块页面块）`)
  }
  const budget = JSON.parse(readFileSync(budgetPath, 'utf8'))
  const hints = budget.pageChunkHints ?? []
  if (hints.length === 0) {
    throw new Error(`budget.json 缺少 pageChunkHints：${budgetPath}（无法识别模块页面块）`)
  }

  const exposeRefs = new Set()
  for (const match of readFileSync(remoteEntry, 'utf8').matchAll(
    /\bimport\s*\(\s*["'`]([^"'`\s]+\.(?:js|css))["'`]\s*\)/g,
  )) {
    exposeRefs.add(match[1].replace(/^\.?\//, '').split('?')[0])
  }
  const expose = files.filter(
    (path) => path.endsWith('.js') && exposeRefs.has(distName(path)) && !distName(path).includes('_virtual_mf-'),
  )
  const pages = files.filter((path) => path.endsWith('.js') && hints.some((hint) => distName(path).includes(hint)))
  return { css: files.filter((path) => path.endsWith('.css')).map(toFile), js: [...expose, ...pages].map(toFile) }
}

/**
 * 扫描一组产物文件（纯函数，供 fixture 断言）。
 *
 * @param input `{ css, js }` 待检文件清单。
 * @returns 违规项（空数组为通过）。
 */
export function scanProductFiles({ css = [], js = [] }) {
  const problems = []
  for (const file of css) {
    const source = stripComments(file.source)
    for (const selector of cssSelectors(source)) {
      if (!selector.includes('[data-v-')) problems.push(`${file.path}：选择器未作用域化（P1）${selector}`)
      const global = selector.match(/^\s*(:root|html|body|\*)\b/)
      if (global !== null) problems.push(`${file.path}：全局样式选择器 ${global[1]}（P2）`)
    }
    const color = source.match(PATTERNS.colorLiteral)
    if (color !== null && !COLOR_ALLOWED.some((pattern) => pattern.test(source))) {
      problems.push(`${file.path}：硬编码色值 ${color[0]}（P3）`)
    }
  }
  for (const file of js) {
    const source = stripComments(file.source)
    if (PATTERNS.prototype.test(source)) problems.push(`${file.path}：改全局原型（P4/G1）`)
    if (PATTERNS.globalEvent.test(source)) problems.push(`${file.path}：挂全局事件（P4/G2）`)
    if (PATTERNS.globalAssign.test(source)) problems.push(`${file.path}：改全局变量（P4/G3）`)
    if (PATTERNS.documentRoot.test(source)) problems.push(`${file.path}：直控根节点（P4/G4）`)
    if (PATTERNS.persist.test(source)) problems.push(`${file.path}：使用持久化 API（P4/R2）`)
  }
  return problems
}

/**
 * 收集并扫描全部模块源码（模块工程 + 宿主构建期合并模块目录）。
 *
 * @param frontendDir `frontend/` 目录。
 * @returns 违规项（空数组为通过）。
 */
export function scanModuleSources(frontendDir = FRONTEND_DIR) {
  return scanSourceFiles(collectModuleSourceFiles(frontendDir))
}

/**
 * 收集并扫描全部模块远端产物（无任何产物目录即抛错）。
 *
 * @param frontendDir `frontend/` 目录。
 * @returns 违规项（空数组为通过）。
 */
export function scanModuleProducts(frontendDir = FRONTEND_DIR) {
  const moduleDirs = listModuleDirs(frontendDir).filter((dir) => existsSync(join(dir, 'dist')))
  if (moduleDirs.length === 0) {
    throw new Error('未找到任何模块产物目录（frontend/modules/*/dist）；请先构建模块')
  }
  const problems = []
  for (const moduleDir of moduleDirs) problems.push(...scanProductFiles(collectProductTargets(moduleDir)))
  return problems
}

/**
 * 源码面扫描（CLI）。
 *
 * @param moduleDir 指定模块工程目录（缺省扫全部）。
 * @returns 违规项。
 */
function runSourceScan(moduleDir) {
  const files =
    moduleDir !== undefined
      ? sourceFilesOf(join(moduleDir, 'src'), FRONTEND_DIR)
      : collectModuleSourceFiles(FRONTEND_DIR)
  console.log(`[module-isolation] 源码面扫描 ${files.length} 个文件`)
  return scanSourceFiles(files)
}

/**
 * 产物面扫描（CLI；缺产物目录即抛错，不静默跳过）。
 *
 * @param moduleDir 指定模块工程目录（缺省扫全部）。
 * @returns 违规项。
 */
function runProductScan(moduleDir) {
  const moduleDirs = moduleDir !== undefined ? [moduleDir] : listModuleDirs(FRONTEND_DIR)
  const missing = moduleDirs.filter((dir) => !existsSync(join(dir, 'dist')))
  if (missing.length > 0) {
    throw new Error(`模块产物目录不存在：${missing.join('、')}（请先构建：npm run build）`)
  }
  const problems = []
  let cssCount = 0
  let jsCount = 0
  for (const dir of moduleDirs) {
    const targets = collectProductTargets(dir)
    cssCount += targets.css.length
    jsCount += targets.js.length
    problems.push(...scanProductFiles(targets))
  }
  console.log(`[module-isolation] 产物面扫描 CSS ${cssCount} 个 / 模块自有 JS 块 ${jsCount} 个`)
  return problems
}

/**
 * CLI 入口。
 *
 * @param argv 进程参数。
 */
function main(argv) {
  const args = argv.slice(2)
  const productMode = args.includes('--product')
  const moduleIndex = args.indexOf('--module')
  const moduleDir = moduleIndex >= 0 ? resolve(args[moduleIndex + 1]) : undefined
  try {
    const problems = productMode ? runProductScan(moduleDir) : runSourceScan(moduleDir)
    if (problems.length > 0) {
      console.error(`[module-isolation] 不通过（${problems.length} 项）：`)
      for (const problem of problems) console.error(`  - ${problem}`)
      exit(1)
    }
    console.log(`[module-isolation] 通过：${productMode ? '产物面' : '源码面'}隔离零违规`)
  } catch (error) {
    console.error(`[module-isolation] 不通过：${error instanceof Error ? error.message : String(error)}`)
    exit(1)
  }
}

if (
  import.meta.url.startsWith('file:') &&
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main(process.argv)
}
