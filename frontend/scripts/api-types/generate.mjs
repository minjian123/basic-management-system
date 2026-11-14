/**
 * 跨仓前端契约类型生成器（需求 01-9）：**唯一实现**，产品仓只放配置与薄壳。
 *
 * 能力（取 bms / mdm / msg 三份旧实现的并集）：
 *   1. 枚举 `<contractsDir>/*.json` 逐份生成 `<outDir>/<name>.ts`，并生成汇总导出 `index.ts`；
 *   2. `--files-from <文件|->` 增量：改动未触及判据前缀时直接跳过（预检 / CI 省时间）；
 *   3. `--check` 零漂移：缺失 / 多余生成物、逐字节差异（带首处差异行号）。
 *
 * 用法：
 *   薄壳调用（产品仓 `scripts/generate.mjs`）：`await run({ packageDir })`
 *   直接调用：`node generate.mjs --config <api-types.config.json> [--check] [--files-from <文件|->]`
 *
 * 产品差异全部来自配置文件（`<packageDir>/api-types.config.json`）：
 * `contractsDir`（仓根相对）、`outDir` / `indexFile`（包目录相对）、`header` / `index` 文案、
 * `inputs`（增量判据前缀，缺省取 contractsDir 与包目录）。
 */

import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

/** 产品配置文件（包目录内）。 */
const CONFIG_FILE = 'api-types.config.json'

/**
 * 按**调用方包目录**解析 `openapi-typescript`。
 *
 * 实现住在基座 `frontend/scripts/`，依赖却声明在各产品的 api-types 包里；从实现文件位置
 * 静态 import 会 `ERR_MODULE_NOT_FOUND`，故运行时以调用方 `package.json` 为锚点解析。
 *
 * @param packageDir api-types 包目录。
 * @returns `{ openapiTS, astToString }`。
 */
async function loadOpenapiTypescript(packageDir) {
  const requireFromPackage = createRequire(join(packageDir, 'package.json'))
  const entry = requireFromPackage.resolve('openapi-typescript')
  const loaded = await import(pathToFileURL(entry).href)
  // CJS 入口经 ESM 桥接后形态不稳定：可能是 `{default: fn}`，也可能是 `{default: {default: fn}}`
  const api = loaded.default
  const openapiTS = typeof api === 'function' ? api : api?.default
  const astToString = loaded.astToString ?? api?.astToString
  if (typeof openapiTS !== 'function' || typeof astToString !== 'function') {
    throw new TypeError(`openapi-typescript 入口形态异常：${entry}`)
  }
  return { openapiTS, astToString }
}

/**
 * 读取 JSON 文件。
 *
 * @param path 文件路径。
 * @returns 解析后的对象。
 */
function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

/**
 * 读取 `--files-from` 清单（一行一个仓根相对路径）。
 *
 * `-` 表示标准输入：提交前门禁通过管道递进来，不在仓内落临时文件。
 *
 * @param argv 参数数组。
 * @returns 清单行；未传该参数返回 null。
 */
function readChangedList(argv) {
  const index = argv.indexOf('--files-from')
  if (index < 0 || index + 1 >= argv.length) {
    return null
  }
  const source = argv[index + 1]
  const text = readFileSync(source === '-' ? 0 : source, 'utf8')
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
}

/**
 * 生成单份契约的类型文件内容。
 *
 * @param options 生成上下文。
 * @param fileName 契约文件名（如 `msg.json`）。
 * @returns 生成内容。
 */
async function generateFile(options, fileName) {
  const { config, contractsDir, openapiTS, astToString } = options
  const name = fileName.replace(/\.json$/, '')
  const schema = readJson(join(contractsDir, fileName))
  const ast = await openapiTS(schema)
  const header = [
    '/**',
    ` * ${config.header.title.replaceAll('{name}', name)}`,
    ' *',
    ` * 本文件由 \`${config.header.generator}\` 生成，请勿手工修改。`,
    ` * 来源：${config.contractsDir}/${fileName}（${config.header.sourceNote}，唯一事实源）。`,
    ` * 重新生成：${config.header.regenerateCmd}`,
    ' */',
    '',
  ].join('\n')
  return { content: `${header}${astToString(ast)}`, schema }
}

/**
 * 生成汇总导出 `index.ts`。
 *
 * @param config 产品配置。
 * @param names 契约名清单（排序）。
 * @returns 汇总文件内容。
 */
function indexContent(config, names) {
  const notes = config.index.notes ?? []
  const lines = ['/**', ` * ${config.index.title}`]
  if (notes.length > 0) {
    lines.push(' *')
    for (const note of notes) {
      lines.push(` * ${note}`)
    }
  }
  lines.push(' */', '')
  for (const name of names) {
    lines.push(config.index.exportTemplate.replaceAll('{name}', name))
  }
  lines.push('')
  return lines.join('\n')
}

/**
 * 取首个差异行（只报一处，避免整份刷屏）。
 *
 * @param expected 期望文本。
 * @param actual 实际文本。
 * @returns `{line, expected, actual}`；完全一致返回 null。
 */
function firstDiffLine(expected, actual) {
  const left = expected.split('\n')
  const right = actual.split('\n')
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    if (left[index] !== right[index]) {
      return { line: index + 1, expected: left[index] ?? '<文件末尾>', actual: right[index] ?? '<文件末尾>' }
    }
  }
  return null
}

/**
 * 执行生成 / 校验。
 *
 * @param options 选项。
 * @param options.packageDir api-types 包目录（含配置文件与产物）。
 * @param options.argv 参数数组（缺省取进程参数）。
 * @returns 退出码（0 通过 / 1 失败）。
 */
export async function run({ packageDir, argv = process.argv.slice(2) }) {
  const configPath = resolve(packageDir, CONFIG_FILE)
  if (!existsSync(configPath)) {
    console.error(`[api-types] 未找到产品配置：${configPath}`)
    return 1
  }
  const config = readJson(configPath)
  const repoRoot = resolve(packageDir, '../../..')
  const contractsDir = join(repoRoot, config.contractsDir)
  const outDir = join(packageDir, config.outDir)
  const inputs = config.inputs ?? [`${config.contractsDir}/`, 'frontend/packages/api-types/']

  const check = argv.includes('--check')
  const changed = readChangedList(argv)
  if (changed && !changed.some((rel) => inputs.some((prefix) => rel.startsWith(prefix)))) {
    console.log('[api-types] 跳过：本次改动未触及契约快照 / 类型生成物 / 契约 schema')
    return 0
  }

  const files = (await readdir(contractsDir, { withFileTypes: true }).catch(() => []))
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => entry.name)
    .sort()
  if (files.length === 0) {
    console.error(`[api-types] 未找到契约快照：${contractsDir}`)
    return 1
  }

  const names = files.map((fileName) => fileName.replace(/\.json$/, ''))
  const expected = new Map()
  const { openapiTS, astToString } = await loadOpenapiTypescript(packageDir)
  let version = ''
  for (const fileName of files) {
    const generated = await generateFile({ config, contractsDir, openapiTS, astToString }, fileName)
    expected.set(`${fileName.replace(/\.json$/, '')}.ts`, generated.content)
    version = version || String(generated.schema.info?.version ?? '')
  }
  expected.set(config.indexFile, indexContent(config, names))

  if (check) {
    const problems = []
    for (const [name, content] of expected) {
      const path = join(outDir, name)
      if (!existsSync(path)) {
        problems.push(`缺少生成物：${config.outDir}/${name}`)
        continue
      }
      const actual = await readFile(path, 'utf8')
      const diff = firstDiffLine(content, actual)
      if (diff !== null) {
        problems.push(
          `与契约快照漂移：${config.outDir}/${name} 第 ${diff.line} 行；` +
            `期望 ${JSON.stringify(diff.expected)}，实际 ${JSON.stringify(diff.actual)}`,
        )
      }
    }
    const diskFiles = (await readdir(outDir).catch(() => [])).filter((name) => name.endsWith('.ts'))
    for (const name of diskFiles) {
      if (!expected.has(name)) {
        problems.push(`多余生成物：${config.outDir}/${name}`)
      }
    }
    if (problems.length > 0) {
      for (const problem of problems) {
        console.error(`[api-types] ${problem}`)
      }
      return 1
    }
    const suffix = names.length === 1 && version ? `（info.version=${version}）` : ''
    console.log(`[api-types] 零漂移：${names.length} 份契约类型一致${suffix}`)
    return 0
  }

  await mkdir(outDir, { recursive: true })
  for (const [name, content] of expected) {
    await writeFile(join(outDir, name), content, 'utf8')
  }
  console.log(`[api-types] 已生成 ${names.length} 份契约类型 + ${config.indexFile}`)
  return 0
}

/**
 * CLI 入口（`--config <path>` 直调时用）。
 *
 * @returns 退出码。
 */
async function main() {
  const argv = process.argv.slice(2)
  const index = argv.indexOf('--config')
  if (index < 0 || index + 1 >= argv.length) {
    console.error('[api-types] 直接调用需 `--config <api-types.config.json>`；产品仓请走薄壳脚本')
    return 2
  }
  const packageDir = resolve(argv[index + 1], '..')
  return run({ packageDir, argv })
}

const invokedDirectly = process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (invokedDirectly) {
  process.exitCode = await main()
}
