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
 * 用法（需先构建两侧产物）：
 *     cd frontend/apps/desktop && npm run build
 *     cd frontend/modules/demo && npm run build
 *     node frontend/scripts/check-shared-deps.mjs
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exit } from 'node:process'

import { readSharedSource } from './shared-deps.mjs'

/** `frontend/` 目录（本文件位于 `frontend/scripts/`）。 */
const FRONTEND_DIR = fileURLToPath(new URL('..', import.meta.url))

/** 两侧产物目录（角色 → 目录）。 */
const DIST_DIRS = {
  host: join(FRONTEND_DIR, 'apps/desktop/dist'),
  remote: join(FRONTEND_DIR, 'modules/demo/dist'),
}

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

/** 断言失败清单。 */
const problems = []
for (const [role, distDir] of Object.entries(DIST_DIRS)) {
  if (!existsSync(distDir)) {
    problems.push(`${role} 产物目录不存在：${distDir}（请先构建）`)
  }
}
if (problems.length > 0) {
  console.error(`[shared-deps] 不通过：${problems.join('；')}`)
  exit(1)
}

const source = readSharedSource()
const sharedNames = Object.keys(source.shared).sort()
const hostText = readDeclarationText(DIST_DIRS.host)
const remoteText = readDeclarationText(DIST_DIRS.remote)
if (hostText === undefined || remoteText === undefined) {
  console.error(
    '[shared-deps] 不通过：产物中未找到共享声明块（_virtual_mf-localSharedImportMap*），请确认 Module Federation 插件已参与构建',
  )
  exit(1)
}

const hostDeclared = parseHostDeclarations(hostText)
const remoteDeclared = parseRemoteDeclarations(remoteText, sharedNames)

// 1 共享面一致
const hostNames = Object.keys(hostDeclared).sort()
const remoteNames = Object.keys(remoteDeclared).sort()
if (hostNames.join(',') !== sharedNames.join(',')) {
  problems.push(`宿主共享面与单一来源不一致：产物 [${hostNames.join(', ')}] ≠ 单一来源 [${sharedNames.join(', ')}]`)
}
if (remoteNames.join(',') !== sharedNames.join(',')) {
  problems.push(`模块共享面与单一来源不一致：产物 [${remoteNames.join(', ')}] ≠ 单一来源 [${sharedNames.join(', ')}]`)
}

// 2 版本要求一致 + 3 / 4 角色形态
for (const name of sharedNames) {
  const expected = source.shared[name].requiredVersion
  const host = hostDeclared[name]
  const remote = remoteDeclared[name]
  if (host !== undefined && host.requiredVersion !== expected) {
    problems.push(`宿主 ${name} 的 requiredVersion 与单一来源不一致：${String(host.requiredVersion)} ≠ ${expected}`)
  }
  if (remote !== undefined && remote.requiredVersion !== expected) {
    problems.push(`模块 ${name} 的 requiredVersion 与单一来源不一致：${String(remote.requiredVersion)} ≠ ${expected}`)
  }
  if (host !== undefined && !host.providesLocal) {
    problems.push(`宿主 ${name} 被声明为 import:false（宿主是提供方，须打包并提供实例）`)
  }
  if (remote !== undefined && !remote.strictVersion) {
    problems.push(`模块 ${name} 未声明 strictVersion（版本不满足须拒绝加载）`)
  }
}

// 4 模块侧本地回退已消失（产物中无本地实现，取值即抛「必须由宿主提供」）
if (!remoteText.includes(HOST_REQUIRED_MARKER)) {
  problems.push('模块产物未体现「共享依赖必须由宿主提供」的取值语义（本地回退可能仍存在）')
}
const remoteImportFalse = /import:!1/.test(remoteText)
if (!remoteImportFalse) {
  problems.push('模块产物未声明 import:false（存在打包本地回退副本的风险）')
}

// 5 依赖实例数 = 1（提供方份数：宿主 1 + 模块 0）
for (const name of sharedNames) {
  const hostProvides = hostDeclared[name]?.providesLocal === true ? 1 : 0
  const remoteProvides = remoteDeclared[name]?.noLocalImport === true ? 0 : 1
  const providers = hostProvides + remoteProvides
  if (providers !== 1) {
    problems.push(`共享依赖 ${name} 的提供方份数为 ${providers}（应为 1：宿主提供、模块不提供）`)
  }
}

if (problems.length > 0) {
  console.error(`[shared-deps] 不通过：${problems.join('；')}`)
  exit(1)
}
console.log(
  `[shared-deps] 通过：共享面 ${sharedNames.join(' / ')}；两侧声明一致、宿主为提供方、模块 import:false + strictVersion；` +
    `依赖实例数 = 1（提供方份数：宿主 1 / 模块 0）`,
)
