/** 基础布局件用例（03_03_03）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import {
  CollapsePanel,
  CollapsePanelGroup,
  ContentTabs,
  GridItem,
  GridLayout,
  LayoutCard,
  SpacingDivider,
  SplitPane,
} from '../src'

const BaseStub = (name: string, props: string[], template: string) => ({
  name,
  props,
  emits: ['tab-change', 'change', 'update:modelValue'],
  template,
})

const ElRow = BaseStub('ElRow', ['gutter', 'justify', 'align'], '<div class="el-row"><slot /></div>')
const ElCol = BaseStub('ElCol', ['span', 'offset', 'xs', 'sm', 'md', 'lg', 'xl'], '<div class="el-col"><slot /></div>')
const ElDivider = BaseStub(
  'ElDivider',
  ['direction', 'contentPosition', 'borderStyle'],
  '<div class="el-divider"><slot /></div>',
)
const ElTabs = BaseStub(
  'ElTabs',
  ['modelValue', 'type'],
  '<div class="el-tabs"><button data-test="tab-a" @click="$emit(\'tab-change\', \'a\')">A</button><slot /></div>',
)
const ElTabPane = BaseStub('ElTabPane', ['name', 'label', 'disabled', 'lazy'], '<div class="el-tab-pane"><slot /></div>')
const ElCard = BaseStub('ElCard', ['shadow', 'bodyStyle'], '<div class="el-card"><slot name="header" /><slot /><slot name="footer" /></div>')
const ElCollapse = BaseStub('ElCollapse', ['modelValue', 'accordion'], '<div class="el-collapse"><slot /></div>')
const ElCollapseItem = BaseStub(
  'ElCollapseItem',
  ['name', 'title', 'disabled'],
  '<div class="el-collapse-item"><slot name="title" /><slot /></div>',
)

const stubs = { ElRow, ElCol, ElDivider, ElTabs, ElTabPane, ElCard, ElCollapse, ElCollapseItem }

describe('栅格', () => {
  it('传递间距并对齐，子项缺省占满 24 栅', () => {
    const wrapper = mount(GridLayout, {
      props: { gutter: 16, justify: 'space-between', align: 'middle' },
      global: { stubs },
      slots: { default: GridItem },
    })
    const row = wrapper.findComponent(ElRow)
    expect(row.props('gutter')).toBe(16)
    expect(row.props('justify')).toBe('space-between')
    expect(row.props('align')).toBe('middle')

    const item = mount(GridItem, { global: { stubs } })
    expect(item.findComponent(ElCol).props('span')).toBe(24)
  })

  it('子项支持列宽与偏距', () => {
    const wrapper = mount(GridItem, { props: { span: 12, offset: 6 }, global: { stubs } })
    const col = wrapper.findComponent(ElCol)
    expect(col.props('span')).toBe(12)
    expect(col.props('offset')).toBe(6)
  })
})

describe('间距分割线', () => {
  it('按方向 / 文案位 / 虚线传递属性', () => {
    const wrapper = mount(SpacingDivider, {
      props: { direction: 'vertical', position: 'left', dashed: true, size: 'lg' },
      slots: { default: '分组' },
      global: { stubs },
    })
    const divider = wrapper.findComponent(ElDivider)
    expect(divider.props('direction')).toBe('vertical')
    expect(divider.props('contentPosition')).toBe('left')
    expect(divider.props('borderStyle')).toBe('dashed')
    expect(wrapper.text()).toContain('分组')
    expect(wrapper.attributes('style')).toContain('margin-inline: 24px')
  })
})

describe('内容页签', () => {
  it('渲染页签并经 BaseTabs 状态派发事件', async () => {
    const wrapper = mount(ContentTabs, {
      props: { modelValue: 'a', tabs: [{ key: 'a', title: 'A' }, { key: 'b', title: 'B', disabled: true }] },
      global: { stubs },
    })
    expect(wrapper.findAllComponents(ElTabPane)).toHaveLength(2)

    await wrapper.find('[data-test="tab-a"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['a'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['a'])
  })
})

describe('卡片', () => {
  it('标题栏 / 附加区 / 页脚', () => {
    const wrapper = mount(LayoutCard, {
      props: { title: '基本信息' },
      slots: { default: '<div data-test="body">内容</div>', extra: '<button data-test="extra">编辑</button>', footer: '<div data-test="footer">页脚</div>' },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('基本信息')
    expect(wrapper.find('[data-test="extra"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="footer"]').exists()).toBe(true)
  })

  it('可折叠时点击标题收起正文', async () => {
    const wrapper = mount(LayoutCard, {
      props: { title: '折叠', collapsible: true },
      slots: { default: '<div data-test="body">内容</div>' },
      global: { stubs },
    })
    expect(wrapper.find('.bms-layout-card__body').attributes('style') ?? '').not.toContain('display: none')
    await wrapper.find('.bms-layout-card__header').trigger('click')
    expect(wrapper.find('.bms-layout-card__body').attributes('style')).toContain('display: none')
  })

  it('无标题与附加区时不渲染标题栏', () => {
    const wrapper = mount(LayoutCard, { global: { stubs }, slots: { default: '<div>x</div>' } })
    expect(wrapper.find('.bms-layout-card__header').exists()).toBe(false)
  })
})

describe('折叠面板', () => {
  it('组透传手风琴并派发展开变化', async () => {
    const wrapper = mount(CollapsePanelGroup, {
      props: { modelValue: 'one', accordion: true },
      global: { stubs, components: { CollapsePanel } },
      slots: { default: '<collapse-panel name="one" title="一">内容</collapse-panel>' },
    })
    expect(wrapper.findComponent(ElCollapse).props('accordion')).toBe(true)

    wrapper.findComponent(ElCollapse).vm.$emit('change', 'two')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['two'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['two'])
  })
})

describe('组合可用', () => {
  it('栅格 + 卡片 + 折叠 + 分栏可组合挂载', () => {
    const wrapper = mount(GridLayout, {
      global: { stubs, components: { GridItem, LayoutCard, CollapsePanelGroup, CollapsePanel, SplitPane } },
      slots: {
        default:
          '<grid-item :span="12"><layout-card title="详情"><collapse-panel-group><collapse-panel name="a" title="A">内容</collapse-panel></collapse-panel-group></layout-card></grid-item>',
      },
    })
    expect(wrapper.findComponent(LayoutCard).exists()).toBe(true)
    expect(wrapper.findComponent(CollapsePanel).exists()).toBe(true)
  })
})
