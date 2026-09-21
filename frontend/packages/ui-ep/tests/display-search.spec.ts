// kiwi_id: 961
/** 全局搜索件族与投影用例（07_07）：契约同实现 + 高亮清洗 + 检索引擎 + 六件行为。 */

import { BaseAccess, type SearchEngineAdapter } from '@bms/core'
import {
  createSearchEngineStub,
  describeSearchContract,
  SEARCH_CONTRACT_DOMAINS,
  type SearchContractTarget,
} from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import {
  createHttpSearchEngine,
  GlobalSearch,
  registerSearchEngine,
  sanitizeHighlight,
  SearchEntry,
  SearchFileTab,
  SearchHitItem,
  highlightHit,
  highlightKeyword,
  SearchLogTab,
  SearchPalette,
  searchEngineRegistry,
  useBaseSearch,
} from '../src'

/** 具体权限上下文。 */
class DemoAccess extends BaseAccess {}

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

/** 等待一轮微任务与宏任务。 */
const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

/** 契约目标（投影适配）。 */
function makeTarget(): SearchContractTarget {
  const base = useBaseSearch({ ready: false })
  return {
    get ready() {
      return base.ready.value
    },
    get degraded() {
      return base.degraded.value
    },
    get requestCount() {
      return base.requestCount.value
    },
    get phase() {
      return base.phase.value
    },
    get keyword() {
      return base.keyword.value
    },
    get domains() {
      return base.state.domains
    },
    get accessibleDomains() {
      return base.accessibleDomains.value
    },
    get groups() {
      return base.groups.value
    },
    get total() {
      return base.total.value
    },
    get page() {
      return base.page.value
    },
    get pageSize() {
      return base.pageSize.value
    },
    get suggestions() {
      return base.suggestions.value
    },
    get recentKeywords() {
      return base.recentKeywords.value
    },
    get logItems() {
      return base.logItems.value
    },
    get fileItems() {
      return base.fileItems.value
    },
    get engineDegraded() {
      return base.engineDegraded.value
    },
    setReady: (value) => base.setReady(value),
    setEngine: (engine) => base.setEngine(engine as SearchEngineAdapter | undefined),
    setAccess: (access) => base.setAccess(access as BaseAccess),
    setDomains: (domains) => base.setDomains(domains),
    setKeyword: (value) => base.setKeyword(value),
    setActiveDomain: (key) => base.setActiveDomain(key),
    setPage: (value) => base.setPage(value),
    setPageSize: (size) => base.setPageSize(size),
    setLogType: (value) => base.setLogType(value),
    setLogRange: (range) => base.setLogRange(range),
    setFileType: (value) => base.setFileType(value),
    search: () => base.search(),
    suggest: () => base.suggest(),
    clearSuggestions: () => base.clearSuggestions(),
    searchLogs: () => base.searchLogs(),
    searchFiles: () => base.searchFiles(),
    addRecentKeyword: (value) => base.addRecentKeyword(value),
    removeRecentKeyword: (value) => base.removeRecentKeyword(value),
    clearRecentKeywords: () => base.clearRecentKeywords(),
    dispose: () => base.state.dispose(),
  }
}

describeSearchContract('全局搜索契约（useBaseSearch）', makeTarget)

describe('searchHighlight 高亮与清洗', () => {
  it('关键词高亮先转义再包裹 em', () => {
    expect(highlightKeyword('张三 <b>', '张')).toBe('<em>张</em>三 &lt;b&gt;')
    expect(highlightKeyword('abc', '')).toBe('abc')
  })

  it('白名单清洗剔除脚本与事件属性', () => {
    const cleaned = sanitizeHighlight('<em>张</em><script>alert(1)</script><img src=x onerror=alert(1)>')
    expect(cleaned).toContain('<em>张</em>')
    expect(cleaned).not.toContain('<script')
    expect(cleaned).not.toContain('onerror')
  })

  it('highlightHit 片段优先、标题按关键词高亮', () => {
    const result = highlightHit({ docType: 'user', bizId: 'u1', title: '张三', highlight: '研发<em>中</em>心' }, '张')
    expect(result.title).toContain('<em>张</em>')
    expect(result.summary).toContain('<em>中</em>')
  })
})

describe('searchEngine 内建引擎与注册表', () => {
  it('HTTP 引擎按端点请求并返回结果', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ groups: [], total: 0 }) })
    vi.stubGlobal('fetch', fetchMock)
    const engine = createHttpSearchEngine({ endpoint: '/api/v1', headers: { 'x-token': 't' } })
    await engine.searchGlobal({ keyword: '张', types: ['user'], page: 1, pageSize: 20 })
    const url = fetchMock.mock.calls[0]?.[0] as string
    expect(url).toContain('/api/v1/search/global')
    expect(url).toContain('q=%E5%BC%A0')
    vi.unstubAllGlobals()
  })

  it('HTTP 引擎不可用时降级不抛错', async () => {
    vi.stubGlobal('fetch', undefined)
    const engine = createHttpSearchEngine()
    expect(await engine.searchGlobal({ keyword: 'a', page: 1, pageSize: 20 })).toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('注册表登记自定义引擎', () => {
    const engine = createSearchEngineStub().engine as SearchEngineAdapter
    registerSearchEngine('custom-test', () => engine as never)
    expect(searchEngineRegistry.keys()).toContain('custom-test')
  })
})

describe('SearchHitItem 命中项', () => {
  it('渲染高亮标题与摘要，点击上抛 open', async () => {
    const hit = { docType: 'user', bizId: 'u1', title: '张三', highlight: '研发<em>中</em>心', updatedAt: '2026-09-20' }
    const wrapper = mount(SearchHitItem, { props: { hit, keyword: '张', domains: [{ key: 'user', label: '用户' }] } })
    expect(wrapper.find('[data-test="hit-user-u1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="hit-title"]').html()).toContain('<em>')
    await wrapper.trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual([hit])
  })
})

describe('SearchEntry 顶栏入口', () => {
  it('占位降级；就绪输入与快捷键呼出', async () => {
    const placeholder = mount(SearchEntry, { props: {} })
    expect(placeholder.find('[data-test="search-entry-degrade"]').exists()).toBe(true)

    const wrapper = mount(SearchEntry, { props: { ready: true } })
    await wrapper.find('[data-test="search-entry-input"]').setValue('张')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['张'])

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    expect(wrapper.emitted('open-panel')).toBeTruthy()
  })
})

describe('SearchPalette 命令面板', () => {
  it('键盘导航与选中；最近搜索与查看全部', async () => {
    const suggestions = [
      { docType: 'user', bizId: 'u1', title: '张三' },
      { docType: 'user', bizId: 'u2', title: '张四' },
    ]
    const wrapper = mount(SearchPalette, {
      props: { modelValue: true, keyword: '张', suggestions, recentKeywords: ['采购'] },
    })
    const input = wrapper.find('[data-test="search-palette-keyword"]')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')?.[0]).toEqual([suggestions[1]])
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()

    await wrapper.find('[data-test="palette-recent-0"]').trigger('click')
    expect(wrapper.emitted('recent-select')?.[0]).toEqual(['采购'])
    await wrapper.find('[data-test="palette-view-all"]').trigger('click')
    expect(wrapper.emitted('search')?.[0]).toEqual(['张'])
  })
})

describe('SearchLogTab 审计日志页签', () => {
  it('范围不合法不触发检索；合法可检索', async () => {
    const wrapper = mount(SearchLogTab, { props: { ready: true, items: [{ docType: 'log', bizId: 'l1', title: '操作日志' }] } })
    await wrapper.find('[data-test="log-search"]').trigger('click')
    expect(wrapper.emitted('search')).toBeFalsy()

    await wrapper.find('[data-test="log-range-start"]').setValue('2026-09-01')
    await wrapper.find('[data-test="log-range-end"]').setValue('2026-09-10')
    expect(wrapper.find('[data-test="log-range-error"]').exists()).toBe(false)
    await wrapper.find('[data-test="log-search"]').trigger('click')
    expect(wrapper.emitted('search')).toHaveLength(1)
  })
})

describe('SearchFileTab 文件内容页签', () => {
  it('不可检索文件给出提示', () => {
    const wrapper = mount(SearchFileTab, {
      props: { ready: true, items: [{ docType: 'file_meta', bizId: 'f1', title: 'a.pdf', unsearchable: true }] },
    })
    expect(wrapper.find('[data-test="file-unsearchable"]').exists()).toBe(true)
  })
})

describe('GlobalSearch 结果页容器', () => {
  it('注入引擎后件内驱动检索并渲染分组', async () => {
    const stub = createSearchEngineStub()
    const wrapper = mount(GlobalSearch, {
      props: {
        ready: true,
        domains: SEARCH_CONTRACT_DOMAINS.filter((domain) => domain.key === 'user'),
        engine: stub.engine as SearchEngineAdapter,
      },
    })
    await wrapper.find('[data-test="keyword"]').setValue('张')
    await wrapper.find('[data-test="search"]').trigger('click')
    await flush()
    expect(stub.calls).toContain('searchGlobal')
    expect(wrapper.find('[data-test="hit-user-u1"]').exists()).toBe(true)
  })

  it('降级条替代入口上抛 fallback', async () => {
    const wrapper = mount(GlobalSearch, {
      props: { ready: true, engineDegraded: true, domains: [{ key: 'user', label: '用户', perm: 'user:query' }] },
    })
    await wrapper.find('[data-test="fallback"]').trigger('click')
    expect(wrapper.emitted('fallback')?.[0]?.[0]).toEqual([{ key: 'user', label: '用户', perm: 'user:query' }])
  })

  it('log:query / file:query 时展示审计日志与文件页签', async () => {
    const noAccess = mount(GlobalSearch, {
      props: { ready: true, domains: [{ key: 'user', label: '用户' }] },
    })
    expect(noAccess.find('[data-test="log-tab"]').exists()).toBe(false)

    const withAccess = mount(GlobalSearch, {
      props: {
        ready: true,
        domains: [{ key: 'user', label: '用户' }],
        access: accessOf(['log:query', 'file:query']),
      },
    })
    await flush()
    expect(withAccess.find('[data-test="log-tab"]').exists()).toBe(true)
    expect(withAccess.find('[data-test="file-tab"]').exists()).toBe(true)
  })
})
