// kiwi_id: 961
/** 全局搜索能力基类 / 组件基类用例（07_07）：契约同实现（核心 + 投影）+ 身份依赖 + 域过滤 + 组件展示语义。 */

import { BaseAccess, BaseSearch } from '@bms/core'
import {
  describeSearchContract,
  SEARCH_CONTRACT_DOMAINS,
  SEARCH_CONTRACT_HITS,
  type SearchContractEngine,
  type SearchContractTarget,
} from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体权限上下文。 */
class DemoAccess extends BaseAccess {}

/** 具体搜索件（可实例化）。 */
class SearchState extends BaseSearch {}

/**
 * 构造权限上下文。
 *
 * @param codes 权限码。
 * @returns 权限上下文。
 */
function accessOf(codes: readonly string[]): BaseAccess {
  const access = new DemoAccess()
  access.setCodes(codes)
  return access
}

/** 契约目标（基类实例适配）。 */
function makeTarget(): SearchContractTarget {
  const base = new SearchState()
  return {
    get ready() {
      return base.ready
    },
    get degraded() {
      return base.degraded
    },
    get requestCount() {
      return base.requestCount
    },
    get phase() {
      return base.phase
    },
    get keyword() {
      return base.keyword
    },
    get domains() {
      return base.domains
    },
    get accessibleDomains() {
      return base.accessibleDomains
    },
    get groups() {
      return base.groups
    },
    get total() {
      return base.total
    },
    get page() {
      return base.page
    },
    get pageSize() {
      return base.pageSize
    },
    get suggestions() {
      return base.suggestions
    },
    get recentKeywords() {
      return base.recentKeywords
    },
    get logItems() {
      return base.logItems
    },
    get fileItems() {
      return base.fileItems
    },
    get engineDegraded() {
      return base.engineDegraded
    },
    setReady: (value) => base.setReady(value),
    setEngine: (engine) => base.setEngine(engine as SearchContractEngine | undefined),
    setAccess: (access) => base.setAccess(access as BaseAccess),
    setDomains: (domains) => base.setDomains(domains),
    setKeyword: (keyword) => base.setKeyword(keyword),
    setActiveDomain: (key) => base.setActiveDomain(key),
    setPage: (page) => base.setPage(page),
    setPageSize: (size) => base.setPageSize(size),
    setLogType: (type) => base.setLogType(type),
    setLogRange: (range) => base.setLogRange(range),
    setFileType: (type) => base.setFileType(type),
    search: () => base.search(),
    suggest: () => base.suggest(),
    clearSuggestions: () => base.clearSuggestions(),
    searchLogs: () => base.searchLogs(),
    searchFiles: () => base.searchFiles(),
    addRecentKeyword: (keyword) => base.addRecentKeyword(keyword),
    removeRecentKeyword: (keyword) => base.removeRecentKeyword(keyword),
    clearRecentKeywords: () => base.clearRecentKeywords(),
    dispose: () => base.dispose(),
  }
}

describeSearchContract('全局搜索契约（BaseSearch）', makeTarget)

describe('BaseSearch 身份与展示语义', () => {
  it('能力键与依赖登记', () => {
    const base = new SearchState()
    expect(base.identifier).toBe('search')
    expect(base.depends).toContain('global-search')
    expect(base).toBeInstanceOf(BaseSearch)
  })

  it('可见分组按可检索域过滤且只保留有命中的域', () => {
    const base = new SearchState()
    base.setDomains(SEARCH_CONTRACT_DOMAINS)
    base.setAccess(accessOf(['user:query']))
    base.groups.push(
      { key: 'user', label: '用户', items: [SEARCH_CONTRACT_HITS[0]] },
      { key: 'log', label: '审计日志', items: [SEARCH_CONTRACT_HITS[2]] },
      { key: 'dept', label: '部门', items: [] },
    )
    expect(base.visibleGroups().map((group) => group.key)).toEqual(['user'])
  })

  it('命中语义与跳转目标', () => {
    const base = new SearchState()
    expect(base.hitSemantic(SEARCH_CONTRACT_HITS[0])).toBe('primary')
    expect(base.hitSemantic(SEARCH_CONTRACT_HITS[2])).toBe('info')
    expect(base.hitKey(SEARCH_CONTRACT_HITS[0])).toBe('user:u1')
    expect(base.hitTarget(SEARCH_CONTRACT_HITS[0])).toEqual({ docType: 'user', bizId: 'u1' })
  })

  it('权限门控与降级替代入口', () => {
    const base = new SearchState()
    base.setDomains(SEARCH_CONTRACT_DOMAINS)
    base.setAccess(accessOf(['user:query']))
    expect(base.hasLogPermission).toBe(false)
    expect(base.hasFilePermission).toBe(false)
    expect(base.fallbackDomains.map((domain) => domain.key)).toEqual(['user'])
  })
})
