/**
 * 共享依赖治理：**运行期**断言（真实 Module Federation 运行时，非替身）。
 *
 * Kiwi 用例：**979**（阶段五 02_02「依赖共享与版本偏斜治理」，一任务一条）。
 *
 * 与构建期产物级断言（`frontend/scripts/check-shared-deps.mjs`）合为「双层」：
 * 产物级证明「产物里只有一份实现 + 声明形态正确」，本用例证明「运行期共享域协商只选出这一份」。
 *
 * 覆盖（见任务 02_02 详细设计 §3.6）：
 *   1. 共享声明由单一来源生成，角色差异正确（宿主提供 / 模块 `import:false` + `strictVersion`）；
 *   2. 共享域内每个共享依赖的**版本条目数恒为 1**（单例语义），且版本满足版本要求；
 *   3. 版本偏斜判定：不满足 `requiredVersion` 的版本不被接受（`strictVersion` 拒绝语义）。
 *
 * 说明：运行期「宿主未提供时的拒绝路径」不在此断言——MF 运行时共享域在**同一进程内为全局**，
 * 跨用例会相互污染（先建的实例已注册提供者），该路径由产物级断言（模块侧声明 `import:false`
 * 且本地取值函数直接抛「must be provided by host」）覆盖，强度更高且更稳定。
 */
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

import { createInstance, satisfy } from '@module-federation/runtime'
import { describe, expect, it } from 'vitest'

import { loadSharedDependencies } from '../../../scripts/shared-deps.mjs'

import hostPackage from '../package.json'

/** 共享面（单一来源）与两侧声明。 */
const hostDeclaration = loadSharedDependencies({ role: 'host' })
const remoteDeclaration = loadSharedDependencies({ role: 'remote' })
const sharedNames = Object.keys(hostDeclaration.shared)

/** 依赖清单中登记的版本范围（单一来源与之长期绑定，由白名单护栏断言）。 */
const declaredRange = (name: string): string => String((hostPackage.dependencies as Record<string, string>)[name] ?? '')

const nodeRequire = createRequire(import.meta.url)

/**
 * 读取依赖的**实装版本**（构建期由 MF 插件注入声明的就是该值；运行期用例据此模拟宿主提供方）。
 *
 * @param name 包名。
 * @returns 实装版本。
 */
function installedVersion(name: string): string {
  try {
    const resolved = nodeRequire.resolve(`${name}/package.json`)
    return JSON.parse(readFileSync(resolved, 'utf8')).version as string
  } catch {
    let dir = dirname(new URL(import.meta.url).pathname)
    for (let depth = 0; depth < 6; depth += 1) {
      const candidate = join(dir, 'node_modules', name, 'package.json')
      if (existsSync(candidate)) return JSON.parse(readFileSync(candidate, 'utf8')).version as string
      const parent = dirname(dir)
      if (parent === dir) break
      dir = parent
    }
    throw new Error(`未找到依赖 ${name} 的实装版本`)
  }
}

/** 宿主共享声明 + 实装版本（对齐构建期插件注入的形态）。 */
const hostSharedWithVersion = Object.fromEntries(
  Object.entries(hostDeclaration.shared).map(([name, entry]) => [name, { ...entry, version: installedVersion(name) }]),
)

describe('共享依赖声明（单一来源 + 角色差异）', () => {
  it('共享面与版本要求取自单一来源，且共享项一律单例', () => {
    expect(sharedNames.length).toBeGreaterThan(0)
    for (const name of sharedNames) {
      const entry = hostDeclaration.shared[name]
      expect(entry.singleton).toBe(true)
      expect(entry.requiredVersion).toMatch(/^[\^~]?\d+\.\d+\.\d+/)
      // 宿主为提供方：不得声明 import:false
      expect(entry.import).toBeUndefined()
    }
  })

  it('模块侧为消费方：不打包本地回退副本且版本不满足即拒绝', () => {
    for (const name of sharedNames) {
      const entry = remoteDeclaration.shared[name]
      expect(entry.import).toBe(false)
      expect(entry.suppressMissingImportWarning).toBe(true)
      expect(entry.strictVersion).toBe(true)
      expect(entry.requiredVersion).toBe(hostDeclaration.shared[name].requiredVersion)
    }
  })

  it('版本要求与依赖清单登记的版本范围一致（单一来源不漂移）', () => {
    for (const name of sharedNames) {
      expect(hostDeclaration.shared[name].requiredVersion).toBe(declaredRange(name))
    }
  })
})

describe('共享域协商（真实运行时）', () => {
  it('共享域内每个共享依赖只有一个版本条目，且版本满足版本要求', async () => {
    const instance = createInstance({
      name: 'bms-desktop-share-scope-test',
      shareScope: hostDeclaration.shareScope,
      shared: hostSharedWithVersion,
    })
    await Promise.all(instance.initializeSharing(hostDeclaration.shareScope))
    const scope = instance.shareScopeMap[hostDeclaration.shareScope] ?? {}

    for (const name of sharedNames) {
      const versions = Object.keys(scope[name] ?? {})
      expect(versions, `${name} 在共享域内的版本条目数`).toHaveLength(1)
      expect(versions[0], `${name} 的共享版本即实装版本`).toBe(installedVersion(name))
      expect(satisfy(versions[0], hostDeclaration.shared[name].requiredVersion), `${name} 版本满足要求`).toBe(true)
    }
  })

  it('宿主提供者可由运行时解析出实例（单例语义下的唯一来源）', async () => {
    const instance = createInstance({
      name: 'bms-desktop-resolve-test',
      shareScope: hostDeclaration.shareScope,
      shared: hostSharedWithVersion,
    })
    const factory = await instance.loadShare('vue')
    expect(factory).not.toBe(false)
    expect(typeof factory).toBe('function')
  })
})

describe('版本偏斜处置语义', () => {
  it('major 不一致的版本不被接受（strictVersion 下即拒绝加载）', () => {
    const required = hostDeclaration.shared['vue'].requiredVersion
    expect(satisfy('2.7.16', required)).toBe(false)
    expect(satisfy('4.0.0', required)).toBe(false)
  })

  it('同 major 且不低于下界的版本被接受', () => {
    const required = hostDeclaration.shared['vue'].requiredVersion
    expect(satisfy('3.5.41', required)).toBe(true)
    expect(satisfy('3.6.0', required)).toBe(true)
  })
})
