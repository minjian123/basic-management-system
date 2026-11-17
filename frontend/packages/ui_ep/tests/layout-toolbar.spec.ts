// kiwi_id: 2525
/** 列表 / 表单工具栏件（09_02）：动作渲染 / 触发 / 分态 / 溢出 / 帮助位。 */

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FormToolbar from '../src/components/layout/FormToolbar.vue'
import ListToolbar from '../src/components/layout/ListToolbar.vue'

/** 弹窗桩（就地渲染插槽，便于断言帮助内容）。 */
const longTextStub = {
  props: ['modelValue', 'title'],
  template: '<div v-if="modelValue" data-test="long-text-stub"><span>{{ title }}</span><slot /></div>',
}

describe('ListToolbar 列表工具栏（09_02）', () => {
  it('渲染默认动作与页面覆盖的 testId；点击回传动作键', async () => {
    const wrapper = mount(ListToolbar, {
      props: {
        overrides: [
          { key: 'create', label: '新建用户', testId: 'user-create' },
          { key: 'batch-delete', testId: 'user-batch-delete' },
        ],
      },
    })
    expect(wrapper.find('[data-test="user-create"]').text()).toBe('新建用户')
    expect(wrapper.text()).toContain('刷新')
    expect(wrapper.text()).toContain('关闭')

    await wrapper.find('[data-test="user-create"]').trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual(['create'])
  })

  it('批量动作随选中数启用；加载态禁用全部动作', async () => {
    const idle = mount(ListToolbar, {
      props: { overrides: [{ key: 'batch-delete', testId: 'user-batch-delete' }], selectedCount: 0 },
    })
    expect(idle.find('[data-test="user-batch-delete"]').attributes('disabled')).toBeDefined()

    const selected = mount(ListToolbar, {
      props: { overrides: [{ key: 'batch-delete', testId: 'user-batch-delete' }], selectedCount: 2 },
    })
    expect(selected.find('[data-test="user-batch-delete"]').attributes('disabled')).toBeUndefined()

    const loading = mount(ListToolbar, { props: { loading: true } })
    expect(loading.find('[data-test="list-toolbar"]').exists()).toBe(true)
    expect(loading.text()).toContain('刷新')
    expect(loading.find('button[disabled]').exists()).toBe(true)
  })

  it('右组超限收进「更多」；帮助按锚点显隐并打开弹层', async () => {
    const fetcher = vi.fn(async () => ({
      matched: true,
      anchor_found: true,
      level: 'module',
      article: { id: '1', title: '模块帮助', content: '<p>正文</p>', source: 'builtin' },
      categories: [],
    }))
    const wrapper = mount(ListToolbar, {
      props: {
        maxRight: 1,
        actions: [
          { key: 'export', label: '导出', group: 'right', order: 10 },
          { key: 'columns', label: '自定义列', group: 'right', order: 20 },
        ],
        help: { context: { moduleKey: 'm1' }, anchorAvailable: true },
        helpFetcher: fetcher,
      },
      global: { stubs: { LongTextDialog: longTextStub } },
    })
    expect(wrapper.find('[data-test="toolbar-more"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="help-entry"]').exists()).toBe(true)

    await wrapper.find('[data-test="help-entry"]').trigger('click')
    await flushPromises()
    expect(fetcher).toHaveBeenCalledWith({ module_key: 'm1' }, { moduleKey: 'm1' })
    expect(wrapper.find('[data-test="long-text-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="help-article-content"]').html()).toContain('正文')
  })

  it('无锚点不显示帮助入口', () => {
    const wrapper = mount(ListToolbar, {
      props: { help: { context: {}, anchorAvailable: false }, helpFetcher: vi.fn() },
    })
    expect(wrapper.find('[data-test="help-entry"]').exists()).toBe(false)
  })
})

describe('FormToolbar 表单工具栏（09_02）', () => {
  it('只读 / 编辑分态：修改与保存互斥，关闭两态可见', async () => {
    const wrapper = mount(FormToolbar, {
      props: {
        editing: false,
        overrides: [
          { key: 'edit', testId: 'user-record-edit' },
          { key: 'save', testId: 'user-record-save' },
          { key: 'cancel', testId: 'user-record-cancel' },
        ],
      },
    })
    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-record-save"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('关闭')

    await wrapper.setProps({ editing: true })
    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="user-record-save"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-record-cancel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('关闭')
  })

  it('动作回传与帮助位（编辑态仍可见）', async () => {
    const wrapper = mount(FormToolbar, {
      props: {
        editing: true,
        overrides: [{ key: 'save', testId: 'user-record-save' }],
        help: { context: { formKey: 'user' }, anchorAvailable: true },
        helpFetcher: vi.fn(async () => ({ matched: false, anchor_found: true, categories: [] })),
      },
      global: { stubs: { LongTextDialog: longTextStub } },
    })
    await wrapper.find('[data-test="user-record-save"]').trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual(['save'])
    expect(wrapper.find('[data-test="help-entry"]').exists()).toBe(true)
  })
})
