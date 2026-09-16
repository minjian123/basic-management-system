/** 基础布局件二用例（Kiwi 736）：内容页签 / 卡片 / 折叠。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import Card from '@/components/layout/Card.vue'
import Collapse from '@/components/layout/Collapse.vue'
import CollapseItem from '@/components/layout/CollapseItem.vue'
import TabPane from '@/components/layout/TabPane.vue'
import Tabs from '@/components/layout/Tabs.vue'

import { mountWithPlugins } from './helpers/mount'

beforeEach(() => {
  localStorage.clear()
})

const TabsHost = {
  components: { Tabs, TabPane },
  data: () => ({ active: 'a' }),
  template: `
    <Tabs v-model="active" type="card" closable addable>
      <TabPane name="a" label="基本信息">内容 A</TabPane>
      <TabPane name="b" label="明细" :lazy="true">内容 B</TabPane>
    </Tabs>
  `,
}

describe('基础布局件二（Kiwi 736）', () => {
  it('内容页签：切换 / 关闭 / 新增 / 形态与 TabPane lazy', async () => {
    const wrapper = mountWithPlugins(TabsHost)
    const tabs = wrapper.findComponent(Tabs)
    const elTabs = tabs.findComponent({ name: 'ElTabs' })

    expect(elTabs.props('type')).toBe('card')
    expect(elTabs.props('closable')).toBe(true)
    expect(elTabs.props('addable')).toBe(true)
    expect(wrapper.text()).toContain('基本信息')
    expect(wrapper.text()).toContain('内容 A')
    expect(wrapper.text()).not.toContain('内容 B') // lazy 未激活不渲染

    elTabs.vm.$emit('update:modelValue', 'b')
    await nextTick()
    expect(tabs.emitted('update:modelValue')?.at(-1)).toEqual(['b'])
    expect(wrapper.text()).toContain('内容 B')

    elTabs.vm.$emit('tab-remove', 'a')
    elTabs.vm.$emit('tab-add')
    await nextTick()
    expect(tabs.emitted('tab-remove')?.at(-1)).toEqual(['a'])
    expect(tabs.emitted('tab-add')).toBeTruthy()
  })

  it('卡片：标题 / 描述 / extra / 折叠 / loading 骨架 / hoverable', async () => {
    const wrapper = mountWithPlugins(Card, {
      props: { title: '基础信息', description: '描述', collapsible: true, hoverable: true },
      slots: {
        default: '<div class="card-body">内容</div>',
        extra: '<button class="extra">操作</button>',
      },
    })
    expect(wrapper.text()).toContain('基础信息')
    expect(wrapper.text()).toContain('描述')
    expect(wrapper.find('.extra').exists()).toBe(true)
    expect(wrapper.find('.bms-card').classes()).toContain('is-hoverable')

    await wrapper.find('.bms-card-collapse-toggle').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.at(-1)).toEqual([true])
    expect(wrapper.emitted('collapse-change')?.at(-1)).toEqual([true])

    const loading = mountWithPlugins(Card, {
      props: { title: '加载中', loading: true },
      slots: { default: '<div class="card-body">内容</div>' },
    })
    expect(loading.find('.bms-skeleton').exists()).toBe(true)
    expect(loading.find('.card-body').exists()).toBe(false)
  })

  it('折叠面板：多开 / 手风琴 / 禁用 / iconPosition / lazy / persistKey', async () => {
    const CollapseHost = {
      components: { Collapse, CollapseItem },
      data: () => ({ active: ['a'] as string[] }),
      template: `
        <Collapse v-model="active" icon-position="left">
          <CollapseItem name="a" title="面板 A">内容 A</CollapseItem>
          <CollapseItem name="b" title="面板 B" :lazy="true">内容 B</CollapseItem>
          <CollapseItem name="c" title="面板 C" disabled>内容 C</CollapseItem>
        </Collapse>
      `,
    }
    const wrapper = mountWithPlugins(CollapseHost)
    const collapse = wrapper.findComponent(Collapse)
    const elCollapse = collapse.findComponent({ name: 'ElCollapse' })

    expect(wrapper.find('.bms-collapse--icon-left').exists()).toBe(true)
    expect(wrapper.text()).toContain('内容 A')
    expect(wrapper.text()).not.toContain('内容 B') // lazy 未展开

    elCollapse.vm.$emit('update:modelValue', ['a', 'b'])
    await nextTick()
    expect(collapse.emitted('update:modelValue')?.at(-1)).toEqual([['a', 'b']])
    expect(wrapper.text()).toContain('内容 B')

    const accordion = mountWithPlugins({
      components: { Collapse, CollapseItem },
      template: `
        <Collapse accordion persist-key="test-collapse">
          <CollapseItem name="a" title="A">内容 A</CollapseItem>
        </Collapse>
      `,
    })
    const accordionCollapse = accordion.findComponent(Collapse)
    expect(accordionCollapse.findComponent({ name: 'ElCollapse' }).props('accordion')).toBe(true)

    accordionCollapse.findComponent({ name: 'ElCollapse' }).vm.$emit('update:modelValue', 'a')
    await nextTick()
    expect(accordionCollapse.emitted('update:modelValue')?.at(-1)).toEqual(['a'])
    expect(localStorage.getItem('bms:pref:test-collapse:expanded')).toBe('["a"]')
  })
})
