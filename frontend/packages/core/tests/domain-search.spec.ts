/** 全局搜索领域纯函数用例（07_07）：域 / 命中归一、权限过滤、参数构造、日志范围、分组与建议、最近搜索、降级与错误码。 */

import {
  SEARCH_LOG_RANGE_EXCEED_TEXT,
  SEARCH_LOG_RANGE_MAX_DAYS,
  SEARCH_LOG_RANGE_REQUIRED_TEXT,
  addRecentKeyword,
  buildFileParams,
  buildGlobalParams,
  buildLogParams,
  clampSearchPage,
  clampSearchPageSize,
  diffDays,
  domainLabelOf,
  filterAccessibleDomains,
  groupHits,
  hitKey,
  hitRouteTarget,
  isBlankKeyword,
  isSearchErrorCode,
  normalizeKeyword,
  normalizeRecentKeywords,
  normalizeSearchDomains,
  normalizeSearchHit,
  normalizeSearchHits,
  normalizeSearchResult,
  parseDegradeReason,
  parseDegraded,
  removeRecentKeyword,
  resolveSearchErrorText,
  topHits,
  validateLogRange,
  type SearchDomain,
} from '@bms/core'
import { describe, expect, it } from 'vitest'

const domains: SearchDomain[] = [
  { key: 'user', label: '用户', perm: 'user:query' },
  { key: 'log', label: '审计日志', perm: 'log:query' },
]

describe('domain/search 域与命中归一', () => {
  it('域归一剔除脏项并回落标签', () => {
    const list = normalizeSearchDomains([
      { key: 'user', label: '用户' },
      { key: '' },
      { key: 'dept' },
      null,
    ])
    expect(list).toEqual([
      { key: 'user', label: '用户' },
      { key: 'dept', label: 'dept' },
    ])
  })

  it('命中归一兼容 snake_case 并剔除脏项', () => {
    const hit = normalizeSearchHit({ doc_type: 'user', biz_id: 'u1', title: '张三', updated_at: '2026-09-20' })
    expect(hit).toEqual({ docType: 'user', bizId: 'u1', title: '张三', updatedAt: '2026-09-20' })
    expect(normalizeSearchHit({ biz_id: 'u2' })).toBeUndefined()
    expect(normalizeSearchHits([{ bizId: 'u1', title: '甲' }, { title: '无 id' }])).toHaveLength(1)
  })

  it('聚合结果归一（total 回落命中合计、降级原因白名单）', () => {
    const result = normalizeSearchResult({
      groups: [{ key: 'user', label: '用户', items: [{ docType: 'user', bizId: 'u1', title: '张三' }] }],
      degraded: true,
      degrade_reason: 'fallback',
    })
    expect(result.total).toBe(1)
    expect(result.degraded).toBe(true)
    expect(result.degradeReason).toBe('fallback')
    expect(normalizeSearchResult(null)).toEqual({ groups: [], total: 0 })
  })

  it('域权限过滤（perm 缺省可见）与域标签', () => {
    const visible = filterAccessibleDomains(domains, new Set(['user:query']))
    expect(visible.map((domain) => domain.key)).toEqual(['user'])
    expect(domainLabelOf(domains, 'user')).toBe('用户')
    expect(domainLabelOf(domains, 'unknown')).toBe('unknown')
  })
})

describe('domain/search 关键词与参数', () => {
  it('关键词归一（空判定 / 去空白 / 截断）', () => {
    expect(isBlankKeyword('   ')).toBe(true)
    expect(isBlankKeyword(null)).toBe(true)
    expect(isBlankKeyword(' 张 ')).toBe(false)
    expect(normalizeKeyword('  张三  ')).toBe('张三')
    expect(normalizeKeyword('一二三四五', 3)).toBe('一二三')
  })

  it('分页夹取与参数构造', () => {
    expect(clampSearchPage(0)).toBe(1)
    expect(clampSearchPage(999)).toBe(100)
    expect(clampSearchPageSize(0)).toBe(20)
    expect(clampSearchPageSize(999)).toBe(100)

    expect(buildGlobalParams({ keyword: '张', types: ['user', 'dept'], page: 2, pageSize: 10 })).toEqual({
      q: '张',
      types: 'user,dept',
      page: 2,
      size: 10,
    })
    expect(buildGlobalParams({ keyword: '张' })).toEqual({ q: '张', page: 1, size: 20 })
    expect(buildLogParams({ keyword: '登录', logType: 'login', start: '2026-09-01', end: '2026-09-02' })).toEqual({
      q: '登录',
      log_type: 'login',
      start_time: '2026-09-01',
      end_time: '2026-09-02',
      page: 1,
      size: 20,
    })
    expect(buildFileParams({ keyword: '采购', fileType: 'pdf' })).toEqual({
      q: '采购',
      file_type: 'pdf',
      page: 1,
      size: 20,
    })
  })

  it('审计时间范围校验（必填 / 上限）', () => {
    expect(diffDays('2026-09-01', '2026-09-11')).toBe(10)
    expect(validateLogRange({})).toEqual({ valid: false, message: SEARCH_LOG_RANGE_REQUIRED_TEXT })
    expect(validateLogRange({ start: '2026-01-01', end: '2026-09-01' }).valid).toBe(false)
    expect(validateLogRange({}).message).toBe(SEARCH_LOG_RANGE_REQUIRED_TEXT)
    expect(validateLogRange({ start: '2026-09-01', end: '2026-09-20' }).valid).toBe(true)
    expect(SEARCH_LOG_RANGE_MAX_DAYS).toBe(31)
    expect(validateLogRange({ start: '2026-01-01', end: '2026-09-01' }).message).toBe(SEARCH_LOG_RANGE_EXCEED_TEXT)
  })
})

describe('domain/search 分组与建议', () => {
  const hits = [
    { docType: 'user', bizId: 'u1', title: '甲' },
    { docType: 'user', bizId: 'u2', title: '乙' },
    { docType: 'user', bizId: 'u3', title: '丙' },
    { docType: 'user', bizId: 'u4', title: '丁' },
    { docType: 'dept', bizId: 'd1', title: '研发' },
  ]

  it('按域分组（域清单保序，未知域追加）', () => {
    const groups = groupHits(hits, domains)
    expect(groups.map((group) => group.key)).toEqual(['user', 'dept'])
    expect(groups[0]?.items).toHaveLength(4)
  })

  it('即时建议各域 Top N 并截断总量', () => {
    expect(topHits(hits, 3, 2)).toHaveLength(2)
    expect(topHits(hits, 2, 8).filter((hit) => hit.docType === 'user')).toHaveLength(2)
  })

  it('命中键与跳转目标', () => {
    expect(hitKey({ docType: 'user', bizId: 'u1', title: '甲' })).toBe('user:u1')
    expect(hitRouteTarget({ docType: 'user', bizId: 'u1', title: '甲' })).toEqual({ docType: 'user', bizId: 'u1' })
  })
})

describe('domain/search 最近搜索与降级错误码', () => {
  it('最近搜索去重 / 置顶 / 上限 / 移除', () => {
    let list = normalizeRecentKeywords(['甲', '甲', '', '乙'])
    expect(list).toEqual(['甲', '乙'])
    list = addRecentKeyword(list, '丙')
    expect(list).toEqual(['丙', '甲', '乙'])
    list = addRecentKeyword(list, '甲')
    expect(list).toEqual(['甲', '丙', '乙'])
    list = addRecentKeyword(list, '丁', 2)
    expect(list).toEqual(['丁', '甲'])
    expect(removeRecentKeyword(['甲', '乙'], '甲')).toEqual(['乙'])
  })

  it('降级解析', () => {
    expect(parseDegraded(1)).toBe(true)
    expect(parseDegradeReason('timeout')).toBe('timeout')
    expect(parseDegradeReason('unknown')).toBeUndefined()
  })

  it('错误码判定与文案', () => {
    expect(isSearchErrorCode(10103)).toBe(true)
    expect(isSearchErrorCode(99999)).toBe(false)
    expect(resolveSearchErrorText(10101)).toBe('检索服务不可用')
    expect(resolveSearchErrorText(10107)).toBe('检索时间范围超限')
    expect(resolveSearchErrorText(12345)).toBe('检索失败')
  })
})
