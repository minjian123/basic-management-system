/**
 * 模块契约用例工厂（`@bms/core/testing`）：模块与平台之间的契约「同一套断言」。
 *
 * 各模块工程（`frontend/modules/*`）在自己的 spec 中调用本工厂并传入本模块实现，
 * 跑同一套断言——覆盖注入上下文（只读快照）、注册声明（八类通道键规则）、
 * 共享依赖与样式约束（由平台护栏纯函数产出的事实，零违规）；「全部注册实现」的
 * 齐备性由平台护栏（`check-module-manifest.mjs`）保证（见任务 03_02 详细设计 §3.9）。
 *
 * 核心包不触文件系统：共享 / 隔离事实由调用方（模块用例）经平台脚本取得后传入。
 */

import { describe, expect, it } from 'vitest'

import { MODULE_CONTRACT_VERSION } from '../src/module/contract'
import { MODULE_NAME_PATTERN } from '../src/module/define'
import { LOAD_MODES, REMOTE_ENTRY_PATTERN } from '../src/module/manifest'
import type { ModuleManifestEntry } from '../src/module/manifest'
import type { ModuleDefinition, ModuleRegistration } from '../src/module/types'

/** 模块契约事实断言（由平台护栏纯函数产出；提供时断言零违规）。 */
export interface ModuleContractFacts {
  /** 模块工程 `package.json` 版本（版本单一来源）。 */
  packageVersion?: string
  /** 共享依赖护栏违规清单（应为空）。 */
  sharedViolations?: string[]
  /** 隔离扫描违规清单（源码面 + 产物面，应为空）。 */
  isolationViolations?: string[]
}

/** 模块契约用例工厂目标。 */
export interface ModuleContractTarget {
  /** 模块定义（入口默认导出产物）。 */
  definition: ModuleDefinition
  /** 宿主清单条目（提供时断言名称 / 版本一致与形态合法）。 */
  manifestEntry?: ModuleManifestEntry
  /** 事实断言（提供时逐项断言）。 */
  facts?: ModuleContractFacts
}

/** 区域标识模式（点分小写）。 */
const REGION_AREA_PATTERN = /^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$/

/** 语言标识模式（小写）。 */
const LOCALE_PATTERN = /^[a-z][a-z0-9-]*$/

/** 取注册声明中各命名空间通道的键（组件 / 字段渲染器 / 图标 / 卡片 / 区域 / 令牌 / 文案包）。 */
function namespaceKeysOf(registration: ModuleRegistration): string[] {
  const keys: string[] = [
    ...Object.keys(registration.components ?? {}),
    ...(registration.fieldRenderers ?? []).map((item) => item.key),
    ...Object.keys(registration.icons ?? {}),
    ...(registration.cards ?? []).map((item) => (item as { key?: string }).key ?? ''),
    ...(registration.regions ?? []).map((item) => item.key),
    ...(registration.themeTokens ?? []).map((item) => item.key),
    ...(registration.i18nPacks ?? []).map((item) => item.key),
  ]
  return keys
}

/**
 * 登记模块契约用例套件（各模块传入本实现，跑同一套断言）。
 *
 * @param name 契约名（如「演示模块契约」）。
 * @param target 目标（模块定义 + 可选清单条目 / 事实）。
 */
export function describeModuleContract(name: string, target: ModuleContractTarget): void {
  describe(name, () => {
    it('定义形状与契约版本：冻结、名称 / 版本合法、契约版本与平台一致', () => {
      const { definition } = target
      expect(Object.isFrozen(definition)).toBe(true)
      expect(MODULE_NAME_PATTERN.test(definition.manifest.name)).toBe(true)
      expect(definition.manifest.version.trim()).not.toBe('')
      expect(definition.manifest.contractVersion).toBe(MODULE_CONTRACT_VERSION)
    })

    it('注入上下文：只读快照可消费、缺失项自行降级（不抛错、不假定存在）', async () => {
      const registration = await target.definition.setup(Object.freeze({}))
      expect(typeof registration).toBe('object')
      expect(registration).not.toBeNull()
    })

    it('注册声明：八类通道键带模块命名空间前缀、形状合法', async () => {
      const moduleName = target.definition.manifest.name
      const registration = await target.definition.setup({})

      for (const key of namespaceKeysOf(registration)) {
        expect(key.startsWith(`${moduleName}:`)).toBe(true)
      }
      for (const route of registration.routes ?? []) {
        expect(route.path.startsWith('/')).toBe(true)
        expect(typeof route.component).toBe('function')
      }
      for (const region of registration.regions ?? []) {
        expect(REGION_AREA_PATTERN.test(region.area)).toBe(true)
        expect(region.component).toBeDefined()
      }
      for (const pack of registration.i18nPacks ?? []) {
        const locale = pack.key.split(':')[1] ?? ''
        expect(LOCALE_PATTERN.test(locale)).toBe(true)
      }
      for (const token of registration.themeTokens ?? []) {
        for (const tokenName of Object.keys(token.tokens)) {
          expect(tokenName.startsWith('--bms-')).toBe(true)
        }
      }
    })

    it('清单一致：名称 / 版本严格相等、形态合法（提供清单条目时）', () => {
      const entry = target.manifestEntry
      if (entry === undefined) return
      expect(entry.name).toBe(target.definition.manifest.name)
      expect(entry.version).toBe(target.definition.manifest.version)
      expect(LOAD_MODES.includes(entry.mode)).toBe(true)
      if (entry.mode === 'remote') {
        expect(REMOTE_ENTRY_PATTERN.test(entry.entry)).toBe(true)
      }
      expect(typeof entry.enabled).toBe('boolean')
    })

    it('版本单一来源：定义版本 = 模块工程 package.json 版本（提供时）', () => {
      if (target.facts?.packageVersion === undefined) return
      expect(target.definition.manifest.version).toBe(target.facts.packageVersion)
    })

    it('共享依赖：白名单与版本要求零违规（提供事实时）', () => {
      if (target.facts?.sharedViolations === undefined) return
      expect(target.facts.sharedViolations).toEqual([])
    })

    it('样式约束：隔离扫描零违规（提供事实时）', () => {
      if (target.facts?.isolationViolations === undefined) return
      expect(target.facts.isolationViolations).toEqual([])
    })
  })
}
