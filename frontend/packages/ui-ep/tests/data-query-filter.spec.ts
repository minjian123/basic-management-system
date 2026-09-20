// kiwi_id: 958
/** 查询筛选区用例（07_05）：查询方案契约 + 占位 + 折叠与窄屏 + 查询·重置 + 条件摘要 + 方案 + 高级入口。 */

import { describeQuerySchemeContract, type QuerySchemeContractTarget } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { QueryFilter, useBaseQueryScheme, type QueryFilterSearchPayload } from '../src'

/** 契约目标：查询方案基类投影。 */
function makeTarget(): QuerySchemeContractTarget {
  const api = useBaseQueryScheme()
  return {
    get conditions() {
      return api.conditions.value
    },
    get keyword() {
      return api.keyword.value
    },
    get schemes() {
      return api.schemes.value
    },
    get activeScheme() {
      return api.activeScheme.value
    },
    get defaultSchemeName() {
      return api.defaultSchemeName.value
    },
    setConditions: (conditions) => api.setConditions(conditions),
    setKeyword: (value) => api.setKeyword(value),
    resetConditions: () => api.resetConditions(),
    queryParams: () => api.queryParams.value,
    prune: (fields) => api.scheme.prune(fields),
    setSchemes: (schemes) => api.setSchemes(schemes),
    saveScheme: (entry) => api.scheme.saveScheme({ ...entry, conditions: [...entry.conditions] }),
    applyScheme: (name) => api.applyScheme(name),
    removeScheme: (name) => api.removeScheme(name),
    renameScheme: (oldName, newName) => api.renameScheme(oldName, newName),
    setDefaultScheme: (name) => api.setDefaultScheme(name),
  }
}

describeQuerySchemeContract('查询方案契约（useBaseQueryScheme）', makeTarget)

/** 字段声明样例。 */
const fields = [
  { key: 'status', label: '状态', type: 'select' as const, options: [{ label: '启用', value: 'enabled' }] },
  { key: 'amount', label: '金额', type: 'number' as const },
  { key: 'created', label: '创建时间', type: 'date' as const },
  { key: 'dept', label: '部门', type: 'dept' as const },
]

describe('QueryFilter 占位与折叠', () => {
  it('未就绪时降级且不发请求', () => {
    const wrapper = mount(QueryFilter, { props: { fields } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('查询条件未就绪')
    expect(wrapper.find('[data-test="search"]').exists()).toBe(false)
  })

  it('条件数超阈值默认折叠，可展开收起', async () => {
    const wrapper = mount(QueryFilter, { props: { ready: true, fields } })
    expect(wrapper.attributes('data-collapsed')).toBe('true')
    expect(wrapper.find('[data-test="field-dept"]').attributes('style')).toContain('display: none')

    await wrapper.find('[data-test="collapse-toggle"]').trigger('click')
    expect(wrapper.attributes('data-collapsed')).toBe('false')
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([false])
    expect(wrapper.find('[data-test="field-dept"]').attributes('style') ?? '').not.toContain('display: none')
  })

  it('窄屏仅保留关键字', () => {
    const wrapper = mount(QueryFilter, { props: { ready: true, fields, viewportWidth: 800 } })
    expect(wrapper.attributes('data-narrow')).toBe('true')
    expect(wrapper.find('[data-test="field-status"]').attributes('style')).toContain('display: none')
    expect(wrapper.find('[data-test="keyword"]').exists()).toBe(true)
  })
})

describe('QueryFilter 查询 / 重置 / 条件摘要', () => {
  it('条件变更与查询参数序列化', async () => {
    const wrapper = mount(QueryFilter, { props: { ready: true, fields } })
    await wrapper.find('[data-test="input-status"]').setValue('enabled')
    expect(wrapper.emitted('update:conditions')?.[0]).toEqual([[{ field: 'status', operator: 'eq', value: 'enabled' }]])

    await wrapper.find('[data-test="keyword"]').setValue('张')
    expect(wrapper.emitted('update:keyword')?.[0]).toEqual(['张'])

    await wrapper.find('[data-test="search"]').trigger('click')
    const payload = wrapper.emitted('search')?.[0]?.[0] as QueryFilterSearchPayload
    expect(payload.params).toEqual({ status: 'enabled', keyword: '张' })
  })

  it('区间起 > 止时内联拦截且不提交', async () => {
    const wrapper = mount(QueryFilter, { props: { ready: true, fields, collapsed: false } })
    await wrapper.find('[data-test="input-amount"]').setValue('20')
    await wrapper.find('[data-test="input-amount-end"]').setValue('10')
    await wrapper.find('[data-test="search"]').trigger('click')
    expect(wrapper.emitted('invalid')).toHaveLength(1)
    expect(wrapper.emitted('search')).toBeUndefined()
  })

  it('条件摘要 chips：仅展示已生效条件、单个移除即重查', async () => {
    const wrapper = mount(QueryFilter, {
      props: {
        ready: true,
        fields,
        conditions: [
          { field: 'status', operator: 'eq', value: 'enabled' },
          { field: 'amount', operator: 'eq', value: '' },
        ],
      },
    })
    expect(wrapper.find('[data-test="summary"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chip-status"]').text()).toContain('状态：启用')
    expect(wrapper.find('[data-test="chip-amount"]').exists()).toBe(false)

    await wrapper.find('[data-test="chip-remove-status"]').trigger('click')
    expect(wrapper.emitted('update:conditions')?.[0]).toEqual([[{ field: 'amount', operator: 'eq', value: '' }]])
    expect(wrapper.emitted('search')).toHaveLength(1)
    expect(wrapper.find('[data-test="summary"]').exists()).toBe(false)
  })

  it('清空全部等价重置', async () => {
    const wrapper = mount(QueryFilter, {
      props: { ready: true, fields, conditions: [{ field: 'status', operator: 'eq', value: 'enabled' }] },
    })
    await wrapper.find('[data-test="clear-all"]').trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('重置回字段默认值并立即重查', async () => {
    const wrapper = mount(QueryFilter, {
      props: {
        ready: true,
        fields: [{ key: 'status', label: '状态', type: 'select', defaultValue: 'enabled', options: [] }],
        conditions: [{ field: 'status', operator: 'eq', value: 'disabled' }],
        keyword: '张',
      },
    })
    await wrapper.find('[data-test="reset"]').trigger('click')
    expect(wrapper.emitted('update:conditions')?.[0]).toEqual([[{ field: 'status', operator: 'eq', value: 'enabled' }]])
    expect(wrapper.emitted('update:keyword')?.[0]).toEqual([''])
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })
})

describe('QueryFilter 查询方案与高级入口', () => {
  const schemes = [
    { name: '我负责的', scope: 'user' as const, target: 'business' as const, conditions: [], isDefault: true },
    { name: '本月待审', scope: 'tenant' as const, target: 'business' as const, conditions: [] },
  ]

  it('方案面板：应用 / 设默认 / 删除 / 保存 / 另存为 / 重命名', async () => {
    const wrapper = mount(QueryFilter, {
      props: { ready: true, fields, showScheme: true, schemes, activeScheme: '我负责的' },
    })
    await wrapper.find('[data-test="scheme-trigger"]').trigger('click')
    expect(wrapper.find('[data-test="scheme-panel"]').exists()).toBe(true)

    await wrapper.find('[data-test="scheme-item-本月待审"] button').trigger('click')
    expect(wrapper.emitted('scheme-change')?.[0]).toEqual(['本月待审'])

    await wrapper.find('[data-test="scheme-trigger"]').trigger('click')
    await wrapper.find('[data-test="scheme-default-我负责的"]').trigger('click')
    expect(wrapper.emitted('set-default-scheme')?.[0]).toEqual(['我负责的'])

    await wrapper.find('[data-test="scheme-delete-我负责的"]').trigger('click')
    expect(wrapper.emitted('delete-scheme')?.[0]).toEqual(['我负责的'])

    await wrapper.find('[data-test="scheme-save"]').trigger('click')
    expect(wrapper.emitted('save-scheme')).toHaveLength(1)

    await wrapper.find('[data-test="scheme-save-as"]').trigger('click')
    expect(wrapper.emitted('save-as-scheme')).toHaveLength(1)

    await wrapper.find('[data-test="scheme-rename"]').trigger('click')
    expect(wrapper.emitted('rename-scheme')).toHaveLength(1)
  })

  it('字典类条件挂高级查询入口；失效提示可见', async () => {
    const wrapper = mount(QueryFilter, { props: { ready: true, fields, invalidHint: true } })
    expect(wrapper.find('[data-test="invalid-hint"]').text()).toContain('部分筛选条件已失效')
    await wrapper.find('[data-test="advanced-status"]').trigger('click')
    expect(wrapper.emitted('advanced')?.[0]?.[0]).toMatchObject({ key: 'status' })
    expect(wrapper.find('[data-test="advanced-amount"]').exists()).toBe(false)
  })
})
