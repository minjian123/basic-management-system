// kiwi_id: 958
/** 通用表格用例（07_05）：表格契约 + 占位契约 + 列设置 / 多列排序 / 多选 / 树形 / 行内编辑 / 展开行 / 虚拟滚动 / 三态。 */

import {
  describePlaceholderDisplayContract,
  describeTableContract,
  type PlaceholderDisplayContractTarget,
  type TableContractTarget,
} from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { DataTable, useBaseTable } from '../src'

/** 契约目标：表格基类投影。 */
function makeTableTarget(): TableContractTarget {
  const api = useBaseTable()
  return {
    get rows() {
      return api.rows.value
    },
    get total() {
      return api.total.value
    },
    get page() {
      return api.page.value
    },
    get pageSize() {
      return api.pageSize.value
    },
    get sorts() {
      return api.sorts.value
    },
    get listDensity() {
      return api.listDensity.value
    },
    get densityToken() {
      return api.table.densityToken
    },
    get selectedKeys() {
      return api.selectedKeys.value
    },
    get columnKeys() {
      return api.table.columnConfig.visibleOrder
    },
    get expandedKeys() {
      return api.expandedKeys.value
    },
    setRows: (rows, total) => api.setRows(rows, total),
    setPage: (page) => api.setPage(page),
    setPageSize: (size) => api.setPageSize(size),
    resetToFirstPage: () => api.resetToFirstPage(),
    toggleSort: (column, additive) => api.toggleSort(column, additive),
    sortParams: () => api.table.sortParams(),
    setListDensity: (density) => api.setListDensity(density),
    setVisible: (key, visible) => api.setVisible(key, visible),
    normalizeColumns: (seeds) => api.table.columnConfig.normalizeWith(seeds),
    toggleSelect: (key) => api.toggleSelect(key),
    toggleExpand: (key) => api.toggleExpand(key),
    expandAll: () => api.expandAll(),
    collapseAll: () => api.collapseAll(),
  }
}

/** 契约目标：占位语义（07_01 冻结契约继续跑同一套件）。 */
function makePlaceholderTarget(): PlaceholderDisplayContractTarget {
  const api = useBaseTable()
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    setReady: (value) => api.setReady(value),
    load: () => api.markLoaded(),
  }
}

describeTableContract('表格契约（useBaseTable）', makeTableTarget)
describePlaceholderDisplayContract('占位展示契约（useBaseTable）', makePlaceholderTarget)

/** 列声明样例。 */
const columns = [
  { key: 'name', title: '名称' },
  { key: 'status', title: '状态', status: true },
  { key: 'amount', title: '金额', sortable: true, format: 'amount' as const },
]

/** 行数据样例。 */
const rows = [
  { id: '1', name: '甲', status: 'enabled', amount: 10 },
  { id: '2', name: '乙', status: 'pending', amount: 20 },
]

describe('DataTable 列设置与工具栏', () => {
  it('列设置抽屉：显隐切换与列宽重置并上抛列变更', async () => {
    const wrapper = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2 } })
    expect(wrapper.find('[data-test="settings-panel"]').exists()).toBe(false)

    await wrapper.find('[data-test="column-settings"]').trigger('click')
    expect(wrapper.find('[data-test="settings-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="settings-item-name"]').exists()).toBe(true)

    await wrapper.find('[data-test="settings-visible-status"]').trigger('change')
    expect(wrapper.find('[data-test="settings-item-status"]').text()).toContain('状态')
    expect(wrapper.emitted('column-change')?.length).toBe(1)

    await wrapper.find('[data-test="settings-move-name"]').trigger('click')
    await wrapper.find('[data-test="settings-width-reset-amount"]').trigger('click')
    await wrapper.find('[data-test="settings-reset"]').trigger('click')
    expect(wrapper.emitted('column-change')?.length).toBe(4)
  })

  it('工具栏：刷新 / 密度 / 自动列宽 / 全屏', async () => {
    const wrapper = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2 } })
    expect(wrapper.attributes('data-density')).toBe('default')

    await wrapper.find('[data-test="refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)

    await wrapper.find('[data-test="density"]').trigger('click')
    expect(wrapper.emitted('update:density')?.[0]).toEqual(['small'])
    expect(wrapper.attributes('data-density')).toBe('compact')

    await wrapper.find('[data-test="auto-width"]').trigger('click')
    expect(wrapper.emitted('column-change')?.length).toBeGreaterThan(0)

    await wrapper.find('[data-test="fullscreen"]').trigger('click')
    expect(wrapper.classes()).toContain('is-fullscreen')
  })
})

describe('DataTable 多列排序', () => {
  it('点击表头排序；Shift 叠加多列并显示优先级序号', async () => {
    const sortable = [
      { key: 'a', title: 'A', sortable: true },
      { key: 'b', title: 'B', sortable: true },
    ]
    const wrapper = mount(DataTable, { props: { ready: true, columns: sortable, data: rows, total: 2 } })
    const headers = wrapper.findAll('th')
    expect(headers).toHaveLength(2)

    await headers[0]?.trigger('click')
    expect(wrapper.emitted('sort-change')?.[0]).toEqual([{ prop: 'a', order: 'asc' }])
    expect(wrapper.emitted('sorts-change')?.[0]).toEqual([[{ prop: 'a', order: 'asc' }]])
    expect(wrapper.find('[data-test="sort-index-a"]').text()).toBe('1')

    await headers[1]?.trigger('click', { shiftKey: true })
    expect(wrapper.emitted('sorts-change')?.[1]).toEqual([
      [
        { prop: 'a', order: 'asc' },
        { prop: 'b', order: 'asc' },
      ],
    ])
    expect(wrapper.find('[data-test="sort-index-b"]').text()).toBe('2')

    const plain = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2 } })
    const plainHeaders = plain.findAll('th')
    await plainHeaders[2]?.trigger('click')
    expect(plain.emitted('sort-change')?.[0]).toEqual([{ prop: 'amount', order: 'asc' }])
  })
})

describe('DataTable 多选与选择摘要', () => {
  it('全选当前页与取消全选并上抛选中与摘要', async () => {
    const wrapper = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2, selectable: true } })
    expect(wrapper.find('[data-test="selection-summary"]').text()).toContain('已选 0 条')

    await wrapper.find('[data-test="select-all"]').trigger('change')
    expect(wrapper.emitted('selection-change')?.[0]).toEqual([['1', '2']])
    expect(wrapper.emitted('selection-summary')?.[0]).toEqual([
      { count: 2, total: 2, allAcrossPages: false, mode: 'page' },
    ])
    expect(wrapper.find('[data-test="selection-summary"]').text()).toContain('已选 2 条')

    await wrapper.find('[data-test="select-all"]').trigger('change')
    expect(wrapper.emitted('selection-change')?.[1]).toEqual([[]])
  })

  it('行内复选框切换选中', async () => {
    const wrapper = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2, selectable: true } })
    const boxes = wrapper.findAll('tbody input[type="checkbox"]')
    await boxes[0]?.trigger('change')
    expect(wrapper.emitted('selection-change')?.[0]).toEqual([['1']])
  })
})

describe('DataTable 树形 / 展开行 / 行内编辑', () => {
  const treeRows = [
    { id: '1', name: '父', children: [{ id: '1-1', name: '子' }] },
    { id: '2', name: '叶' },
  ]

  it('树形：默认收起，点击箭头展开子节点', async () => {
    const wrapper = mount(DataTable, {
      props: { ready: true, columns, data: treeRows, total: 2, tree: true, rowKey: 'id' },
    })
    expect(wrapper.find('[data-test="row-1-1"]').exists()).toBe(false)

    await wrapper.find('[data-test="tree-toggle-1"]').trigger('click')
    expect(wrapper.find('[data-test="row-1-1"]').exists()).toBe(true)
    expect(wrapper.emitted('expand-change')?.[0]).toEqual([['1']])
  })

  it('展开行：展开区渲染插槽内容', async () => {
    const wrapper = mount(DataTable, {
      props: { ready: true, columns, data: rows, total: 2, expandable: true },
      slots: { expand: '<p data-test="detail">明细</p>' },
    })
    await wrapper.find('[data-test="expand-toggle-1"]').trigger('click')
    expect(wrapper.find('[data-test="expanded-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="detail"]').text()).toBe('明细')
  })

  it('行内编辑：单元格渲染输入并上抛变更', async () => {
    const wrapper = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2, editable: true } })
    const input = wrapper.find('[data-test="cell-input-1-name"]')
    expect(input.exists()).toBe(true)
    await input.setValue('甲改')
    await input.trigger('change')
    expect(wrapper.emitted('cell-change')?.[0]).toEqual([{ row: rows[0], column: columns[0], value: '甲改' }])
  })
})

describe('DataTable 虚拟滚动', () => {
  it('阈值 200 行显式开启后走窗口化渲染', () => {
    const bigRows = Array.from({ length: 250 }, (_item, index) => ({ id: String(index), name: `行${index}` }))
    const wrapper = mount(DataTable, {
      props: { ready: true, columns, data: bigRows, total: 250, virtual: true, rowHeight: 44, virtualHeight: 360 },
    })
    expect(wrapper.find('[data-test="virtual-scroll"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="data-table"]').exists()).toBe(false)
    const rendered = wrapper.findAll('[data-test^="row-"]')
    expect(rendered.length).toBeGreaterThan(0)
    expect(rendered.length).toBeLessThan(40)
  })

  it('与树形互斥时回落普通模式', () => {
    const bigRows = Array.from({ length: 250 }, (_item, index) => ({ id: String(index), name: `行${index}` }))
    const wrapper = mount(DataTable, {
      props: { ready: true, columns, data: bigRows, total: 250, virtual: true, tree: true },
    })
    expect(wrapper.find('[data-test="virtual-scroll"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="data-table"]').exists()).toBe(true)
  })
})

describe('DataTable 状态视图', () => {
  it('首屏骨架 / 遮罩 / 错误重试 / 搜索无结果', async () => {
    const first = mount(DataTable, { props: { ready: true, columns, data: [], firstLoad: true, loading: true } })
    expect(first.find('[data-test="skeleton"]').exists()).toBe(true)

    const loading = mount(DataTable, { props: { ready: true, columns, data: rows, total: 2, loading: true } })
    expect(loading.find('[data-test="overlay"]').exists()).toBe(true)

    const failed = mount(DataTable, { props: { ready: true, columns, data: [], error: '加载失败' } })
    expect(failed.find('[data-test="error"]').text()).toContain('加载失败')
    await failed.find('[data-test="retry"]').trigger('click')
    expect(failed.emitted('retry')).toHaveLength(1)

    const empty = mount(DataTable, { props: { ready: true, columns, data: [], searchActive: true } })
    expect(empty.find('[data-test="empty"]').text()).toContain('未找到相关内容')
    await empty.find('[data-test="empty-clear"]').trigger('click')
    expect(empty.emitted('clear-filter')).toHaveLength(1)
  })

  it('双击行 / 状态列标签 / 脱敏列 / 格式化列', async () => {
    const wrapper = mount(DataTable, {
      props: { ready: true, columns, data: rows, total: 2 },
    })
    await wrapper.find('[data-test="row-1"]').trigger('dblclick')
    expect(wrapper.emitted('row-dblclick')?.[0]).toEqual([rows[0]])
    expect(wrapper.find('[data-test="row-1"] [data-test="status-tag"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('¥10.00')

    const masked = mount(DataTable, {
      props: {
        ready: true,
        columns: [{ key: 'phone', title: '手机号', mask: true }],
        data: [{ id: '1', phone: '13800001111' }],
        total: 1,
      },
    })
    expect(masked.text()).toContain('***')
    const plain = mount(DataTable, {
      props: {
        ready: true,
        columns: [{ key: 'phone', title: '手机号', mask: true }],
        data: [{ id: '1', phone: '13800001111' }],
        total: 1,
        plainEnabled: true,
      },
    })
    expect(plain.text()).toContain('13800001111')

    const dict = mount(DataTable, {
      props: {
        ready: true,
        columns: [{ key: 'status', title: '状态', dictType: 'sys_status' }],
        data: [{ id: '1', status: 'enabled' }],
        total: 1,
        translator: () => '启用',
      },
    })
    expect(dict.text()).toContain('启用')
  })
})
