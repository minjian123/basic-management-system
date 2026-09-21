#!/usr/bin/env node
/**
 * 共享面白名单与体积护栏（零依赖；挂 CI `shared-deps-check`）。
 *
 * 目的：共享面是**受控集合**——新增依赖必须先登记（进 `shared` 或 `notShared`），
 * 不得由某个模块工程私自扩面；同时防「不共享」演化为无限膨胀。
 *
 * 断言：
 *   1. **构建配置取自单一来源**：两侧 `vite.config.ts` 都必须经 `loadSharedDependencies` 取共享声明
 *      （禁止在配置里回退为手写 `shared` —— 那是漂移的入口）；
 *   2. **模块依赖落白名单**：模块 `package.json` 的 `dependencies` 除平台基座包（`@bms/*`，`file:` 链接）外，
 *      每个包须 ∈（共享面 ∪ 受控非共享项）；出现表外包名即失败（新增依赖须先登记）；
 *   3. **实装版本满足版本要求**：两侧 `package.json` 中受控条的实装版本须满足单一来源的 `requiredVersion`；
 *   4. **非共享项体积阈值**：模块产物（`dist/**​/*.{js,css}`）gzip 合计不得超过单一来源为该非共享项登记的阈值。
 *
 * 用法：
 *     node frontend/scripts/check-shared-whitelist.mjs
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { exit } from 'node:process'

import { readSharedSource } from './shared-deps.mjs'

/** `frontend/` 目录（本文件位于 `frontend/scripts/`）。 */
const FRONTEND_DIR = fileURLToPath(new URL('..', import.meta.url))

/** 受控条目的所在工程（角色 → package.json）。 */
const PACKAGE_JSONS = {
  宿主: join(FRONTEND_DIR, 'apps/desktop/package.json'),
  模块: join(FRONTEND_DIR, 'modules/demo/package.json'),
}

/** 构建配置（须取自单一来源）。 */
const VITE_CONFIGS = ['apps/desktop/vite.config.ts', 'modules/demo/vite.config.ts'].map((file) =>
  join(FRONTEND_DIR, file),
)

/** 平台基座包前缀（`file:` 链接、源码直出，共享机制不成立，白名单豁免）。 */
const PLATFORM_PACKAGE_PREFIX = '@bms/'

/**
 * 解析版本号（`X.Y.Z`，忽略预发布后缀）。
 *
 * @param text 版本串。
 * @returns `[major, minor, patch]`。
 */
function parseVersion(text) {
  return String(text)
    .split('-')[0]
    .split('.')
    .map((part) => Number.parseInt(part, 10) || 0)
}

/**
 * 比较两个版本。
 *
 * @param a 版本串。
 * @param b 版本串。
 * @returns 负数 / 0 / 正数。
 */
function compareVersion(a, b) {
  const [x, y] = [parseVersion(a), parseVersion(b)]
  for (let index = 0; index < 3; index += 1) {
    if (x[index] !== y[index]) return x[index] - y[index]
  }
  return 0
}

/**
 * 判断版本是否满足范围（支持 `^X.Y.Z` / `~X.Y.Z` / `X.Y.Z` 三种写法）。
 *
 * @param version 实装版本。
 * @param range 版本要求。
 * @returns 是否满足。
 */
function satisfies(version, range) {
  const target = String(range).trim()
  if (target.startsWith('^')) {
    const base = target.slice(1)
    return parseVersion(version)[0] === parseVersion(base)[0] && compareVersion(version, base) >= 0
  }
  if (target.startsWith('~')) {
    const base = target.slice(1)
    const [major, minor] = parseVersion(base)
    const [vMajor, vMinor] = parseVersion(version)
    return vMajor === major && vMinor === minor && compareVersion(version, base) >= 0
  }
  return compareVersion(version, target) === 0
}

/**
 * 统计目录下 js / css 的 gzip 合计。
 *
 * @param dir 目录。
 * @returns gzip 字节数。
 */
function measureGzip(dir) {
  let total = 0
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) walk(path)
      else if (/\.(js|css)$/.test(entry.name)) total += gzipSync(readFileSync(path)).length
    }
  }
  walk(dir)
  return total
}

const source = readSharedSource()
const sharedEntries = source.shared ?? {}
const notSharedEntries = source.notShared ?? {}
const whitelist = new Set([...Object.keys(sharedEntries), ...Object.keys(notSharedEntries)])
const problems = []

// 1 构建配置取自单一来源
for (const config of VITE_CONFIGS) {
  if (!existsSync(config)) {
    problems.push(`构建配置不存在：${config}`)
    continue
  }
  const text = readFileSync(config, 'utf8')
  if (!text.includes('loadSharedDependencies(')) {
    problems.push(`${config} 未从单一来源取共享声明（禁止手写 shared，须经 loadSharedDependencies）`)
  }
}

// 2 模块依赖落白名单 + 3 实装版本满足版本要求
for (const [role, file] of Object.entries(PACKAGE_JSONS)) {
  const pkg = JSON.parse(readFileSync(file, 'utf8'))
  const dependencies = Object.keys(pkg.dependencies ?? {})
  for (const name of dependencies) {
    if (name.startsWith(PLATFORM_PACKAGE_PREFIX)) continue
    if (role === '模块' && !whitelist.has(name)) {
      problems.push(`模块依赖 ${name} 未登记：请加入单一来源的 shared 或 notShared 后再使用`)
    }
  }
  const installed = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) }
  for (const [name, entry] of Object.entries({ ...sharedEntries, ...notSharedEntries })) {
    const range = entry.requiredVersion
    if (range === undefined) continue
    const version = installed[name]
    if (version === undefined) continue
    const normalized = String(version).replace(/^[^0-9]*/, '')
    if (!satisfies(normalized, range)) {
      problems.push(`${role} ${name} 实装版本 ${String(version)} 不满足单一来源要求 ${range}`)
    }
  }
}

// 4 非共享项体积阈值（模块产物）
const moduleDist = join(FRONTEND_DIR, 'modules/demo/dist')
for (const [name, entry] of Object.entries(notSharedEntries)) {
  const limit = entry.maxModuleGzipKb
  if (limit === undefined) continue
  if (!existsSync(moduleDist)) {
    problems.push(`模块产物目录不存在：${moduleDist}（请先构建后再跑本护栏）`)
    break
  }
  const actualKb = measureGzip(moduleDist) / 1024
  if (actualKb > limit) {
    problems.push(`模块产物 gzip 合计 ${actualKb.toFixed(1)} KB 超阈值 ${limit} KB（非共享项 ${name} 的成本口径）`)
  }
}

if (problems.length > 0) {
  console.error(`[shared-whitelist] 不通过：${problems.join('；')}`)
  exit(1)
}
console.log(
  `[shared-whitelist] 通过：白名单 ${[...whitelist].join(' / ')}；依赖与实装版本合规；` + `模块产物体积在阈值内`,
)
