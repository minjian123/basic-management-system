#!/usr/bin/env node
/**
 * 模块产物元数据与版本注入（零依赖 ESM；构建期，宿主与模块工程共用）。
 *
 * 目的（任务 03_02 详细设计 §3.3）：
 *   - **版本单一来源**：模块工程 `package.json` 的 `version` 为模块版本唯一权威，
 *     构建期经 `define` 注入模块定义（`__BMS_MODULE_VERSION__`，定义不再手写版本）；
 *   - **版本发现**：构建结束产出 `dist/module.meta.json`（名称 / 版本 / 契约版本），
 *     作为「产物版本」权威——发布与护栏据此校验「清单版本 = 产物版本 = 源码版本」。
 *
 * 用法（模块工程构建配置）：
 *     import { createModuleMetaPlugin, loadModuleContractVersion, loadModulePackage, moduleVersionDefine } from '../../scripts/module-meta.mjs'
 *     const pkg = loadModulePackage(moduleDir)
 *     define: moduleVersionDefine(pkg.version)
 *     plugins: [createModuleMetaPlugin({ name: MODULE_NAME, version: pkg.version, contractVersion: loadModuleContractVersion() })]
 */
import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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

/** 产物元数据文件名（发布与护栏的「产物版本」权威）。 */
export const MODULE_META_FILE = 'module.meta.json'

/** 构建期注入的版本常量名（模块定义经它取得 `package.json` 版本）。 */
export const MODULE_VERSION_DEFINE = '__BMS_MODULE_VERSION__'

/** 模块契约版本单一来源文件名（`frontend/module-contract.json`）。 */
export const MODULE_CONTRACT_FILE = 'module-contract.json'

/**
 * 读取模块工程 `package.json`。
 *
 * @param moduleDir 模块工程目录（含 `package.json`）。
 * @returns 包清单（名称 / 版本）。
 */
export function loadModulePackage(moduleDir) {
  const file = join(moduleDir, 'package.json')
  if (!existsSync(file)) {
    throw new Error(`模块工程缺少 package.json：${file}`)
  }
  return JSON.parse(readFileSync(file, 'utf8'))
}

/**
 * 生成构建期版本注入（`define`，vite / vitest 同用——缺一即测试与构建版本口径不一致）。
 *
 * @param version 模块版本（取自 `package.json`）。
 * @returns `define` 映射。
 */
export function moduleVersionDefine(version) {
  return { [MODULE_VERSION_DEFINE]: JSON.stringify(String(version)) }
}

/**
 * 读取平台模块契约版本（单一来源 `frontend/module-contract.json`）。
 *
 * @param frontendDir `frontend/` 目录（缺省按本文件位置推断）。
 * @returns 契约版本（正整数）。
 */
export function loadModuleContractVersion(frontendDir = FRONTEND_DIR) {
  const file = join(frontendDir, MODULE_CONTRACT_FILE)
  if (!existsSync(file)) {
    throw new Error(`模块契约版本单一来源不存在：${file}`)
  }
  const contractVersion = JSON.parse(readFileSync(file, 'utf8')).contractVersion
  if (!Number.isInteger(contractVersion) || contractVersion < 1) {
    throw new Error(`模块契约版本非法（${MODULE_CONTRACT_FILE}）：${String(contractVersion)}`)
  }
  return contractVersion
}

/**
 * 产物元数据插件：构建结束 emit `dist/module.meta.json`（名称 / 版本 / 契约版本）。
 *
 * @param options 模块名（= 清单 `name`）/ 版本（= `package.json` 版本）/ 契约版本（= 平台常量）。
 * @returns Vite 插件。
 */
export function createModuleMetaPlugin({ name, version, contractVersion }) {
  return {
    name: 'bms-module-meta',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: MODULE_META_FILE,
        source: `${JSON.stringify({ name, version, contractVersion }, null, 2)}\n`,
      })
    },
  }
}
