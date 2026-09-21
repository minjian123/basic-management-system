<script setup lang="ts">
// 开发态核对页（07_07）：全局搜索（入口 / 命令面板 / 结果页 / 命中项 / 日志与文件页签）实例 + 13 项自检上屏（本页不进构建产物）。
import { BaseAccess, SEARCH_LOG_RANGE_EXCEED_TEXT, type SearchDomain, type SearchEngineAdapter } from '@bms/core'
import {
  GlobalSearch,
  SearchEntry,
  SearchFileTab,
  SearchHitItem,
  SearchLogTab,
  SearchPalette,
  highlightKeyword,
  sanitizeHighlight,
  useBaseSearch,
} from '@bms/ui-ep'
import { ref } from 'vue'

/** 权限上下文。 */
class CheckAccess extends BaseAccess {}

/** 可检索域。 */
const domains: SearchDomain[] = [
  { key: 'user', label: '用户', perm: 'user:query' },
  { key: 'dept', label: '部门', perm: 'dept:query' },
  { key: 'log', label: '审计日志', perm: 'log:query' },
  { key: 'file_meta', label: '文件', perm: 'file:query' },
]

/** 命中样例。 */
const userHits = [
  { docType: 'user', bizId: 'u1', title: '张三', highlight: '研发中心 · <em>张</em>三', updatedAt: '2026-09-20T10:00:00Z' },
  { docType: 'user', bizId: 'u2', title: '张四', updatedAt: '2026-09-19T10:00:00Z' },
]

/** 引擎调用轨迹。 */
const calls: string[] = []
/** 是否让下一次全局检索降级。 */
let degradeNext = false
/** 是否让下一次全局检索失败。 */
let failNext = false

/** 检索引擎桩。 */
const engine: SearchEngineAdapter = {
  suggest: async () => userHits,
  searchGlobal: async () => {
    calls.push('searchGlobal')
    if (failNext) {
      throw Object.assign(new Error('mock 失败'), { code: 10101 })
    }
    return {
      groups: [{ key: 'user', label: '用户', items: userHits }],
      total: 2,
      degraded: degradeNext,
      degradeReason: degradeNext ? 'fallback' : undefined,
    }
  },
  searchLogs: async (input) => {
    calls.push('searchLogs')
    return {
      items: [{ docType: 'log', bizId: 'l1', title: '操作日志', highlight: `${input.start} 新增用户` }],
      total: 1,
    }
  },
  searchFiles: async () => {
    calls.push('searchFiles')
    return {
      items: [
        { docType: 'file_meta', bizId: 'f1', title: '采购制度.pdf', highlight: '单笔 ≥ 1 万元需审批' },
        { docType: 'file_meta', bizId: 'f2', title: '扫描件.pdf', unsearchable: true },
      ],
      total: 2,
    }
  },
}

const access = new CheckAccess()
access.setCodes(['user:query', 'dept:query', 'log:query', 'file:query'])

const api = useBaseSearch({
  ready: false,
  domains,
  engine,
  access,
  storage: undefined,
})

/** 关键词与当前域（页签）。 */
const keyword = ref('张')
const activeDomain = ref('all')
/** 快捷键是否触发。 */
let shortcutFired = false
api.registerShortcut(() => {
  shortcutFired = true
})

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 运行自检并上屏。
 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  const add = (label: string, pass: boolean): void => {
    result.push({ label, pass })
  }

  // 1. 占位降级与就绪切换
  api.setKeyword('张')
  await api.search()
  const placeholderPass = api.degraded.value && api.requestCount.value === 0
  api.setReady(true)
  add('占位降级且零请求，就绪后不再降级', placeholderPass && !api.degraded.value)

  // 2. 顶栏入口与快捷键
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
  add('快捷键（mod+k）触发命令面板', shortcutFired)

  // 3. 命令面板即时建议
  api.setKeyword('张')
  await api.suggest()
  add('即时建议返回各域 Top N', api.suggestions.value.length > 0)

  // 4. 最近搜索去重 / 上限 / 清除
  api.addRecentKeyword('采购')
  api.addRecentKeyword('张三')
  api.addRecentKeyword('采购')
  const recentPass = api.recentKeywords.value[0] === '采购' && new Set(api.recentKeywords.value).size === api.recentKeywords.value.length
  api.clearRecentKeywords()
  add('最近搜索去重置顶与清除', recentPass && api.recentKeywords.value.length === 0)

  // 5. 结果页多域分组
  await api.search()
  add('多域分组结果渲染', api.groups.value.length > 0 && api.total.value === 2)

  // 6. 高亮与片段清洗
  const title = highlightKeyword('张三', '张')
  const cleaned = sanitizeHighlight('<em>张</em><scr' + 'ipt>alert(1)</scr' + 'ipt>')
  add('关键词高亮与片段白名单清洗', title.includes('<em>') && !cleaned.includes('<script'))

  // 7. 命中项展示与点击上抛
  add('命中项稳定键与跳转目标', api.state.hitKey(userHits[0]!).includes('u1') && api.state.hitTarget(userHits[0]!).bizId === 'u1')

  // 8. 分页与限深
  api.setPage(999)
  add('分页限深夹取 ≤ 100 页', api.page.value === 100)

  // 9. 降级标记与替代入口
  degradeNext = true
  await api.search()
  const degradePass = api.engineDegraded.value && api.fallbackDomains.value.length > 0
  degradeNext = false
  add('降级标记置位且给出替代入口', degradePass)

  // 10. 错误态与重试
  failNext = true
  await api.search()
  const errorPass = api.phase.value === 'error'
  failNext = false
  add('检索失败置错误态（可重试）', errorPass)

  // 11. 审计日志页签（范围必填 / 超限拒绝）
  api.setLogRange({ start: '2026-09-01', end: '2026-09-10' })
  await api.searchLogs()
  const logPass = api.logItems.value.length === 1
  api.setLogRange({ start: '2026-01-01', end: '2026-09-10' })
  const before = api.requestCount.value
  await api.searchLogs()
  const exceedPass = api.requestCount.value === before && api.state.errorMessage === SEARCH_LOG_RANGE_EXCEED_TEXT
  add('审计日志检索（时间范围必填且 ≤ 31 天）', logPass && exceedPass)

  // 12. 文件内容页签（不可检索提示）
  await api.searchFiles()
  add('文件内容检索与不可检索提示', api.fileItems.value.length === 2 && api.fileItems.value.some((hit) => hit.unsearchable === true))

  // 13. 域权限二次过滤
  const filtered = api.accessibleDomains.value.every((domain) => domain.perm === undefined || access.has(domain.perm))
  add('可检索域按权限二次过滤', filtered && api.accessibleDomains.value.length === 4)

  checks.value = result
}

void runChecks()
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>全局搜索核对页（07-7）</h1>
    <section data-check-scope="entry" style="margin-bottom: 16px">
      <SearchEntry :ready="api.ready.value" :model-value="keyword" :domains="domains" @update:model-value="keyword = $event" />
    </section>
    <section data-check-scope="palette" style="margin-bottom: 16px">
      <SearchPalette :model-value="true" :keyword="keyword" :suggestions="api.suggestions.value" :domains="domains" @select="() => {}" @search="() => {}" />
    </section>
    <section data-check-scope="global" style="margin-bottom: 16px">
      <GlobalSearch
        :ready="api.ready.value"
        :model-value="keyword"
        :domains="domains"
        :groups="api.groups.value"
        :total="api.total.value"
        :page="api.page.value"
        :page-size="api.pageSize.value"
        :engine-degraded="api.engineDegraded.value"
        :access="access"
        :show-pagination="true"
        :active-domain="activeDomain"
        @update:model-value="keyword = $event"
        @update:active-domain="activeDomain = $event"
        @search="api.search()"
      />
    </section>
    <section data-check-scope="hit" style="margin-bottom: 16px">
      <SearchHitItem :hit="userHits[0]!" :keyword="keyword" :domains="domains" />
    </section>
    <section data-check-scope="log" style="margin-bottom: 16px">
      <SearchLogTab :ready="api.ready.value" :items="api.logItems.value" :total="api.logTotal.value" />
    </section>
    <section data-check-scope="file" style="margin-bottom: 16px">
      <SearchFileTab :ready="api.ready.value" :items="api.fileItems.value" :total="api.fileTotal.value" />
    </section>
    <section style="margin-top: 16px">
      <button type="button" @click="api.setReady(!api.ready.value)">切换就绪 / 降级</button>
    </section>
    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
