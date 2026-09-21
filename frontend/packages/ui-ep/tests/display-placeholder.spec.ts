// kiwi_id: 971
/** 占位版展示件用例（07_01）：契约套件 + 六件降级 / 就绪行为。 */

import { describePlaceholderDisplayContract, type PlaceholderDisplayContractTarget } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import {
  AuditDiff,
  ChartCard,
  DataTable,
  FilePreview,
  GlobalSearch,
  NoticeList,
  useDisplayPlaceholder,
} from '../src'

/** 契约目标：占位组合式投影。 */
function makeTarget(): PlaceholderDisplayContractTarget {
  const display = useDisplayPlaceholder()
  return {
    get ready() {
      return display.ready.value
    },
    get degraded() {
      return display.degraded.value
    },
    get requestCount() {
      return display.requestCount.value
    },
    setReady: (value) => display.setReady(value),
    load: () => display.markLoaded(),
  }
}

describePlaceholderDisplayContract('占位展示契约（useDisplayPlaceholder）', makeTarget)

describe('占位展示组合式', () => {
  it('就绪后才允许计入加载，值经展示基类投影', () => {
    const display = useDisplayPlaceholder()
    display.markLoaded()
    expect(display.requestCount.value).toBe(0)
    display.setReady(true)
    display.markLoaded()
    expect(display.requestCount.value).toBe(1)

    display.setValue('甲')
    expect(display.value.value).toBe('甲')
  })
})

describe('DataTable 通用表格', () => {
  it('占位态降级且不渲染表格', () => {
    const wrapper = mount(DataTable, { props: { columns: [{ key: 'name', title: '名称' }] } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('表格数据未就绪')
    expect(wrapper.find('[data-test="data-table"]').exists()).toBe(false)
  })

  it('就绪态渲染行、空态与分页事件', async () => {
    const columns = [
      { key: 'name', title: '名称' },
      { key: 'amount', title: '金额', sortable: true },
    ]
    const data = [{ id: '1', name: '甲', amount: 10 }]
    const wrapper = mount(DataTable, { props: { ready: true, columns, data, total: 25, page: 1 } })
    expect(wrapper.attributes('data-degraded')).toBe('false')
    expect(wrapper.find('[data-test="row-1"]').text()).toContain('甲')

    await wrapper.findAll('th')[1].trigger('click')
    expect(wrapper.emitted('sort-change')?.[0]).toEqual([{ prop: 'amount', order: 'asc' }])

    await wrapper.find('[data-test="row-1"]').trigger('click')
    expect(wrapper.emitted('row-click')?.[0]).toEqual([data[0]])

    await wrapper.find('[data-test="next"]').trigger('click')
    expect(wrapper.emitted('update:page')?.[0]).toEqual([2])

    const empty = mount(DataTable, { props: { ready: true, columns, data: [] } })
    expect(empty.find('[data-test="empty"]').exists()).toBe(true)
  })
})

describe('NoticeList 通知列表', () => {
  const items = [
    { id: 'n1', title: '审批待办', type: 'todo' as const, read: false, createdAt: '2026-09-18' },
    { id: 'n2', title: '系统提示', type: 'system' as const, read: true, createdAt: '2026-09-17' },
  ]

  it('占位态降级，就绪态渲染列表并可操作', async () => {
    const placeholder = mount(NoticeList, { props: {} })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('通知数据未就绪')

    const wrapper = mount(NoticeList, { props: { ready: true, items, unreadCount: 1 } })
    expect(wrapper.find('[data-test="unread-count"]').text()).toContain('1')
    expect(wrapper.find('[data-test="notice-n1"]').exists()).toBe(true)

    await wrapper.find('[data-test="notice-n1"]').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual([items[0]])

    await wrapper.find('[data-test="mark-read"]').trigger('click')
    expect(wrapper.emitted('read')?.[0]).toEqual(['n1'])

    await wrapper.find('[data-test="remove"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]).toEqual(['n1'])

    await wrapper.find('[data-test="read-all"]').trigger('click')
    expect(wrapper.emitted('read-all')).toHaveLength(1)
  })
})

describe('FilePreview 文件预览', () => {
  const files = [
    { id: 'f1', name: 'a.png', mimeType: 'image/png' },
    { id: 'f2', name: 'b.pdf', mimeType: 'application/pdf' },
    { id: 'f3', name: 'c.zip', mimeType: 'application/zip' },
  ]

  it('占位态降级，就绪态按类型渲染并切换', async () => {
    const placeholder = mount(FilePreview, { props: {} })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('文件预览未就绪')

    const wrapper = mount(FilePreview, { props: { ready: true, files, index: 0 } })
    expect(wrapper.attributes('data-kind')).toBe('image')
    expect(wrapper.find('[data-test="file-name"]').text()).toBe('a.png')

    await wrapper.find('[data-test="next"]').trigger('click')
    expect(wrapper.emitted('update:index')?.[0]).toEqual([1])
    expect(wrapper.emitted('change')?.[0]).toEqual([files[1], 1])

    await wrapper.find('[data-test="download"]').trigger('click')
    expect(wrapper.emitted('download')?.[0]).toEqual([files[0]])

    await wrapper.find('[data-test="close"]').trigger('click')
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
    expect(wrapper.emitted('close')).toHaveLength(1)

    const other = mount(FilePreview, { props: { ready: true, files, index: 2 } })
    expect(other.attributes('data-kind')).toBe('other')
  })
})

describe('AuditDiff 审计差异查看', () => {
  const records = [
    { id: 'r1', tableName: 'sys_user', recordId: '1', fields: 2, operator: '张三', chainStatus: 'valid' as const },
  ]

  it('占位态降级，就绪态渲染记录与操作', async () => {
    const placeholder = mount(AuditDiff, { props: {} })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('审计数据未就绪')

    const wrapper = mount(AuditDiff, { props: { ready: true, records, total: 1 } })
    expect(wrapper.find('[data-test="record-r1"]').text()).toContain('sys_user')

    await wrapper.find('[data-test="record-r1"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([records[0]])

    await wrapper.find('[data-test="query"]').trigger('click')
    expect(wrapper.emitted('query')).toHaveLength(1)

    await wrapper.find('[data-test="verify"]').trigger('click')
    expect(wrapper.emitted('verify')).toHaveLength(1)

    await wrapper.find('[data-test="next"]').trigger('click')
    expect(wrapper.emitted('update:page')?.[0]).toEqual([2])
  })
})

describe('ChartCard 图表卡', () => {
  it('占位态降级，就绪态渲染卡头与图表', async () => {
    const placeholder = mount(ChartCard, { props: { title: '销售趋势' } })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('图表数据未就绪')

    const wrapper = mount(ChartCard, { props: { ready: true, title: '销售趋势', chartType: 'bar' } })
    expect(wrapper.find('[data-test="title"]').text()).toBe('销售趋势')
    expect(wrapper.find('[data-test="chart"]').attributes('data-chart-type')).toBe('bar')

    await wrapper.find('[data-test="refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)

    await wrapper.find('[data-test="download"]').trigger('click')
    expect(wrapper.emitted('download')).toHaveLength(1)

    await wrapper.find('[data-test="chart"]').trigger('click')
    expect(wrapper.emitted('chart-click')).toHaveLength(1)
  })
})

describe('GlobalSearch 全局搜索', () => {
  const groups = [
    {
      key: 'user',
      label: '用户',
      items: [{ docType: 'user', bizId: '1', title: '张三' }],
    },
  ]

  it('占位态降级，就绪态可搜索、展示降级条与命中', async () => {
    const placeholder = mount(GlobalSearch, { props: {} })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('搜索服务未就绪')

    const wrapper = mount(GlobalSearch, {
      props: { ready: true, domains: [{ key: 'user', label: '用户' }], groups, engineDegraded: true },
    })
    expect(wrapper.find('[data-test="domain-user"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="engine-degraded"]').exists()).toBe(true)

    await wrapper.find('[data-test="keyword"]').setValue('张')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['张'])

    await wrapper.find('[data-test="search"]').trigger('click')
    expect(wrapper.emitted('search')?.[0]).toEqual(['张'])

    await wrapper.find('[data-test="hit-user-1"]').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual([groups[0].items[0]])

    await wrapper.find('[data-test="retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
