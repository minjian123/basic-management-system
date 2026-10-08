#!/usr/bin/env node
/**
 * 共享依赖产物级断言（**构建期**，零依赖；挂 CI `shared-deps-check`）。
 *
 * 判据全部取自 Module Federation **构建产物中生成的共享声明块**（`_virtual_mf-localSharedImportMap*.js`）——
 * 它是「本侧实际声明了什么、是否提供本地实现」的权威记录，不依赖压缩后的字符串启发式：
 *
 *   1. **共享面一致**：宿主与模块声明的共享项名字集合相同，且等于单一来源 `shared` 的键集合；
 *   2. **版本要求一致**：两侧每项 `requiredVersion` 相同，且等于单一来源；
 *   3. **宿主为提供方**：宿主侧声明**不得**带 `import: false`（须打包并提供实例）；
 *   4. **模块为消费方**：模块侧每项必须 `import: false` + `strictVersion: true`，
 *      且本地取值函数直接抛「must be provided by host」——**产物中不存在第二份实现**；
 *   5. **依赖实例数 = 1**：按上述口径统计每个共享依赖的**提供方份数**（宿主 1 + 模块 0），恒等于 1。
 *
 * **遍历口径（2026-10-08，任务 03_04）**：宿主 × **每个在册仓内模块**（`frontend/modules/＜模块名＞/dist`），
 * 逐模块断言并在失败信息中带模块名；跨仓（产品独立仓库）模块的共享断言在**发布时**经同一强校验执行
 * （平台 CI 不访问仓外产物），不在本护栏范围。
 *
 * 用法（需先构建产物）：
 *     cd frontend/apps/desktop && pnpm run build
 *     cd frontend/modules/<模块名> && pnpm run build
 *     node frontend/scripts/check-shared-deps.mjs
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exit } from 'node:process'

import { listModuleDirs } from './check-module-isolation.mjs'
import { readSharedSource } from './shared-deps.mjs'

/**
 * `frontend/` 目录（本文件位于 `frontend/scripts/`）。
 *
 * Node 直跑按脚本位置推断；经 Vite / Vitest 载入时 `import.meta.url` 非 `file:` 协议，
 * 回退按测试工程目录（`apps/desktop` / `modules/<模块名>` 均为 `frontend/` 下两级）推断；
 * 调用方亦可显式传入目录（导出函数选项）。
 */
const FRONTEND_DIR = (() => {
  if (import.meta.url.startsWith('file:')) return resolve(fileURLToPath(import.meta.url), '..', '..')
  return resolve(process.cwd(), '..', '..')
})()

/** 模块侧「必须由宿主提供」的本地取值函数特征（Module Federation 生成）。 */
const HOST_REQUIRED_MARKER = 'must be provided by host'

/**
 * 读取指定产物目录中的共享声明块文本。
 *
 * @param distDir 产物目录。
 * @returns 声明块文本（未找到返回 `undefined`）。
 */
function readDeclarationText(distDir) {
  const assetsDir = join(distDir, 'assets')
  if (!existsSync(assetsDir)) return undefined
  const name = readdirSync(assetsDir).find((file) => file.startsWith('_virtual_mf-localSharedImportMap'))
  if (name === undefined) return undefined
  return readFileSync(join(assetsDir, name), 'utf8')
}

/**
 * 解析宿主侧声明（形如 `` vue:{name:`vue`,version:`3.5.43`,...,shareConfig:{singleton:!0,requiredVersion:`^3.5.41`,...}} ``）。
 *
 * @param text 声明块文本。
 * @returns 包名 → `{ version, requiredVersion, providesLocal }`。
 */
function parseHostDeclarations(text) {
  const result = {}
  const pattern = /(\S+?):\{name:`([^`]*)`,version:`([^`]*)`[\s\S]*?shareConfig:\{([^}]*)\}/g
  for (const match of text.matchAll(pattern)) {
    const [, key, name, version, config] = match
    result[name] = {
      key,
      version,
      requiredVersion: /requiredVersion:`([^`]*)`/.exec(config)?.[1],
      providesLocal: !/import:!1/.test(config),
    }
  }
  return result
}

/**
 * 解析模块侧声明（形如 `` vue:t(`vue`,`3.5.43`,`default`,!0,{singleton:!0,requiredVersion:`^3.5.41`,strictVersion:!0,eager:!1}) ``）。
 *
 * @param text 声明块文本。
 * @param names 单一来源共享面（包名清单）。
 * @returns 包名 → `{ version, requiredVersion, noLocalImport, strictVersion }`。
 */
function parseRemoteDeclarations(text, names) {
  const result = {}
  // 消费方形态由生成器统一附加 `import: !1`（模块级，见函数体上方的取值函数 helper）
  const noLocalImport = /import:!1/.test(text)
  for (const name of names) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const pattern = new RegExp(':t\\(`' + escaped + '`,`([^`]*)`,`[^`]*`,(![01]),\\{([^}]*)\\}\\)')
    const match = pattern.exec(text)
    if (match === null) continue
    const [, version, , config] = match
    result[name] = {
      version,
      requiredVersion: /requiredVersion:`([^`]*)`/.exec(config)?.[1],
      strictVersion: /strictVersion:!0/.test(config),
      noLocalImport,
    }
  }
  return result
}

/**
 * 模块产物目录清单（`frontend/modules/＜模块名＞/dist`，仅含已构建者）。
 *
 * @param frontendDir `frontend/` 目录。
 * @returns 产物目录清单。
 */
function moduleDistDirs(frontendDir) {
  return listModuleDirs(frontendDir)
    .map((dir) => join(dir, 'dist'))
    .filter((dir) => existsSync(dir))
}

/**
 * 共享依赖产物级断言（纯函数，供 CLI 与用例复用）。
 *
 * @param options 选项：`frontendDir`（`frontend/` 目录；缺省按脚本位置推断）。
 * @returns `{ problems, sharedNames, moduleNames }`（`problems` 空数组即通过）。
 */
export function checkSharedDeps(options = {}) {
  const frontendDir = resolve(options.frontendDir ?? FRONTEND_DIR)
  const hostDist = join(frontendDir, 'apps/desktop/dist')
  const problems = []

  if (!existsSync(hostDist)) {
    problems.push(`宿主产物目录不存在：${hostDist}（请先构建：cd frontend/apps/desktop && pnpm run build）`)
  }
  const moduleDists = moduleDistDirs(frontendDir)
  if (moduleDists.length === 0) {
    problems.push(
      `未找到任何模块产物目录：${join(frontendDir, 'modules')}/*/dist（请先构建模块；跨仓模块由发布时强校验承担，不在本护栏范围）`,
    )
  }
  if (problems.length > 0) {
    return { problems, sharedNames: [], moduleNames: [] }
  }

  const source = readSharedSource({ root: frontendDir })
  const sharedNames = Object.keys(source.shared ?? {}).sort()
  const hostText = readDeclarationText(hostDist)
  if (hostText === undefined) {
    problems.push('宿主产物中未找到共享声明块（_virtual_mf-localSharedImportMap*），请确认 Module Federation 插件已参与构建')
    return { problems, sharedNames, moduleNames: moduleDists.map((dir) => basename(dirname(dir))) }
  }
  const hostDeclared = parseHostDeclarations(hostText)

  // 1 宿主共享面一致
  const hostNames = Object.keys(hostDeclared).sort()
  if (hostNames.join(',') !== sharedNames.join(',')) {
    problems.push(`宿主共享面与单一来源不一致：产物 [${hostNames.join(', ')}] ≠ 单一来源 [${sharedNames.join(', ')}]`)
  }

  // 2 宿主侧版本要求一致 + 3 宿主为提供方
  for (const name of sharedNames) {
    const expected = source.shared[name].requiredVersion
    const host = hostDeclared[name]
    if (host !== undefined && host.requiredVersion !== expected) {
      problems.push(`宿主 ${name} 的 requiredVersion 与单一来源不一致：${String(host.requiredVersion)} ≠ ${expected}`)
    }
    if (host !== undefined && !host.providesLocal) {
      problems.push(`宿主 ${name} 被声明为 import:false（宿主是提供方，须打包并提供实例）`)
    }
  }

  // 4 / 5 逐模块断言（共享面 / 版本要求 / 消费方形态 / 本地回退 / 实例数）
  const moduleNames = []
  for (const distDir of moduleDists) {
    const moduleName = basename(dirname(distDir))
    moduleNames.push(moduleName)
    const label = `模块 ${moduleName}`
    const remoteText = readDeclarationText(distDir)
    if (remoteText === undefined) {
      problems.push(`${label}：产物中未找到共享声明块（_virtual_mf-localSharedImportMap*）`)
      continue
    }
    const remoteDeclared = parseRemoteDeclarations(remoteText, sharedNames)
    const remoteNames = Object.keys(remoteDeclared).sort()
    if (remoteNames.join(',') !== sharedNames.join(',')) {
      problems.push(
        `${label} 共享面与单一来源不一致：产物 [${remoteNames.join(', ')}] ≠ 单一来源 [${sharedNames.join(', ')}]`,
      )
    }
    for (const name of sharedNames) {
      const expected = source.shared[name].requiredVersion
      const remote = remoteDeclared[name]
      if (remote !== undefined && remote.requiredVersion !== expected) {
        problems.push(
          `${label} ${name} 的 requiredVersion 与单一来源不一致：${String(remote.requiredVersion)} ≠ ${expected}`,
        )
      }
      if (remote !== undefined && !remote.strictVersion) {
        problems.push(`${label} ${name} 未声明 strictVersion（版本不满足须拒绝加载）`)
      }
      const hostProvides = hostDeclared[name]?.providesLocal === true ? 1 : 0
      const remoteProvides = remoteDeclared[name]?.noLocalImport === true ? 0 : 1
      const providers = hostProvides + remoteProvides
      if (providers !== 1) {
        problems.push(`${label}：共享依赖 ${name} 的提供方份数为 ${providers}（应为 1：宿主提供、模块不提供）`)
      }
    }
    if (!remoteText.includes(HOST_REQUIRED_MARKER)) {
      problems.push(`${label}：产物未体现「共享依赖必须由宿主提供」的取值语义（本地回退可能仍存在）`)
    }
    if (!/import:!1/.test(remoteText)) {
      problems.push(`${label}：产物未声明 import:false（存在打包本地回退副本的风险）`)
    }
  }

  return { problems, sharedNames, moduleNames }
}

/**
 * CLI 入口。
 *
 * @param argv 进程参数。
 */
function main(argv) {
  const rootIndex = argv.indexOf('--root')
  const frontendDir = rootIndex >= 0 ? resolve(argv[rootIndex + 1]) : undefined
  const { problems, sharedNames, moduleNames } = checkSharedDeps({ frontendDir })
  if (problems.length > 0) {
    console.error(`[shared-deps] 不通过：${problems.join('；')}`)
    exit(1)
  }
  console.log(
    `[shared-deps] 通过：共享面 ${sharedNames.join(' / ')}；宿主为提供方、模块 ${moduleNames.join(' / ')} import:false + strictVersion；` +
      `依赖实例数 = 1（提供方份数：宿主 1 / 模块 0）`,
  )
}

if (
  import.meta.url.startsWith('file:') &&
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main(process.argv)
}
