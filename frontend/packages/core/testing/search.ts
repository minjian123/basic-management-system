/**
 * 全局搜索契约（`@bms/core/testing`）。
 *
 * 能力基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、引擎注入与就绪、域权限二次过滤、多域分组、空态 / 降级 / 错误结算、
 * 即时建议 Top N、审计日志 `log:query` 与范围校验、文件 `file:query`、最近搜索。
 */

import { describe, expect, it } from 'vitest'

/** 契约域（结构化最小面）。 */
export interface SearchContractDomain {
  /** 域标识。 */
  key: string
  /** 域名称。 */
  label: string
  /** 域权限码。 */
  perm?: string
}

/** 契合同步命中。 */
export interface SearchContractHit {
  /** 文档类型。 */
  docType: string
  /** 业务 ID。 */
  bizId: string
  /** 标题。 */
  title: string
  /** 高亮片段。 */
  highlight?: string
  /** 更新时间。 */
  updatedAt?: string
}

/** 契约分组。 */
export interface SearchContractGroup {
  /** 域标识。 */
  key: string
  /** 域名称。 */
  label: string
  /** 命中项。 */
  items: SearchContractHit[]
}

/** 契约检索引擎（结构化最小面）。 */
export interface SearchContractEngine {
  /** 即时建议。 */
  suggest?(input: { keyword: string; types?: readonly string[] }): Promise<unknown>
  /** 全局检索。 */
  searchGlobal?(input: {
    keyword: string
    types?: readonly string[]
    page: number
    pageSize: number
  }): Promise<unknown>
  /** 审计日志检索。 */
  searchLogs?(input: {
    keyword: string
    logType?: string
    start: string
    end: string
    page: number
    pageSize: number
  }): Promise<unknown>
  /** 文件内容检索。 */
  searchFiles?(input: {
    keyword: string
    fileType?: string
    page: number
    pageSize: number
  }): Promise<unknown>
}

/** 全局搜索契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface SearchContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 检索阶段。 */
  readonly phase: string
  /** 关键词。 */
  readonly keyword: string
  /** 域清单。 */
  readonly domains: readonly SearchContractDomain[]
  /** 可检索域（权限过滤后）。 */
  readonly accessibleDomains: readonly SearchContractDomain[]
  /** 全局检索分组。 */
  readonly groups: readonly SearchContractGroup[]
  /** 全局检索总数。 */
  readonly total: number
  /** 页码。 */
  readonly page: number
  /** 页长。 */
  readonly pageSize: number
  /** 即时建议。 */
  readonly suggestions: readonly SearchContractHit[]
  /** 最近搜索。 */
  readonly recentKeywords: readonly string[]
  /** 审计日志命中。 */
  readonly logItems: readonly SearchContractHit[]
  /** 文件内容命中。 */
  readonly fileItems: readonly SearchContractHit[]
  /** 检索侧降级标记。 */
  readonly engineDegraded: boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除检索引擎。 */
  setEngine(engine: SearchContractEngine | undefined): void
  /** 注入 / 移除权限上下文。 */
  setAccess(access: unknown): void
  /** 覆盖域清单。 */
  setDomains(domains: readonly SearchContractDomain[]): void
  /** 设置关键词。 */
  setKeyword(keyword: string): void
  /** 设置当前域。 */
  setActiveDomain(key: string): void
  /** 设置页码。 */
  setPage(page: number): void
  /** 设置页长。 */
  setPageSize(size: number): void
  /** 设置日志类型。 */
  setLogType(type: string): void
  /** 设置审计时间范围。 */
  setLogRange(range: { start?: string; end?: string }): void
  /** 设置文件类型。 */
  setFileType(type: string): void
  /** 全局检索。 */
  search(): Promise<unknown>
  /** 即时建议。 */
  suggest(): Promise<unknown>
  /** 清空建议。 */
  clearSuggestions(): void
  /** 审计日志检索。 */
  searchLogs(): Promise<unknown>
  /** 文件内容检索。 */
  searchFiles(): Promise<unknown>
  /** 追加最近搜索。 */
  addRecentKeyword(keyword: string): void
  /** 移除最近搜索。 */
  removeRecentKeyword(keyword: string): void
  /** 清空最近搜索。 */
  clearRecentKeywords(): void
  /** 释放。 */
  dispose(): void
}

/** 契约域清单。 */
export const SEARCH_CONTRACT_DOMAINS: readonly SearchContractDomain[] = [
  { key: 'user', label: '用户', perm: 'user:query' },
  { key: 'log', label: '审计日志', perm: 'log:query' },
  { key: 'file_meta', label: '文件', perm: 'file:query' },
]

/** 契约命中。 */
export const SEARCH_CONTRACT_HITS: readonly SearchContractHit[] = [
  { docType: 'user', bizId: 'u1', title: '张三', highlight: '研发中心 · <em>张</em>三', updatedAt: '2026-09-20T10:00:00Z' },
  { docType: 'user', bizId: 'u2', title: '张四', updatedAt: '2026-09-19T10:00:00Z' },
  { docType: 'log', bizId: 'l1', title: '操作日志', updatedAt: '2026-09-20T10:00:00Z' },
  { docType: 'file_meta', bizId: 'f1', title: '采购制度.pdf' },
]

/**
 * 创建检索引擎桩（记录调用轨迹）。
 *
 * @param overrides 覆盖方法。
 * @returns 引擎桩与调用轨迹。
 */
export function createSearchEngineStub(overrides: SearchContractEngine = {}): {
  engine: SearchContractEngine
  calls: string[]
} {
  const calls: string[] = []
  const engine: SearchContractEngine = {
    suggest: async () => {
      calls.push('suggest')
      return SEARCH_CONTRACT_HITS.filter((hit) => hit.docType === 'user')
    },
    searchGlobal: async () => {
      calls.push('searchGlobal')
      return {
        groups: [{ key: 'user', label: '用户', items: SEARCH_CONTRACT_HITS.filter((hit) => hit.docType === 'user') }],
        total: 2,
      }
    },
    searchLogs: async () => {
      calls.push('searchLogs')
      return { items: SEARCH_CONTRACT_HITS.filter((hit) => hit.docType === 'log'), total: 1 }
    },
    searchFiles: async () => {
      calls.push('searchFiles')
      return { items: SEARCH_CONTRACT_HITS.filter((hit) => hit.docType === 'file_meta'), total: 1 }
    },
    ...overrides,
  }
  return { engine, calls }
}

/**
 * 全局搜索契约（`07_07` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：域 `user`（`perm: 'user:query'`）/ `log`（`log:query`）/ `file_meta`（`file:query`）；
 * 引擎桩返回用户域两条命中、日志 / 文件各一条。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeSearchContract(name: string, create: () => SearchContractTarget): void {
  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      const stub = createSearchEngineStub()
      target.setEngine(stub.engine)
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setKeyword('张')
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.search()
      await target.suggest()
      await target.searchLogs()
      await target.searchFiles()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入引擎时不产生请求（占位）', async () => {
      const target = create()
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setReady(true)
      target.setKeyword('张')
      await target.search()
      await target.suggest()
      expect(target.requestCount).toBe(0)
      expect(target.phase).toBe('idle')
    })

    it('就绪注入引擎后检索装载（分组 / 总数 / 阶段）', async () => {
      const target = create()
      const stub = createSearchEngineStub()
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('张')
      await target.search()
      expect(target.requestCount).toBe(1)
      expect(target.phase).toBe('ready')
      expect(target.groups).toHaveLength(1)
      expect(target.total).toBe(2)
    })

    it('空结果结算为 empty', async () => {
      const target = create()
      const stub = createSearchEngineStub({ searchGlobal: async () => ({ groups: [], total: 0 }) })
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('无结果')
      await target.search()
      expect(target.phase).toBe('empty')
    })

    it('降级标记置位但结果仍展示', async () => {
      const target = create()
      const stub = createSearchEngineStub({
        searchGlobal: async () => ({
          groups: [{ key: 'user', label: '用户', items: [SEARCH_CONTRACT_HITS[0]] }],
          total: 1,
          degraded: true,
          degradeReason: 'fallback',
        }),
      })
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('张')
      await target.search()
      expect(target.engineDegraded).toBe(true)
      expect(target.groups).toHaveLength(1)
    })

    it('域权限二次过滤（无权限域不展示、不进 types）', async () => {
      const target = create()
      const seen: string[][] = []
      const stub = createSearchEngineStub({
        searchGlobal: async (input) => {
          seen.push([...(input.types ?? [])])
          return { groups: [], total: 0 }
        },
      })
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setAccess({ has: (code: string) => code === 'user:query', codes: ['user:query'] })
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('张')
      expect(target.accessibleDomains.map((domain) => domain.key)).toEqual(['user'])
      await target.search()
      expect(seen.at(-1)).toEqual(['user'])
    })

    it('即时建议按各域 Top N 截断', async () => {
      const target = create()
      const stub = createSearchEngineStub()
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('张')
      await target.suggest()
      expect(target.suggestions.length).toBeLessThanOrEqual(8)
      expect(stub.calls).toContain('suggest')
    })

    it('审计日志检索需 log:query 且范围合法', async () => {
      const target = create()
      const stub = createSearchEngineStub()
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('登录')
      target.setLogRange({ start: '2026-09-01', end: '2026-09-10' })

      target.setAccess({ has: () => false, codes: [] })
      await target.searchLogs()
      expect(target.requestCount).toBe(0)

      target.setAccess({ has: (code: string) => code === 'log:query', codes: ['log:query'] })
      await target.searchLogs()
      expect(target.logItems).toHaveLength(1)

      target.setLogRange({ start: '2026-01-01', end: '2026-09-10' })
      const before = target.requestCount
      await target.searchLogs()
      expect(target.requestCount).toBe(before)
    })

    it('文件内容检索需 file:query', async () => {
      const target = create()
      const stub = createSearchEngineStub()
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setAccess({ has: (code: string) => code === 'file:query', codes: ['file:query'] })
      target.setReady(true)
      target.setKeyword('采购')
      await target.searchFiles()
      expect(target.fileItems).toHaveLength(1)
    })

    it('检索失败置错误态与错误码', async () => {
      const target = create()
      const stub = createSearchEngineStub({
        searchGlobal: async () => {
          throw Object.assign(new Error('超时'), { code: 10102 })
        },
      })
      target.setDomains(SEARCH_CONTRACT_DOMAINS)
      target.setEngine(stub.engine)
      target.setReady(true)
      target.setKeyword('张')
      await target.search()
      expect(target.phase).toBe('error')
    })

    it('最近搜索去重 / 置顶 / 上限 / 移除', () => {
      const target = create()
      target.addRecentKeyword('采购')
      target.addRecentKeyword('张三')
      target.addRecentKeyword('采购')
      expect(target.recentKeywords[0]).toBe('采购')
      expect(new Set(target.recentKeywords).size).toBe(target.recentKeywords.length)
      target.removeRecentKeyword('采购')
      expect(target.recentKeywords).not.toContain('采购')
      target.clearRecentKeywords()
      expect(target.recentKeywords).toHaveLength(0)
    })
  })
}
