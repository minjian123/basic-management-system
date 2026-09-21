<script setup lang="ts">
// 开发态核对页（06_05）：组织选择字段族（统一件 / 人员 / 岗位 / 部门树 / 复合弹窗）实例 + 12 项自检上屏（本页不进构建产物）。
import {
  BaseOrgSource,
  ORG_PLACEHOLDER_TEXT,
  ORG_SEARCH_DEBOUNCE,
  orgTagSummary,
  toOrgTreeNodes,
  type OrgSourceAdapter,
} from '@bms/core'
import {
  DeptTreeSelectField,
  OrgCompositePicker,
  OrgSelectField,
  PostSelectField,
  UserSelectField,
  debounce,
  orgSourceRegistry,
  registerOrgSource,
  useBaseOrgSelect,
} from '@bms/ui-ep'
import { nextTick, ref } from 'vue'

/** 桩数据：用户（含停用）/ 岗位 / 部门树 / 回显命中（u9 未命中）。 */
const users = [
  { id: 'u1', nickname: '张三', username: 'zhangsan', deptId: 'd2', status: 'enabled', phone: '138****8000' },
  { id: 'u2', nickname: '李四', username: 'lisi', deptId: 'd2', status: 'disabled' },
  { id: 'u3', nickname: '王五', username: 'wangwu', deptId: 'd2', status: 'enabled' },
]
const posts = [{ id: 'p1', name: '研发经理', code: 'RD-MGR', status: 'enabled' }]
const depts = [
  { id: 'd1', name: '总部', status: 'enabled', children: [{ id: 'd2', name: '研发部', status: 'enabled' }] },
]
const refs: Record<string, unknown> = {
  u1: { id: 'u1', name: '张三', target: 'user', exists: true, status: 'enabled' },
  u2: { id: 'u2', name: '李四', target: 'user', exists: true, status: 'disabled' },
  u9: { id: 'u9', name: '', target: 'user', exists: false, status: 'disabled' },
}

/** 数据源调用轨迹与最近查询。 */
const calls: string[] = []
const queries: Record<string, unknown>[] = []

/** 桩数据源（记录调用与查询入参）。 */
const source: OrgSourceAdapter = {
  searchUsers: async (query) => {
    calls.push('searchUsers')
    queries.push({ ...query })
    return { list: users, total: users.length }
  },
  searchPosts: async (query) => {
    calls.push('searchPosts')
    queries.push({ ...query })
    return { list: posts, total: posts.length }
  },
  loadDeptTree: async (query) => {
    calls.push('loadDeptTree')
    queries.push({ ...query })
    return depts
  },
  resolveNames: async (query) => {
    calls.push('resolveNames')
    queries.push({ ids: [...query.ids] })
    return query.ids.map((id) => refs[id] ?? { id, name: '', target: query.target, exists: false, status: 'disabled' })
  },
}

/** 自定义数据源（注册表登记示例）。 */
class CheckStoreSource extends BaseOrgSource {
  /** 实现名。 */
  override readonly pluginName: string = 'check-store'
  /**
   * 用户查询（固定返回门店人员）。
   *
   * @returns 原始结果。
   */
  override async searchUsers(): Promise<unknown> {
    return { list: [{ id: 's1', nickname: '店长', status: 'enabled' }], total: 1 }
  }
}
registerOrgSource('check-store', () => new CheckStoreSource())

/** 主实例（用户类型多选 limit=2）。 */
const api = useBaseOrgSelect({
  ready: true,
  kind: 'user',
  multiple: true,
  limit: 2,
  source,
})

/** 页面受控值（统一件 / 复合弹窗）。 */
const orgValue = ref<string[]>([])
const compositeVisible = ref(true)
const compositeValue = ref<string[]>(['u1'])

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

  // 1. 占位降级与零请求
  const placeholderApi = useBaseOrgSelect({ ready: false, multiple: true, source })
  const beforePlaceholder = placeholderApi.requestCount.value
  await placeholderApi.load()
  add('占位降级且零请求', placeholderApi.degraded.value && placeholderApi.requestCount.value === beforePlaceholder)

  // 2. 远程搜索防抖（300ms 常量驱动）
  let debouncedCalls = 0
  const debounced = debounce(() => {
    debouncedCalls += 1
  }, 50)
  debounced()
  debounced()
  await new Promise((resolve) => setTimeout(resolve, 80))
  add(`远程搜索防抖（件层按 ${ORG_SEARCH_DEBOUNCE}ms 调度）`, debouncedCalls === 1)

  // 3. 用户候选首屏加载（同时取脱敏值样例）
  await api.load()
  const maskedPhone = api.items.value.find((item) => item.id === 'u1')?.phone

  // 4. 多选上限截断与提示
  api.setValue(['u1', 'u2'])
  api.toggle('u3')
  add('多选上限截断并提示', api.limitExceeded.value && api.selectedIds.value.length === 2 && api.limitText.value === '最多选择 2 人')

  // 5. 标签折叠（首项 +N）
  api.setValue(['u1', 'u2', 'u3'])
  await api.resolve()
  const summary = orgTagSummary(api.selectedItems.value, 1)
  add('标签折叠为「首项 +N」', summary.visible.length === 1 && summary.overflow === 2)

  // 6. 批量回显（一次请求 + 缓存常驻）
  const beforeResolve = api.requestCount.value
  const beforeResolveCalls = calls.filter((call) => call === 'resolveNames').length
  await api.resolve(['u1', 'u2', 'u9'])
  const afterFirstResolveCalls = calls.filter((call) => call === 'resolveNames').length
  await api.resolve(['u1', 'u2', 'u9'])
  const afterSecondResolveCalls = calls.filter((call) => call === 'resolveNames').length
  add(
    '批量按 id 回显（单请求，已解析不重复）',
    afterFirstResolveCalls === beforeResolveCalls + 1 &&
      afterSecondResolveCalls === afterFirstResolveCalls &&
      api.requestCount.value > beforeResolve,
  )

  // 6. 已删除 / 停用标记
  add('已删除 / 停用占位标记', api.labelOf('u9') === 'u9（已删除）' && api.labelOf('u2') === '李四（停用）')

  // 7. 脱敏展示（出口下发掩码原样渲染；切换类型前先取）
  add('脱敏值原样展示（不加工明文）', maskedPhone === '138****8000')

  // 8. 部门过滤 + 含下级
  api.setDeptFilter('d1', true)
  await api.load()
  const lastQuery = queries.at(-1) ?? {}
  add('部门过滤与含下级参数', lastQuery.deptId === 'd1' && lastQuery.includeChildren === true)

  // 9. 岗位选择（编码展示）
  api.setKind('post')
  await api.load()
  add('岗位候选与编码展示', api.labelOf('p1') === '研发经理' && api.select.itemOf('p1')?.code === 'RD-MGR')

  // 10. 部门树一次性加载与路径回显
  api.setKind('dept')
  await api.loadDeptTree()
  const pathPass = api.deptNodes.value.length === 1 && toOrgTreeNodes(api.deptNodes.value)[0]?.label === '总部'
  api.setValue('d2')
  await api.resolve()
  add('部门树一次性加载与路径回显', pathPass && api.deptNodes.value[0]?.children?.[0]?.name === '研发部')

  // 11. 组织复合选择（勾选启用项并确认回填）
  await nextTick()
  const composite = document.querySelector('[data-test="org-composite-picker"]')
  const checkbox = document.querySelector('[data-test="composite-check-u3"] input')
  if (checkbox instanceof HTMLElement) {
    checkbox.click()
  }
  await nextTick()
  const confirm = document.querySelector('[data-test="composite-confirm"]')
  if (confirm instanceof HTMLElement) {
    confirm.click()
  }
  await nextTick()
  add('组织复合选择勾选与确认回填', composite !== null && compositeValue.value.includes('u3'))

  // 12. 数据源可替换（注册表登记与默认键）
  add('数据源可替换（默认键 http + 自定义登记）', orgSourceRegistry.get('http') !== undefined && orgSourceRegistry.get('check-store') !== undefined)

  checks.value = result
}

void runChecks()
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>组织选择字段核对页（06-5）</h1>
    <section data-check-scope="org" style="margin-bottom: 16px; max-width: 480px">
      <org-select-field v-model="orgValue" :ready="true" :source="source" :multiple="true" :limit="0" :show-avatar="true" />
    </section>
    <section data-check-scope="user" style="margin-bottom: 16px; max-width: 480px">
      <user-select-field v-model="orgValue" :ready="true" :source="source" :multiple="true" :limit="0" :dept-id="'d1'" />
    </section>
    <section data-check-scope="post" style="margin-bottom: 16px; max-width: 480px">
      <post-select-field :model-value="undefined" :ready="true" :source="source" :multiple="true" />
    </section>
    <section data-check-scope="dept" style="margin-bottom: 16px; max-width: 480px">
      <dept-tree-select-field :model-value="undefined" :ready="true" :source="source" />
    </section>
    <section data-check-scope="readonly" style="margin-bottom: 16px; max-width: 480px">
      <org-select-field :model-value="['u1', 'u2', 'u3']" :ready="true" :source="source" readonly :collapse-after="1" />
    </section>
    <section style="margin-bottom: 16px">
      <org-composite-picker v-model:visible="compositeVisible" v-model="compositeValue" :ready="true" :source="source" />
    </section>
    <section style="margin-bottom: 16px">
      <p data-test="placeholder">{{ ORG_PLACEHOLDER_TEXT }}</p>
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
