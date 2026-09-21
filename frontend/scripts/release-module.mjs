#!/usr/bin/env node
/**
 * 模块发布 / 回滚工具（零依赖 ESM；本地与 CI 同口径；见任务 03_02 详细设计 §3.5）。
 *
 * 职责：把「模块独立发布」落为可复现流程——**清单是模块加载与回滚的唯一来源**：
 *   publish   三关强校验（版本 / 隔离 / 共享）→ 归档产物到 `releases/<模块名>/<版本>/`
 *             → 更新清单条目（`entry` 指向版本目录、写入产物版本、`mode` 置 remote）→ 追加发布记录
 *   rollback  清单版本回退到上一版本（`--to` 或发布记录中上一个版本）；模块产物保留是回滚前提
 *   disable   清单内停用（`enabled: false`：不加载、不挂载、不进菜单；保留入口与版本）
 *   enable    恢复可见（`enabled: true`）
 *   status    打印清单条目、已归档版本与最近发布记录
 *
 * 版本不可变：同版本产物已归档即拒绝发布（回滚依赖旧产物不被覆盖）；`--force` 仅限本地开发重发
 * （记录动作 `republish`；生产禁用）。`--root <frontend 目录>` 供演练 / 测试在临时工作区跑全流程。
 *
 * 用法：
 *     node frontend/scripts/release-module.mjs publish  --module demo [--origin http://localhost:5002] [--by 名] [--force] [--dry-run]
 *     node frontend/scripts/release-module.mjs rollback --module demo [--to 0.1.0] [--by 名]
 *     node frontend/scripts/release-module.mjs disable  --module demo [--by 名]
 *     node frontend/scripts/release-module.mjs enable   --module demo [--by 名]
 *     node frontend/scripts/release-module.mjs status   [--module demo]
 */
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { exit } from 'node:process'

import { scanModuleProducts, scanModuleSources } from './check-module-isolation.mjs'
import { checkSharedWhitelist } from './check-shared-whitelist.mjs'
import { MODULE_META_FILE, loadModuleContractVersion, loadModulePackage } from './module-meta.mjs'

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

/** 清单文件（相对 `frontend/`）。 */
export const MANIFEST_PATH = 'apps/desktop/public/modules.json'

/** 发布存储目录（相对 `frontend/`；版本目录 `releases/<模块名>/<版本>/`）。 */
export const RELEASES_DIR = 'releases'

/** 发布记录文件（JSON 真源）与 Markdown 摘要（相对 `frontend/releases/`）。 */
export const RELEASE_LOG_FILE = 'release-log.json'
export const RELEASE_LOG_MARKDOWN_FILE = 'release-log.md'

/** 远端容器入口文件名（契约常量 `MODULE_REMOTE_ENTRY_FILE` 同值，发布脚本侧不可导入 TS）。 */
export const REMOTE_ENTRY_FILE = 'remoteEntry.js'

/** 缺省发布基址（本地演示；生产清单由部署阶段替换为 nginx / CDN 基址）。 */
export const DEFAULT_ORIGIN = 'http://localhost:5002'

/** 合法加载形态（与 core 契约同值）。 */
export const LOAD_MODES = ['local', 'remote']

/** 模块名模式（与 core `MODULE_NAME_PATTERN` 同值）。 */
export const MODULE_NAME_PATTERN = /^[a-z][a-z0-9-]*$/

/** 远端入口 URL 模式（与 core `REMOTE_ENTRY_PATTERN` 同值）。 */
export const REMOTE_ENTRY_PATTERN = /^https?:\/\/\S+$/

/** 合法发布记录动作。 */
export const RELEASE_ACTIONS = ['publish', 'republish', 'rollback', 'disable', 'enable']

/** 发布流程错误（可读信息；CLI 捕获后退出码 1）。 */
export class ReleaseError extends Error {}

/** 读取字符串字段（去空白；非字符串返回空串）。 */
function readText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * 解析模块清单（严格；口径与 core `parseModuleManifest` 一致，一致性由宿主用例以 fixture 对照断言）。
 *
 * @param raw 清单原始数据（`JSON.parse` 产物）。
 * @returns `{ entries, rejected }`。
 * @throws ReleaseError 清单非数组。
 */
export function parseManifest(raw) {
  if (!Array.isArray(raw)) {
    throw new ReleaseError('模块清单须为数组')
  }
  const entries = []
  const rejected = []
  const seen = new Set()
  for (const item of raw) {
    const record = typeof item === 'object' && item !== null ? item : {}
    const name = readText(record.name)
    const entry = readText(record.entry)
    const version = readText(record.version)
    const modeText = readText(record.mode)
    const enabledRaw = record.enabled

    if (name === '' || !MODULE_NAME_PATTERN.test(name)) {
      rejected.push({ name, reason: `模块名缺失或非法：${name}` })
      continue
    }
    if (entry === '') {
      rejected.push({ name, reason: '入口缺失' })
      continue
    }
    if (version === '') {
      rejected.push({ name, reason: '版本缺失' })
      continue
    }
    if (modeText !== '' && !LOAD_MODES.includes(modeText)) {
      rejected.push({ name, reason: `加载形态非法：${modeText}` })
      continue
    }
    if (enabledRaw !== undefined && typeof enabledRaw !== 'boolean') {
      rejected.push({ name, reason: `可见性取值非法：${String(enabledRaw)}` })
      continue
    }
    const mode = modeText === '' ? 'local' : modeText
    if (mode === 'remote' && !REMOTE_ENTRY_PATTERN.test(entry)) {
      rejected.push({ name, reason: `远端入口须为绝对 URL：${entry}` })
      continue
    }
    if (seen.has(name)) {
      rejected.push({ name, reason: '清单内重名' })
      continue
    }
    seen.add(name)
    entries.push({ name, entry, version, mode, enabled: enabledRaw ?? true })
  }
  return { entries, rejected }
}

/**
 * 解析 `frontend/` 根（缺省按脚本位置推断）。
 *
 * @param root 指定根目录。
 * @returns 绝对路径。
 */
function resolveRoot(root) {
  return resolve(root ?? FRONTEND_DIR)
}

/**
 * 读取清单文件（`entries` 为归一后的条目；`raw` 为原始数组，写回时只改目标条目、不夹带无关字段）。
 *
 * @param root `frontend/` 根。
 * @returns `{ entries, rejected, raw }`。
 */
export function readManifest(root) {
  const file = join(resolveRoot(root), MANIFEST_PATH)
  if (!existsSync(file)) {
    throw new ReleaseError(`模块清单不存在：${file}`)
  }
  const raw = JSON.parse(readFileSync(file, 'utf8'))
  return { ...parseManifest(raw), raw }
}

/**
 * 就地修补原始清单数组中目标条目（保留其余条目原字段与顺序；非对象项原样保留）。
 *
 * @param raw 原始清单数组。
 * @param name 目标模块名。
 * @param patch 字段补丁。
 * @returns 新数组。
 */
function patchRawEntries(raw, name, patch) {
  return raw.map((item) => {
    if (typeof item === 'object' && item !== null && readText(item.name) === name) {
      return { ...item, ...patch }
    }
    return item
  })
}

/**
 * 写回清单（2 空格缩进 + 末尾换行；未涉及条目与字段原值保留）。
 *
 * @param root `frontend/` 根。
 * @param entries 清单条目（原始形态；仅目标条目被修补）。
 */
export function writeManifest(root, entries) {
  const file = join(resolveRoot(root), MANIFEST_PATH)
  writeFileSync(file, `${JSON.stringify(entries, null, 2)}\n`, 'utf8')
}

/**
 * 读取发布记录（缺省空记录）。
 *
 * @param root `frontend/` 根。
 * @returns `{ version, records }`。
 */
export function readReleaseLog(root) {
  const file = join(resolveRoot(root), RELEASES_DIR, RELEASE_LOG_FILE)
  if (!existsSync(file)) return { version: 1, records: [] }
  return JSON.parse(readFileSync(file, 'utf8'))
}

/**
 * 渲染发布记录 Markdown 摘要。
 *
 * @param log 发布记录。
 * @returns Markdown 文本。
 */
export function renderReleaseLogMarkdown(log) {
  const lines = [
    '# 模块发布记录（摘要）',
    '',
    '> 由 `frontend/scripts/release-module.mjs` 从 `release-log.json` 生成；请勿手工编辑。',
    '',
    '| 时间（UTC） | 操作者 | 动作 | 模块 | 版本 | 前版本 | 入口 |',
    '| --- | --- | --- | --- | --- | --- | --- |',
  ]
  for (const record of [...log.records].reverse()) {
    lines.push(
      `| ${record.at} | ${record.by} | ${record.action} | ${record.module} | ${record.version} | ${record.previousVersion ?? '—'} | ${record.entry} |`,
    )
  }
  lines.push('')
  return `${lines.join('\n')}\n`
}

/**
 * 追加发布记录（JSON 真源 + Markdown 摘要）。
 *
 * @param root `frontend/` 根。
 * @param record 记录（时间 / 操作者 / 动作 / 模块 / 版本 / 前版本 / 入口 / 契约版本）。
 */
export function appendReleaseLog(root, record) {
  const log = readReleaseLog(root)
  log.records.push(record)
  const dir = join(resolveRoot(root), RELEASES_DIR)
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, RELEASE_LOG_FILE), `${JSON.stringify(log, null, 2)}\n`, 'utf8')
  writeFileSync(join(dir, RELEASE_LOG_MARKDOWN_FILE), renderReleaseLogMarkdown(log), 'utf8')
}

/**
 * 读取产物元数据（`dist/module.meta.json`）。
 *
 * @param moduleDir 模块工程目录。
 * @returns 元数据（缺失 / 非法返回 `undefined`）。
 */
export function readModuleMeta(moduleDir) {
  const file = join(moduleDir, 'dist', MODULE_META_FILE)
  if (!existsSync(file)) return undefined
  try {
    return JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    return undefined
  }
}

/**
 * 取 URL 的 origin（`https://host:port` 部分）。
 *
 * @param url URL。
 * @returns origin（非法返回 `undefined`）。
 */
export function originOf(url) {
  const match = /^(https?:\/\/[^/]+)/.exec(String(url))
  return match?.[1]
}

/**
 * 取缺省操作者（`--by` > `git config user.name` > `USER`）。
 *
 * @param root `frontend/` 根（git 工作区）。
 * @returns 操作者标识。
 */
export function defaultOperator(root) {
  try {
    const name = execFileSync('git', ['config', 'user.name'], { cwd: resolveRoot(root), encoding: 'utf8' }).trim()
    if (name !== '') return name
  } catch {
    // 非 git 工作区（演练 / 测试）→ 退回环境变量
  }
  return process.env.USER ?? process.env.USERNAME ?? 'unknown'
}

/**
 * 发布前强校验三关（版本 / 隔离 / 共享）。
 *
 * @param options `{ root, name }`。
 * @returns `{ violations, meta, pkg, moduleDir, distDir }`。
 */
export function checkReleaseGuards({ root, name }) {
  const frontendDir = resolveRoot(root)
  const moduleDir = join(frontendDir, 'modules', name)
  const distDir = join(moduleDir, 'dist')
  const violations = []

  if (!existsSync(moduleDir)) {
    violations.push(`模块工程不存在：${moduleDir}`)
    return { violations, meta: undefined, pkg: undefined, moduleDir, distDir }
  }

  // ① 版本关
  const pkg = loadModulePackage(moduleDir)
  const meta = readModuleMeta(moduleDir)
  const contractVersion = loadModuleContractVersion(frontendDir)
  if (!existsSync(join(distDir, REMOTE_ENTRY_FILE))) {
    violations.push(`产物入口不存在：${join(distDir, REMOTE_ENTRY_FILE)}（请先 npm run build）`)
  }
  if (meta === undefined) {
    violations.push(`产物元数据不存在或非法：${join(distDir, MODULE_META_FILE)}（请先 npm run build）`)
  } else {
    if (meta.name !== name) violations.push(`产物元数据模块名不一致：${String(meta.name)} ≠ ${name}`)
    if (meta.version !== pkg.version) violations.push(`产物元数据版本与 package.json 不一致：${meta.version} ≠ ${pkg.version}`)
    if (meta.contractVersion !== contractVersion) {
      violations.push(`产物契约版本与平台不一致：${String(meta.contractVersion)} ≠ ${contractVersion}（契约升级须重新构建发布）`)
    }
  }

  // ② 隔离关（源码面 + 产物面）
  violations.push(...scanModuleSources(frontendDir))
  if (existsSync(distDir)) {
    violations.push(...scanModuleProducts(frontendDir))
  }

  // ③ 共享关（白名单 / 版本要求 / 非共享项体积）
  violations.push(...checkSharedWhitelist({ frontendDir }))

  return { violations, meta, pkg, moduleDir, distDir }
}

/**
 * 取发布记录中该模块的上一个版本（最近一次「版本 ≠ 当前版本」的记录）。
 *
 * @param log 发布记录。
 * @param name 模块名。
 * @param currentVersion 清单当前版本。
 * @returns 版本（无则 `undefined`）。
 */
export function previousVersionOf(log, name, currentVersion) {
  for (const record of [...log.records].reverse()) {
    if (record.module !== name) continue
    if (record.version !== currentVersion) return record.version
  }
  return undefined
}

/**
 * 发布模块（三关校验 → 归档 → 清单更新 → 发布记录）。
 *
 * @param options `{ root?, name, origin?, by?, force?, dryRun? }`。
 * @returns 发布结果。
 * @throws ReleaseError 校验未通过 / 版本不可变 / 形态冲突。
 */
export function publishModule(options) {
  const root = resolveRoot(options.root)
  const { name } = options
  const by = options.by ?? defaultOperator(root)
  const force = options.force ?? false
  const dryRun = options.dryRun ?? false

  const { violations, meta, pkg } = checkReleaseGuards({ root, name })
  if (violations.length > 0) {
    throw new ReleaseError(`发布前强校验未通过（${violations.length} 项）：\n  - ${violations.join('\n  - ')}`)
  }
  const version = meta.version
  const { entries, rejected, raw } = readManifest(root)
  if (rejected.length > 0) {
    throw new ReleaseError(`清单存在被拒项（先修清单）：${rejected.map((item) => `${item.name}：${item.reason}`).join('；')}`)
  }
  const index = entries.findIndex((entry) => entry.name === name)
  const existing = index >= 0 ? entries[index] : undefined
  if (existing?.mode === 'local') {
    throw new ReleaseError(`清单条目为构建期合并形态（mode: local）：${name}（发布即远端形态，请先明确迁移）`)
  }
  const origin = options.origin ?? (existing !== undefined ? originOf(existing.entry) : undefined) ?? DEFAULT_ORIGIN
  const entryUrl = `${origin.replace(/\/+$/, '')}/${name}/${version}/${REMOTE_ENTRY_FILE}`
  const archiveDir = join(root, RELEASES_DIR, name, version)
  // 版本不可变以**归档产物**为准（清单版本仅是当前指向）：已归档即拒绝重发（回滚依赖旧产物不被覆盖），
  // 清单已有同版本但未归档（如开发地址迁移为版本目录）仍属首次发布
  const archived = existsSync(join(archiveDir, REMOTE_ENTRY_FILE))
  if (archived && !force) {
    throw new ReleaseError(`版本产物不可变：${name}@${version} 已归档（本地重发用 --force，记录动作 republish）`)
  }
  const action = archived ? 'republish' : 'publish'
  // 前版本 = 版本发生变化时的清单版本（首次发布 / 同版本重发为 null）
  const previousVersion = existing !== undefined && existing.version !== version ? existing.version : null

  if (dryRun) {
    return { action, version, entry: entryUrl, archiveDir, previousVersion, dryRun: true }
  }

  // 归档（版本不可变：force 才允许覆盖；非 force 时已归档即拒绝）
  if (archived) {
    rmSync(archiveDir, { recursive: true, force: true })
  }
  mkdirSync(archiveDir, { recursive: true })
  cpSync(join(root, 'modules', name, 'dist'), archiveDir, { recursive: true })

  // 清单更新（只改目标条目、其余原样保留；新条目按远端形态写入，不写 enabled——缺省可见）
  const nextRaw = patchRawEntries(raw, name, { entry: entryUrl, version, mode: 'remote' })
  if (index < 0) {
    nextRaw.push({ name, entry: entryUrl, version, mode: 'remote' })
  }
  writeManifest(root, nextRaw)

  // 发布记录
  appendReleaseLog(root, {
    at: new Date().toISOString(),
    by,
    action,
    module: name,
    version,
    previousVersion,
    entry: entryUrl,
    contractVersion: meta.contractVersion,
  })
  return { action, version, entry: entryUrl, archiveDir, previousVersion, pkgVersion: pkg.version }
}

/**
 * 回滚模块（清单版本回退；模块产物保留）。
 *
 * @param options `{ root?, name, to?, by? }`。
 * @returns 回滚结果。
 * @throws ReleaseError 无目标版本 / 产物缺失 / 契约版本不符。
 */
export function rollbackModule(options) {
  const root = resolveRoot(options.root)
  const { name } = options
  const by = options.by ?? defaultOperator(root)
  const { entries, rejected, raw } = readManifest(root)
  if (rejected.length > 0) {
    throw new ReleaseError(`清单存在被拒项（先修清单）：${rejected.map((item) => `${item.name}：${item.reason}`).join('；')}`)
  }
  const index = entries.findIndex((entry) => entry.name === name)
  if (index < 0) throw new ReleaseError(`清单未登记模块：${name}`)
  const current = entries[index]
  if (current.mode === 'local') throw new ReleaseError(`构建期合并形态（mode: local）不参与回滚：${name}`)
  const log = readReleaseLog(root)
  const targetVersion = options.to ?? previousVersionOf(log, name, current.version)
  if (targetVersion === undefined) {
    throw new ReleaseError(`未找到可回滚版本：${name}（仅发布过一次；可用 --to 指定目标版本）`)
  }
  if (targetVersion === current.version) {
    throw new ReleaseError(`回滚目标与当前版本相同：${name}@${targetVersion}`)
  }
  const archiveDir = join(root, RELEASES_DIR, name, targetVersion)
  if (!existsSync(join(archiveDir, REMOTE_ENTRY_FILE))) {
    throw new ReleaseError(`目标版本产物不存在（产物保留是回滚前提）：${archiveDir}`)
  }
  const metaFile = join(archiveDir, MODULE_META_FILE)
  if (!existsSync(metaFile)) throw new ReleaseError(`目标版本产物元数据不存在：${metaFile}`)
  const targetMeta = JSON.parse(readFileSync(metaFile, 'utf8'))
  const contractVersion = loadModuleContractVersion(root)
  if (targetMeta.name !== name || targetMeta.version !== targetVersion) {
    throw new ReleaseError(`目标版本产物元数据不一致：${String(targetMeta.name)}@${String(targetMeta.version)} ≠ ${name}@${targetVersion}`)
  }
  if (targetMeta.contractVersion !== contractVersion) {
    throw new ReleaseError(`目标版本契约版本与平台不一致：${String(targetMeta.contractVersion)} ≠ ${contractVersion}（须重新构建发布）`)
  }
  const origin = originOf(current.entry) ?? DEFAULT_ORIGIN
  const entryUrl = `${origin}/${name}/${targetVersion}/${REMOTE_ENTRY_FILE}`
  writeManifest(root, patchRawEntries(raw, name, { entry: entryUrl, version: targetVersion }))
  appendReleaseLog(root, {
    at: new Date().toISOString(),
    by,
    action: 'rollback',
    module: name,
    version: targetVersion,
    previousVersion: current.version,
    entry: entryUrl,
    contractVersion: targetMeta.contractVersion,
  })
  return { version: targetVersion, previousVersion: current.version, entry: entryUrl }
}

/**
 * 停用 / 启用模块（清单 `enabled`；保留入口与版本）。
 *
 * @param options `{ root?, name, enabled, by? }`。
 * @returns 结果（`{ enabled, version }`）。
 * @throws ReleaseError 清单未登记该模块。
 */
export function setModuleEnabled(options) {
  const root = resolveRoot(options.root)
  const { name, enabled } = options
  const by = options.by ?? defaultOperator(root)
  const { entries, rejected, raw } = readManifest(root)
  if (rejected.length > 0) {
    throw new ReleaseError(`清单存在被拒项（先修清单）：${rejected.map((item) => `${item.name}：${item.reason}`).join('；')}`)
  }
  const index = entries.findIndex((entry) => entry.name === name)
  if (index < 0) throw new ReleaseError(`清单未登记模块：${name}`)
  const entry = entries[index]
  writeManifest(root, patchRawEntries(raw, name, { enabled }))
  appendReleaseLog(root, {
    at: new Date().toISOString(),
    by,
    action: enabled ? 'enable' : 'disable',
    module: name,
    version: entry.version,
    previousVersion: null,
    entry: entry.entry,
    contractVersion: null,
  })
  return { enabled, version: entry.version }
}

/**
 * 模块状态（清单条目 / 已归档版本 / 最近记录）。
 *
 * @param options `{ root?, name? }`。
 * @returns 状态汇总。
 */
export function moduleStatus(options = {}) {
  const root = resolveRoot(options.root)
  const { entries, rejected } = readManifest(root)
  const log = readReleaseLog(root)
  const selected = options.name === undefined ? entries : entries.filter((entry) => entry.name === options.name)
  const archived = {}
  for (const entry of selected) {
    const dir = join(root, RELEASES_DIR, entry.name)
    if (!existsSync(dir)) continue
    archived[entry.name] = readdirSync(dir, { withFileTypes: true })
      .filter((item) => item.isDirectory() && existsSync(join(dir, item.name, MODULE_META_FILE)))
      .map((item) => item.name)
      .sort()
  }
  const records = log.records.filter((record) => options.name === undefined || record.module === options.name).slice(-5)
  return { entries: selected, rejected, archived, records }
}

/**
 * 解析 CLI 选项。
 *
 * @param argv 参数（不含子命令）。
 * @returns 选项对象。
 */
function parseOptions(argv) {
  const valueOf = (flag) => {
    const index = argv.indexOf(flag)
    return index >= 0 ? argv[index + 1] : undefined
  }
  return {
    module: valueOf('--module'),
    root: valueOf('--root'),
    origin: valueOf('--origin'),
    to: valueOf('--to'),
    by: valueOf('--by'),
    force: argv.includes('--force'),
    dryRun: argv.includes('--dry-run'),
  }
}

/** CLI 用法。 */
const USAGE = `用法：
  node frontend/scripts/release-module.mjs publish  --module <模块名> [--origin <基址>] [--by <操作者>] [--force] [--dry-run]
  node frontend/scripts/release-module.mjs rollback --module <模块名> [--to <版本>] [--by <操作者>]
  node frontend/scripts/release-module.mjs disable  --module <模块名> [--by <操作者>]
  node frontend/scripts/release-module.mjs enable   --module <模块名> [--by <操作者>]
  node frontend/scripts/release-module.mjs status   [--module <模块名>]`

/**
 * CLI 入口。
 *
 * @param argv 进程参数。
 */
function main(argv) {
  const [command, ...rest] = argv.slice(2)
  const options = parseOptions(rest)
  try {
    if (command === 'status') {
      const status = moduleStatus({ root: options.root, name: options.module })
      console.log('[release-module] 清单条目：')
      for (const entry of status.entries) {
        console.log(
          `  - ${entry.name}@${entry.version} [${entry.mode}${entry.enabled ? '' : ' / 停用'}] → ${entry.entry}`,
        )
      }
      for (const [name, versions] of Object.entries(status.archived)) {
        console.log(`[release-module] 已归档版本（${name}）：${versions.join(' / ')}`)
      }
      console.log('[release-module] 最近记录：')
      for (const record of status.records) {
        console.log(`  - ${record.at} ${record.by} ${record.action} ${record.module}@${record.version}`)
      }
      return
    }
    if (options.module === undefined) {
      throw new ReleaseError(`缺少 --module（模块名）\n${USAGE}`)
    }
    const common = { root: options.root, by: options.by, name: options.module }
    if (command === 'publish') {
      const result = publishModule({ ...common, origin: options.origin, force: options.force, dryRun: options.dryRun })
      console.log(
        `[release-module] ${result.dryRun ? '（dry-run）' : ''}${result.action}：${options.module}@${result.version} → ${result.entry}`,
      )
      return
    }
    if (command === 'rollback') {
      const result = rollbackModule({ ...common, to: options.to })
      console.log(
        `[release-module] rollback：${options.module} ${result.previousVersion} → ${result.version}（${result.entry}）`,
      )
      return
    }
    if (command === 'disable' || command === 'enable') {
      const result = setModuleEnabled({ ...common, enabled: command === 'enable' })
      console.log(`[release-module] ${command}：${options.module}@${result.version}（enabled=${String(result.enabled)}）`)
      return
    }
    throw new ReleaseError(`未知子命令：${command ?? ''}\n${USAGE}`)
  } catch (error) {
    if (error instanceof ReleaseError) {
      console.error(`[release-module] 不通过：${error.message}`)
    } else {
      console.error(`[release-module] 失败：${error instanceof Error ? error.stack : String(error)}`)
    }
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
