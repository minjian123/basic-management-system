/** 表单框架壳用例（03_05）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { FormLayoutShell, useConfirm, useFormShell } from '../src'

const tab = (key: string, title = key) => ({ key, title, path: key, closable: key !== 'list' })

describe('useFormShell', () => {
  it('列表页签固定且详情不同记录新开、同记录激活', () => {
    const shell = useFormShell({ listTitle: '用户列表' })
    expect(shell.listTab.closable).toBe(false)
    expect(shell.detailTabs.value).toHaveLength(0)

    shell.openDetail({ id: '1', title: '用户 1' })
    shell.openDetail({ id: '2', title: '用户 2' })
    shell.openDetail({ id: '1', title: '用户 1' })
    expect(shell.detailTabs.value.map((item) => item.key)).toEqual(['detail:1', 'detail:2'])
    expect(shell.activeKey.value).toBe('detail:1')
    expect(shell.activeDetail()?.title).toBe('用户 1')
  })

  it('缓存键随 cacheDetail 生效', () => {
    const shell = useFormShell({ cacheDetail: true })
    shell.openDetail({ id: '1', title: 'A' })
    expect(shell.cachedDetailKeys.value).toEqual(['detail:1'])
  })

  it('关闭详情（脏数据经二次确认）与刷新信号', async () => {
    const confirm = useConfirm()
    const shell = useFormShell()
    const key = shell.openDetail({ id: '1', title: 'A' })
    shell.markDirty(key)

    const pending = shell.closeDetail(key)
    confirm.resolveConfirm(true)
    expect(await pending).toBe(true)
    expect(shell.detailTabs.value).toHaveLength(0)
    expect(shell.activeKey.value).toBe('list')

    shell.requestRefresh()
    expect(shell.refreshToken.value).toBe(1)
  })
})

const DualTabsStub = {
  name: 'DualTabs',
  props: ['primary', 'primaryKey', 'secondary', 'secondaryKey'],
  emits: ['select', 'update:primaryKey', 'update:secondaryKey'],
  template: `<div class="dual-tabs">
    <button data-test="d-primary" @click="$emit('select', 'primary', primaryKey)">列表</button>
    <button data-test="d-secondary" @click="$emit('select', 'secondary', 'detail:2')">详情</button>
  </div>`,
}

describe('FormLayoutShell', () => {
  it('列表 / 详情插槽按激活页签切换，选择事件归一', async () => {
    const list = tab('list', '列表')
    const detail = tab('detail:1', '用户 1')
    const wrapper = mount(FormLayoutShell, {
      props: { listTab: list, detailTabs: [detail], activeDetailKey: 'detail:1' },
      slots: { list: '<div data-test="list">列表</div>', detail: '<div data-test="detail">详情</div>' },
      global: { stubs: { DualTabs: DualTabsStub } },
    })
    expect(wrapper.find('[data-test="detail"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="list"]').exists()).toBe(false)

    await wrapper.find('[data-test="d-primary"]').trigger('click')
    await wrapper.find('[data-test="d-secondary"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['list'], ['detail:2']])
  })

  it('列表激活时渲染列表插槽', () => {
    const list = tab('list', '列表')
    const wrapper = mount(FormLayoutShell, {
      props: { listTab: list, detailTabs: [], activeDetailKey: 'list' },
      slots: { list: '<div data-test="list">列表</div>' },
      global: { stubs: { DualTabs: DualTabsStub } },
    })
    expect(wrapper.find('[data-test="list"]').exists()).toBe(true)
    expect(wrapper.attributes('data-open-mode')).toBe('tab')
  })
})
