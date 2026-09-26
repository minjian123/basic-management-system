/**
 * 服务契约前端类型生成器：读 `deploy/contracts/<service>.json`（快照，唯一事实源），
 * 经 `openapi-typescript` 生成 `src/<service>.ts` 与 `src/index.ts`。
 *
 * 用法：
 *   node scripts/generate.mjs           # 生成（覆盖写入）
 *   node scripts/generate.mjs --check   # 零漂移校验（重新生成并与仓库产物逐字节比对）
 */

import { existsSync } from 'node:fs'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import openapiTS, { astToString } from 'openapi-typescript'

const here = dirname(fileURLToPath(import.meta.url))
const pkgDir = resolve(here, '..')
const repoRoot = resolve(pkgDir, '../../..')
const contractsDir = join(repoRoot, 'deploy', 'contracts')
const srcDir = join(pkgDir, 'src')

/**
 * 生成文件头（统一标注「勿手改」与来源）。
 *
 * @param service 服务键。
 * @param source 快照相对路径。
 * @returns 头部注释文本。
 */
function header(service, source) {
  return [
    '/**',
    ` * 服务契约生成类型：${service}`,
    ' *',
    ' * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。',
    ` * 来源：${source}（服务契约快照，唯一事实源）。`,
    ' * 重新生成：pnpm run api-types:gen',
    ' */',
    '',
  ].join('\n')
}

/**
 * 枚举契约快照（顶层 `*.json`，排除 `baseline/` 门禁基线）。
 *
 * @returns 文件名清单（排序）。
 */
async function listContracts() {
  const entries = await readdir(contractsDir, { withFileTypes: true })
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => entry.name)
    .sort()
}

/**
 * 生成单服务类型文件内容。
 *
 * @param fileName 快照文件名（如 `platform.json`）。
 * @returns 生成内容。
 */
async function generateFile(fileName) {
  const service = fileName.replace(/\.json$/, '')
  const schema = JSON.parse(await readFile(join(contractsDir, fileName), 'utf8'))
  const ast = await openapiTS(schema)
  return `${header(service, `deploy/contracts/${fileName}`)}${astToString(ast)}`
}

/**
 * 生成 `index.ts`（按服务命名空间导出）。
 *
 * @param services 服务键清单（排序）。
 * @returns 生成内容。
 */
function indexContent(services) {
  const lines = [
    '/**',
    ' * 服务契约生成类型汇总（由 scripts/generate.mjs 生成，勿手改）。',
    ' *',
    ' * 按服务命名空间导出：`import type { platform } from "@bms/api-types"`。',
    ' */',
    '',
  ]
  for (const service of services) {
    lines.push(`export type * as ${service} from './${service}'`)
  }
  lines.push('')
  return lines.join('\n')
}

async function main() {
  const check = process.argv.includes('--check')
  const contracts = await listContracts()
  if (contracts.length === 0) {
    console.error(`[api-types] 未找到契约快照：${contractsDir}`)
    process.exitCode = 1
    return
  }
  const services = contracts.map((fileName) => fileName.replace(/\.json$/, ''))
  const expected = new Map()
  for (const fileName of contracts) {
    expected.set(`${fileName.replace(/\.json$/, '')}.ts`, await generateFile(fileName))
  }
  expected.set('index.ts', indexContent(services))

  if (check) {
    const problems = []
    for (const [name, content] of expected) {
      const path = join(srcDir, name)
      if (!existsSync(path)) {
        problems.push(`缺少生成文件：src/${name}`)
        continue
      }
      if ((await readFile(path, 'utf8')) !== content) {
        problems.push(`与快照漂移：src/${name}（重新生成：pnpm run api-types:gen）`)
      }
    }
    const diskFiles = (await readdir(srcDir).catch(() => [])).filter((name) => name.endsWith('.ts'))
    for (const name of diskFiles) {
      if (!expected.has(name)) {
        problems.push(`多余生成文件：src/${name}`)
      }
    }
    if (problems.length > 0) {
      for (const problem of problems) {
        console.error(`[api-types] ${problem}`)
      }
      process.exitCode = 1
      return
    }
    console.log(`[api-types] 零漂移：${services.length} 份服务契约类型一致`)
    return
  }

  await mkdir(srcDir, { recursive: true })
  for (const [name, content] of expected) {
    await writeFile(join(srcDir, name), content, 'utf8')
  }
  console.log(`[api-types] 已生成 ${services.length} 份服务契约类型 + index.ts`)
}

await main()
