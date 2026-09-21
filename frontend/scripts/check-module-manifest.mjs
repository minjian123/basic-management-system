#!/usr/bin/env node
/**
 * 清单 / 版本发现 / 契约用例齐备护栏（零依赖；挂 `module-build`，本地可复跑）。
 *
 * 断言（见任务 03_02 详细设计 §3.8）：
 *   1. **清单可解析**：严格解析零拒绝（口径与 core 一致，一致性由宿主用例以 fixture 对照断言）；
 *   2. **远端条目版本化**：`mode: remote` 条目 `entry` 匹配 `<基址>/<名称>/<版本>/remoteEntry.js`，
 *      且路径版本 = 条目 `version`（清单是加载与回滚的唯一来源，指向版本目录）；
 *   3. **本地条目可解析**：`mode: local` 条目 `entry` 对应宿主本地入口表（`apps/desktop/src/modules/<entry>/index.ts` 存在）；
 *   4. **版本发现**：模块工程存在时 `package.json` 版本 = 条目版本；`dist/` 存在时产物元数据
 *      （名称 / 版本 / 契约版本）与工程、平台一致；
 *   5. **契约用例齐备**：每个模块工程 `tests/module-contract.spec.ts` 存在且引用 `describeModuleContract`
 *      （「全部注册实现跑同一套断言」的发现性保证）；
 *   6. **留痕一致**：发布记录存在且有该模块记录时，最近一条记录的版本 = 清单当前版本。
 *
 * 用法：
 *     node frontend/scripts/check-module-manifest.mjs [--root <frontend 目录>]
 */
import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exit } from 'node:process'

import { listModuleDirs } from './check-module-isolation.mjs'
import { MODULE_META_FILE, loadModuleContractVersion, loadModulePackage } from './module-meta.mjs'
import { MANIFEST_PATH, RELEASE_LOG_FILE, RELEASES_DIR, REMOTE_ENTRY_FILE, readReleaseLog, readManifest } from './release-module.mjs'

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

/** 契约用例文件名与工厂标识（发现性护栏判据）。 */
export const MODULE_CONTRACT_SPEC = 'tests/module-contract.spec.ts'
export const MODULE_CONTRACT_FACTORY = 'describeModuleContract'

/**
 * 清单 / 版本发现 / 契约用例齐备护栏（纯函数，供 CLI 与用例复用）。
 *
 * @param options 选项：`frontendDir`（`frontend/` 目录；缺省按脚本位置推断）。
 * @returns 违规清单（空数组即通过）。
 */
export function checkModuleManifest(options = {}) {
  const frontendDir = resolve(options.frontendDir ?? FRONTEND_DIR)
  const problems = []

  // 1 清单可解析
  let entries = []
  try {
    const parsed = readManifest(frontendDir)
    entries = parsed.entries
    for (const rejection of parsed.rejected) {
      problems.push(`清单项被拒（${rejection.name}）：${rejection.reason}`)
    }
  } catch (error) {
    problems.push(`清单不可读：${error instanceof Error ? error.message : String(error)}`)
    return problems
  }

  const contractVersion = loadModuleContractVersion(frontendDir)
  const log = readReleaseLog(frontendDir)

  for (const entry of entries) {
    // 2 远端条目版本化 / 3 本地条目可解析
    if (entry.mode === 'remote') {
      const pattern = new RegExp(`^https?://[^/]+/${entry.name}/([^/]+)/${REMOTE_ENTRY_FILE}$`)
      const match = pattern.exec(entry.entry)
      if (match === null) {
        problems.push(`远端条目入口不符合版本目录约定：${entry.name} → ${entry.entry}`)
      } else if (match[1] !== entry.version) {
        problems.push(`远端条目入口版本与清单版本不一致：${entry.name} → ${entry.entry}（清单 ${entry.version}）`)
      }
    } else {
      const localEntry = join(frontendDir, 'apps/desktop/src/modules', entry.entry, 'index.ts')
      if (!existsSync(localEntry)) {
        problems.push(`本地条目入口未登记（宿主本地入口表）：${entry.name} → ${entry.entry}（缺 ${localEntry}）`)
      }
    }

    // 4 版本发现
    const moduleDir = join(frontendDir, 'modules', entry.name)
    if (existsSync(join(moduleDir, 'package.json'))) {
      const pkg = loadModulePackage(moduleDir)
      if (pkg.version !== entry.version) {
        problems.push(`清单版本与模块工程版本不一致：${entry.name} 清单 ${entry.version} ≠ package.json ${pkg.version}`)
      }
      const metaFile = join(moduleDir, 'dist', MODULE_META_FILE)
      if (existsSync(metaFile)) {
        const meta = JSON.parse(readFileSync(metaFile, 'utf8'))
        if (meta.name !== entry.name) problems.push(`产物元数据模块名不一致：${String(meta.name)} ≠ ${entry.name}`)
        if (meta.version !== entry.version) {
          problems.push(`清单版本与产物元数据版本不一致：${entry.name} 清单 ${entry.version} ≠ 产物 ${String(meta.version)}`)
        }
        if (meta.contractVersion !== contractVersion) {
          problems.push(`产物契约版本与平台不一致：${entry.name} ${String(meta.contractVersion)} ≠ ${contractVersion}`)
        }
      }
    }

    // 6 留痕一致
    const moduleRecords = log.records.filter((record) => record.module === entry.name)
    const last = moduleRecords[moduleRecords.length - 1]
    if (last !== undefined && last.version !== entry.version) {
      problems.push(`清单版本与最近发布记录不一致：${entry.name} 清单 ${entry.version} ≠ 记录 ${last.version}（${last.action}）`)
    }
  }

  // 5 契约用例齐备
  for (const moduleDir of listModuleDirs(frontendDir)) {
    const spec = join(moduleDir, MODULE_CONTRACT_SPEC)
    if (!existsSync(spec)) {
      problems.push(`模块契约用例缺失：${spec}（每个模块工程须经 describeModuleContract 跑同一套断言）`)
      continue
    }
    if (!readFileSync(spec, 'utf8').includes(MODULE_CONTRACT_FACTORY)) {
      problems.push(`模块契约用例未引用契约工厂 ${MODULE_CONTRACT_FACTORY}：${spec}`)
    }
  }

  return problems
}

/**
 * CLI 入口。
 *
 * @param argv 进程参数。
 */
function main(argv) {
  const rootIndex = argv.indexOf('--root')
  const frontendDir = rootIndex >= 0 ? resolve(argv[rootIndex + 1]) : undefined
  try {
    const problems = checkModuleManifest({ frontendDir })
    if (problems.length > 0) {
      console.error(`[module-manifest] 不通过（${problems.length} 项）：`)
      for (const problem of problems) console.error(`  - ${problem}`)
      exit(1)
    }
    console.log(
      `[module-manifest] 通过：清单可解析、远端条目版本化、版本发现一致、契约用例齐备（清单 ${MANIFEST_PATH}、发布记录 ${RELEASES_DIR}/${RELEASE_LOG_FILE}）`,
    )
  } catch (error) {
    console.error(`[module-manifest] 不通过：${error instanceof Error ? error.message : String(error)}`)
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
