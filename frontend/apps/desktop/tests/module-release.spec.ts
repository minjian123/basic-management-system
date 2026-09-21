// kiwi_id: 981
/**
 * 模块发布 / 回滚 / 停用工具用例（清单唯一来源）：三关强校验（版本 / 隔离 / 共享）、
 * 版本不可变、归档与清单写回、发布记录与摘要、回滚目标解析与产物保留校验；
 * 解析口径与 core 一致（fixture 对照）；清单 / 版本发现 / 契约用例齐备护栏；
 * 发布存储服务纯函数（MIME / 路径穿越 / 索引）。
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { parseModuleManifest } from '@bms/core'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { checkModuleManifest } from '../../../scripts/check-module-manifest.mjs'
import {
  ReleaseError,
  parseManifest,
  previousVersionOf,
  publishModule,
  readManifest,
  readReleaseLog,
  renderReleaseLogMarkdown,
  rollbackModule,
  setModuleEnabled,
} from '../../../scripts/release-module.mjs'
import { mimeTypeOf, renderIndex, resolveRequestPath } from '../../../scripts/serve-module-releases.mjs'

/** 临时 `frontend/` 工作区根。 */
let root = ''

/** 写入 JSON 文件（自动建目录）。 */
function writeJson(path: string, value: unknown): void {
  mkdirSync(join(path, '..'), { recursive: true })
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
}

/** 写入文本文件（自动建目录）。 */
function writeText(path: string, text: string): void {
  mkdirSync(join(path, '..'), { recursive: true })
  writeFileSync(path, text, 'utf8')
}

/**
 * 构造最小临时工作区（模块工程 + 宿主清单 + 共享 / 契约声明；形态与仓库同构）。
 *
 * @param target 工作区根。
 */
function createFixture(target: string): void {
  const moduleDir = join(target, 'modules/demo')
  writeJson(join(moduleDir, 'package.json'), { name: '@bms/module-demo', version: '0.1.0' })
  writeText(join(moduleDir, 'vite.config.ts'), "loadSharedDependencies({ role: 'remote' })\n")
  writeJson(join(moduleDir, 'budget.json'), { pageChunkHints: ['DemoHome'] })
  writeText(join(moduleDir, 'dist/remoteEntry.js'), 'export {}\n')
  writeJson(join(moduleDir, 'dist/module.meta.json'), { name: 'demo', version: '0.1.0', contractVersion: 1 })
  writeText(join(moduleDir, 'tests/module-contract.spec.ts'), "describeModuleContract('demo', target)\n")

  writeJson(join(target, 'apps/desktop/package.json'), { name: '@bms/desktop', version: '0.1.0' })
  writeText(join(target, 'apps/desktop/vite.config.ts'), "loadSharedDependencies({ role: 'host' })\n")
  writeJson(join(target, 'apps/desktop/public/modules.json'), [])

  writeJson(join(target, 'shared-dependencies.json'), { shared: {}, notShared: {} })
  writeJson(join(target, 'module-contract.json'), { contractVersion: 1 })
}

/**
 * 设定模块版本（`package.json` 与产物元数据同步；版本单一来源 + 版本发现口径）。
 *
 * @param version 新版本。
 */
function setModuleVersion(version: string): void {
  writeJson(join(root, 'modules/demo/package.json'), { name: '@bms/module-demo', version })
  writeJson(join(root, 'modules/demo/dist/module.meta.json'), { name: 'demo', version, contractVersion: 1 })
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'bms-module-release-'))
  createFixture(root)
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

describe('清单解析口径（Kiwi 981）', () => {
  it('与 core `parseModuleManifest` 逐项一致（有效项 / 缺字段 / 形态 / 可见性 / 重名 / 远端入口）', () => {
    const fixtures: unknown[] = [
      [
        { name: 'demo', entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js', version: '0.1.0', mode: 'remote' },
        { name: 'legacy', entry: 'legacy', version: '1.0.0', mode: 'local', enabled: false },
        { name: 'demo', entry: 'demo2', version: '0.2.0' },
        { name: 'bad-mode', entry: 'bad', version: '1', mode: 'federation' },
        { name: 'bad-enabled', entry: 'bad', version: '1', enabled: 'false' },
        { name: 'relative', entry: '/x/remoteEntry.js', version: '1', mode: 'remote' },
        { name: 'missing', entry: 'missing' },
      ],
      [],
    ]
    for (const fixture of fixtures) {
      expect(parseManifest(fixture)).toEqual(parseModuleManifest(fixture))
    }
  })

  it('整份形态非法（非数组）抛错（与 core 同口径）', () => {
    expect(() => parseManifest({})).toThrow(ReleaseError)
    expect(() => parseModuleManifest({})).toThrow()
  })
})

describe('发布（Kiwi 981）', () => {
  it('发布：归档产物 + 清单指向版本目录 + 发布记录与 Markdown 摘要', () => {
    const result = publishModule({ root, name: 'demo', by: 'tester' })

    expect(result.action).toBe('publish')
    expect(result.version).toBe('0.1.0')
    expect(result.entry).toBe('http://localhost:5002/demo/0.1.0/remoteEntry.js')
    expect(existsSync(join(root, 'releases/demo/0.1.0/remoteEntry.js'))).toBe(true)
    expect(existsSync(join(root, 'releases/demo/0.1.0/module.meta.json'))).toBe(true)

    const { entries } = readManifest(root)
    expect(entries).toEqual([
      {
        name: 'demo',
        entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
        version: '0.1.0',
        mode: 'remote',
        enabled: true,
      },
    ])

    const log = readReleaseLog(root)
    expect(log.records).toHaveLength(1)
    expect(log.records[0]).toMatchObject({
      by: 'tester',
      action: 'publish',
      module: 'demo',
      version: '0.1.0',
      previousVersion: null,
      contractVersion: 1,
    })
    const markdown = readFileSync(join(root, 'releases/release-log.md'), 'utf8')
    expect(markdown).toContain('| 动作 |')
    expect(markdown).toContain('| publish | demo | 0.1.0 |')
  })

  it('版本不可变：同版本产物已归档即拒绝重发；--force 重发记录 republish', () => {
    publishModule({ root, name: 'demo', by: 'tester' })

    expect(() => publishModule({ root, name: 'demo', by: 'tester' })).toThrow(/版本产物不可变/)

    const republish = publishModule({ root, name: 'demo', by: 'tester', force: true })
    expect(republish.action).toBe('republish')
    expect(readReleaseLog(root).records.map((record) => record.action)).toEqual(['publish', 'republish'])
  })

  it('清单已有同版本但产物未归档（开发地址迁移为版本目录）仍属首次发布', () => {
    writeJson(join(root, 'apps/desktop/public/modules.json'), [
      { name: 'demo', entry: 'http://localhost:5002/remoteEntry.js', version: '0.1.0', mode: 'remote' },
    ])

    const result = publishModule({ root, name: 'demo', by: 'tester' })

    expect(result.action).toBe('publish')
    expect(readManifest(root).entries[0]?.entry).toBe('http://localhost:5002/demo/0.1.0/remoteEntry.js')
  })

  it('dry-run 不写任何文件', () => {
    const result = publishModule({ root, name: 'demo', dryRun: true })

    expect(result.dryRun).toBe(true)
    expect(existsSync(join(root, 'releases'))).toBe(false)
    expect(readManifest(root).entries).toEqual([])
  })

  it('版本发现：产物元数据与 package.json 不一致即拒绝（校验通过才可入清单）', () => {
    writeJson(join(root, 'modules/demo/dist/module.meta.json'), { name: 'demo', version: '9.9.9', contractVersion: 1 })

    expect(() => publishModule({ root, name: 'demo' })).toThrow(/产物元数据版本与 package.json 不一致/)
    expect(readManifest(root).entries).toEqual([])
  })

  it('契约版本不符即拒绝（契约升级须模块适配后重新构建）', () => {
    writeJson(join(root, 'modules/demo/dist/module.meta.json'), { name: 'demo', version: '0.1.0', contractVersion: 999 })

    expect(() => publishModule({ root, name: 'demo' })).toThrow(/产物契约版本与平台不一致/)
  })

  it('隔离关：源码违规（全局原型）拒绝发布', () => {
    writeText(join(root, 'modules/demo/src/index.ts'), 'Object.prototype.hacked = true\n')

    expect(() => publishModule({ root, name: 'demo' })).toThrow(/隔离|G1|全局原型/)
    expect(existsSync(join(root, 'releases/demo/0.1.0'))).toBe(false)
  })

  it('共享关：模块依赖未登记白名单拒绝发布', () => {
    writeJson(join(root, 'modules/demo/package.json'), {
      name: '@bms/module-demo',
      version: '0.1.0',
      dependencies: { lodash: '^4.17.21' },
    })

    expect(() => publishModule({ root, name: 'demo' })).toThrow(/lodash 未登记/)
  })

  it('形态边界：清单条目为 mode: local 时拒绝发布（避免隐式翻转加载形态）', () => {
    writeJson(join(root, 'apps/desktop/public/modules.json'), [
      { name: 'demo', entry: 'demo', version: '0.1.0', mode: 'local' },
    ])

    expect(() => publishModule({ root, name: 'demo' })).toThrow(/mode: local/)
  })
})

describe('回滚与停用（Kiwi 981）', () => {
  it('版本升级后回滚到上一版本：清单指向回退、旧产物保留、记录含前后版本', () => {
    publishModule({ root, name: 'demo', by: 'tester' })
    setModuleVersion('0.2.0')
    publishModule({ root, name: 'demo', by: 'tester' })
    expect(readManifest(root).entries[0]?.version).toBe('0.2.0')

    const result = rollbackModule({ root, name: 'demo', by: 'tester' })

    expect(result).toMatchObject({ version: '0.1.0', previousVersion: '0.2.0' })
    expect(readManifest(root).entries[0]).toMatchObject({
      version: '0.1.0',
      entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
    })
    expect(existsSync(join(root, 'releases/demo/0.1.0/remoteEntry.js'))).toBe(true)
    expect(existsSync(join(root, 'releases/demo/0.2.0/remoteEntry.js'))).toBe(true)

    const records = readReleaseLog(root).records
    expect(records.map((record) => record.action)).toEqual(['publish', 'publish', 'rollback'])
    expect(records[2]).toMatchObject({ version: '0.1.0', previousVersion: '0.2.0' })
  })

  it('无上一版本时回滚拒绝（可用 --to 指定）', () => {
    publishModule({ root, name: 'demo' })

    expect(() => rollbackModule({ root, name: 'demo' })).toThrow(/未找到可回滚版本/)
  })

  it('回滚目标产物缺失拒绝（产物保留是回滚前提）', () => {
    publishModule({ root, name: 'demo' })
    setModuleVersion('0.2.0')
    publishModule({ root, name: 'demo' })
    rmSync(join(root, 'releases/demo/0.1.0'), { recursive: true, force: true })

    expect(() => rollbackModule({ root, name: 'demo' })).toThrow(/目标版本产物不存在/)
  })

  it('回滚目标契约版本不符拒绝', () => {
    publishModule({ root, name: 'demo' })
    setModuleVersion('0.2.0')
    publishModule({ root, name: 'demo' })
    writeJson(join(root, 'releases/demo/0.1.0/module.meta.json'), {
      name: 'demo',
      version: '0.1.0',
      contractVersion: 999,
    })

    expect(() => rollbackModule({ root, name: 'demo' })).toThrow(/契约版本与平台不一致/)
  })

  it('停用 / 启用：改清单 enabled 并留痕，不动入口与版本', () => {
    publishModule({ root, name: 'demo', by: 'tester' })

    const disabled = setModuleEnabled({ root, name: 'demo', enabled: false, by: 'tester' })
    expect(disabled).toMatchObject({ enabled: false, version: '0.1.0' })
    expect(readManifest(root).entries[0]).toMatchObject({
      enabled: false,
      entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
    })

    setModuleEnabled({ root, name: 'demo', enabled: true, by: 'tester' })
    expect(readManifest(root).entries[0]?.enabled).toBe(true)
    expect(readReleaseLog(root).records.map((record) => record.action)).toEqual(['publish', 'disable', 'enable'])
  })

  it('上一版本解析：取最近一次「版本 ≠ 当前版本」的记录（发布 / 回滚链均适用）', () => {
    const log = {
      version: 1,
      records: [
        { module: 'demo', version: '0.1.0' },
        { module: 'demo', version: '0.2.0' },
        { module: 'demo', version: '0.1.0' },
      ],
    } as Parameters<typeof previousVersionOf>[0]

    expect(previousVersionOf(log, 'demo', '0.1.0')).toBe('0.2.0')
    expect(previousVersionOf(log, 'demo', '0.2.0')).toBe('0.1.0')
    expect(previousVersionOf(log, 'other', '0.1.0')).toBeUndefined()
  })
})

describe('清单 / 版本发现 / 契约用例齐备护栏（Kiwi 981）', () => {
  it('发布态零违规；入口非版本目录 / 版本不一致 / 契约用例缺失 / 留痕不一致 逐项拦截', () => {
    publishModule({ root, name: 'demo', by: 'tester' })
    expect(checkModuleManifest({ frontendDir: root })).toEqual([])

    const entry = () => JSON.parse(readFileSync(join(root, 'apps/desktop/public/modules.json'), 'utf8'))

    writeJson(join(root, 'apps/desktop/public/modules.json'), [
      { ...entry()[0], entry: 'http://localhost:5002/remoteEntry.js' },
    ])
    expect(checkModuleManifest({ frontendDir: root }).join('；')).toContain('不符合版本目录约定')

    writeJson(join(root, 'apps/desktop/public/modules.json'), [
      { ...entry()[0], entry: 'http://localhost:5002/demo/0.2.0/remoteEntry.js' },
    ])
    expect(checkModuleManifest({ frontendDir: root }).join('；')).toContain('入口版本与清单版本不一致')

    writeJson(join(root, 'apps/desktop/public/modules.json'), entry())
    rmSync(join(root, 'modules/demo/tests/module-contract.spec.ts'))
    expect(checkModuleManifest({ frontendDir: root }).join('；')).toContain('模块契约用例缺失')

    writeText(join(root, 'modules/demo/tests/module-contract.spec.ts'), 'export {}\n')
    expect(checkModuleManifest({ frontendDir: root }).join('；')).toContain('未引用契约工厂')

    writeText(join(root, 'modules/demo/tests/module-contract.spec.ts'), "describeModuleContract('demo', target)\n")
    setModuleVersion('0.2.0')
    expect(checkModuleManifest({ frontendDir: root }).join('；')).toContain('清单版本与模块工程版本不一致')
  })

  it('Markdown 摘要渲染：含表头与全部记录（倒序）', () => {
    const markdown = renderReleaseLogMarkdown({
      version: 1,
      records: [
        {
          at: '2026-09-22T00:00:00.000Z',
          by: 'a',
          action: 'publish',
          module: 'demo',
          version: '0.1.0',
          previousVersion: null,
          entry: 'http://localhost:5002/demo/0.1.0/remoteEntry.js',
          contractVersion: 1,
        },
      ],
    })

    expect(markdown).toContain('| 时间（UTC） | 操作者 | 动作 | 模块 | 版本 | 前版本 | 入口 |')
    expect(markdown).toContain('| 2026-09-22T00:00:00.000Z | a | publish | demo | 0.1.0 | — |')
  })
})

describe('发布存储服务纯函数（Kiwi 981）', () => {
  it('MIME 映射与索引渲染', () => {
    expect(mimeTypeOf('remoteEntry.js')).toBe('text/javascript; charset=utf-8')
    expect(mimeTypeOf('a.css')).toBe('text/css; charset=utf-8')
    expect(mimeTypeOf('a.bin')).toBe('application/octet-stream')

    publishModule({ root, name: 'demo' })
    const index = renderIndex(join(root, 'releases'))
    expect(index).toContain('demo')
    expect(index).toContain('0.1.0')
  })

  it('路径解析防穿越（归一后一律落在发布存储根内）', () => {
    const releasesRoot = join(root, 'releases')

    expect(resolveRequestPath(releasesRoot, '/demo/0.1.0/remoteEntry.js')).toBe(
      join(releasesRoot, 'demo/0.1.0/remoteEntry.js'),
    )
    // `..` 段被归一（不逃逸根目录）；解析结果始终在 releases 根内
    for (const attempt of ['/../secret.txt', '/demo/../../secret.txt', '/%2e%2e/secret.txt']) {
      const resolved = resolveRequestPath(releasesRoot, attempt)
      expect(resolved?.startsWith(releasesRoot)).toBe(true)
    }
  })
})
