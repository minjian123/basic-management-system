/** 清单对账用例（Kiwi 715）：《前端基类清单》↔ 代码双向（漏登记 / 僵尸条目，双端同款）。 */

import { describe, expect, it } from 'vitest'

import { parseManifest, reconcileManifest, type ManifestIndex } from './helpers/guard/manifest'
import { buildRepoIndex, readManifest } from './helpers/guard/repo'

const repo = buildRepoIndex()
const manifestText = readManifest()
const manifest = parseManifest(manifestText ?? '')

describe.skipIf(!manifestText)('清单对账（Kiwi 715）', () => {
  it('① 清单 §5 与 fragments.ts 双向一致（当前仓库）', () => {
    expect(reconcileManifest(manifest, repo)).toEqual([])
  })

  it('② 僵尸条目 fixture 被拦截（清单有、代码无）', () => {
    const broken: ManifestIndex = {
      ...manifest,
      fragments: [...manifest.fragments, { name: 'useGhost', key: 'ghost', depends: [] }],
    }
    const problems = reconcileManifest(broken, repo)
    expect(problems.map((problem) => problem.rule)).toContain('manifest.fragment-missing')
  })

  it('③ 漏登记 fixture 被拦截（代码有、清单无）', () => {
    const broken: ManifestIndex = {
      ...manifest,
      fragments: manifest.fragments.filter((row) => row.key !== 'value'),
    }
    const problems = reconcileManifest(broken, repo)
    expect(problems.map((problem) => problem.rule)).toContain('manifest.fragment-unregistered')
  })

  it('④ depends 不一致 fixture 被拦截', () => {
    const broken: ManifestIndex = {
      ...manifest,
      fragments: manifest.fragments.map((row) => (row.key === 'field' ? { ...row, depends: ['value'] } : row)),
    }
    const problems = reconcileManifest(broken, repo)
    expect(problems.map((problem) => problem.rule)).toContain('manifest.fragment-depends')
  })

  it('⑤ 基类 / 域基类实现缺失 fixture 被拦截', () => {
    const broken: ManifestIndex = {
      ...manifest,
      baseNames: [...manifest.baseNames, 'BaseGhost'],
      domainFiles: [...manifest.domainFiles, 'BaseGhost.vue'],
    }
    const problems = reconcileManifest(broken, repo)
    const rules = problems.map((problem) => problem.rule)
    expect(rules).toContain('manifest.base-missing')
    expect(rules).toContain('manifest.domain-missing')
  })
})
