// kiwi_id: 983
/**
 * 样例模块契约用例：经 `@bms/core/testing` 契约工厂跑**同一套断言**（注入上下文 / 注册声明 /
 * 共享依赖 / 样式约束）；共享与隔离事实由平台护栏纯函数产出（核心包不触文件系统）。
 */

import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { parseModuleManifest } from '@bms/core'
import { describeModuleContract } from '@bms/core/testing'

import { scanModuleSources } from '../../../scripts/check-module-isolation.mjs'
import { checkSharedWhitelist } from '../../../scripts/check-shared-whitelist.mjs'

import sampleModule from '../src/index'

/** 模块工程目录（`frontend/modules/sample`）。 */
const MODULE_DIR = resolve(import.meta.dirname, '..')
/** `frontend/` 目录。 */
const FRONTEND_DIR = resolve(import.meta.dirname, '../../..')

const pkg = JSON.parse(readFileSync(join(MODULE_DIR, 'package.json'), 'utf8')) as { version: string }
/** 宿主清单条目（经 core 严格解析；清单为加载与回滚的唯一来源）。 */
const manifestEntry = parseModuleManifest(
  JSON.parse(readFileSync(join(FRONTEND_DIR, 'apps/desktop/public/modules.json'), 'utf8')),
).entries.find((entry) => entry.name === sampleModule.manifest.name)

describeModuleContract('样例模块契约（Kiwi 982）', {
  definition: sampleModule,
  manifestEntry,
  facts: {
    packageVersion: pkg.version,
    // 共享依赖关（白名单 / 版本要求；产物未构建时不要求归档）
    sharedViolations: checkSharedWhitelist({ frontendDir: FRONTEND_DIR, requireArtifacts: false }),
    // 样式约束关（源码面隔离扫描；产物面由 module-build 的 guard:isolation 兜底）
    isolationViolations: scanModuleSources(FRONTEND_DIR),
  },
})
