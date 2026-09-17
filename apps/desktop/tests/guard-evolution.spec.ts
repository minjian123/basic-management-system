/** 新增流程演练与错误码对齐用例（Kiwi 716，双端同款）。 */

import { describe, expect, it } from 'vitest'

import { CAPABILITY_VIOLATION_CODE } from '@/base/capability'
import { NOT_IMPLEMENTED_CODE, PERMISSION_CODE, RATE_LIMIT_CODE } from '@/base/error'
import { REGISTRY_DUPLICATE_CODE } from '@/base/provider'

import { scanDependency } from './helpers/guard/dependency'
import { scanInheritance } from './helpers/guard/inheritance'
import { parseManifest, reconcileManifest, type ManifestIndex } from './helpers/guard/manifest'
import { buildRepoIndex, readManifest } from './helpers/guard/repo'

const repo = buildRepoIndex()
const manifestText = readManifest() ?? ''
const manifest = parseManifest(manifestText)

describe('新增流程演练与错误码对齐（Kiwi 716）', () => {
  it('① 新增流程步骤文档（清单 §8）齐备可执行', () => {
    expect(manifestText).toContain('新增演练')
    for (const step of ['候选', '设计节点', '评审', '登记', '护栏', '消费方']) {
      expect(manifestText).toContain(step)
    }
  })

  it('② 继承护栏可拦截违规 fixture', () => {
    const problems = scanInheritance(
      [{ path: 'src/base/probe.ts', source: 'export class BaseCapability extends Object {}' }],
      repo.fragmentKeys,
    )
    expect(problems.map((problem) => problem.rule)).toContain('inheritance.base-parent')
  })

  it('③ 依赖护栏可拦截违规 fixture', () => {
    const problems = scanDependency([
      {
        path: 'src/base/probe.ts',
        source: "import { useValue } from '@/components/base/value'\nexport const probe = useValue",
      },
    ])
    expect(problems.map((problem) => problem.rule)).toContain('dependency.reverse-components')
  })

  it('④ 对账护栏可拦截差异 fixture', () => {
    const broken: ManifestIndex = {
      ...manifest,
      fragments: manifest.fragments.filter((row) => row.key !== 'field'),
    }
    const problems = reconcileManifest(broken, repo)
    expect(problems.map((problem) => problem.rule)).toContain('manifest.fragment-unregistered')
  })

  it('⑤ 正样例（当前仓库）三类护栏全绿', () => {
    expect(scanInheritance(repo.files, repo.fragmentKeys)).toEqual([])
    expect(scanDependency(repo.files, repo.fragmentDepends)).toEqual([])
    if (manifestText) {
      expect(reconcileManifest(manifest, repo)).toEqual([])
    }
  })

  it('⑥ 错误码段位对齐（19001 / 10001 / 10003 / 10005 / 30001）', () => {
    expect(NOT_IMPLEMENTED_CODE).toBe(19001)
    expect(CAPABILITY_VIOLATION_CODE).toBe(10001)
    expect(REGISTRY_DUPLICATE_CODE).toBe(10003)
    expect(RATE_LIMIT_CODE).toBe(10005)
    expect(PERMISSION_CODE).toBe(30001)
  })
})
