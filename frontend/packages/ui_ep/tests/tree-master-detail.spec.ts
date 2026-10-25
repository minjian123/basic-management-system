/** 树形主从布局与可调分割用例（03_03_02）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { EmptyState, SplitPane, TreeMasterDetail } from '../src'

const ElTreeStub = defineComponent({
  name: 'ElTree',
  props: { data: { type: Array, default: () => [] } },
  emits: ['node-click'],
  methods: {
    filter(): void {},
    setCurrentKey(): void {},
  },
  template:
    '<div class="el-tree"><button v-for="node in data" :key="node.key" :data-test="`node-${node.key}`" @click="$emit(\'node-click\', node)">{{ node.label }}</button></div>',
})

const ElInputStub = defineComponent({
  name: 'ElInput',
  props: { modelValue: { type: String, default: '' } },
  emits: ['update:modelValue'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})

const stubs = { ElTree: ElTreeStub, ElInput: ElInputStub }

const treeData = [
  { key: 'a', label: '分组 A', children: [{ key: 'a1', label: '节点 A1' }] },
  { key: 'b', label: '分组 B' },
]

describe('TreeMasterDetail', () => {
  it('点击节点发出 select 与 update:selectedKey', async () => {
    const wrapper = mount(TreeMasterDetail, {
      props: { treeData, selectedKey: 'b' },
      global: { stubs },
    })
    await wrapper.find('[data-test="node-a"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ key: 'a' })
    expect(wrapper.emitted('update:selectedKey')?.[0]).toEqual(['a'])
  })

  it('空树走数据空态，未选中走未选择空态', () => {
    const emptyTree = mount(TreeMasterDetail, { props: { treeData: [] }, global: { stubs } })
    expect(emptyTree.findComponent(EmptyState).props('type')).toBe('data')

    const unselected = mount(TreeMasterDetail, {
      props: { treeData, selectedKey: '' },
      global: { stubs },
    })
    expect(unselected.findComponent(EmptyState).props('type')).toBe('unselected')
  })

  it('有选中时渲染主区插槽', () => {
    const wrapper = mount(TreeMasterDetail, {
      props: { treeData, selectedKey: 'a' },
      slots: { default: '<div data-test="detail">详情</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="detail"]').exists()).toBe(true)
  })
})

function pointerEvent(type: string, clientX: number): MouseEvent {
  const event = new MouseEvent(type)
  Object.defineProperty(event, 'clientX', { value: clientX })
  return event
}

describe('SplitPane', () => {
  it('拖拽改变尺寸并发出 update:modelValue', async () => {
    const wrapper = mount(SplitPane, { props: { modelValue: 280, max: 400 } })
    wrapper.find('[data-test="split-handle"]').element.dispatchEvent(pointerEvent('pointerdown', 300))
    window.dispatchEvent(pointerEvent('pointermove', 340))
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([320])
    window.dispatchEvent(pointerEvent('pointerup', 340))
    expect(wrapper.emitted('resize-end')?.at(-1)).toEqual([320])
  })

  it('拖拽受上下界约束', async () => {
    const wrapper = mount(SplitPane, { props: { modelValue: 280, min: 200, max: 400 } })
    wrapper.find('[data-test="split-handle"]').element.dispatchEvent(pointerEvent('pointerdown', 300))
    window.dispatchEvent(pointerEvent('pointermove', 5000))
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([400])
    window.dispatchEvent(pointerEvent('pointermove', 0))
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([200])
    window.dispatchEvent(pointerEvent('pointerup', 0))
  })

  it('键盘微调与双击复位', async () => {
    const wrapper = mount(SplitPane, { props: { modelValue: 300 } })
    const handle = wrapper.find('[data-test="split-handle"]')
    await handle.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([310])
    await handle.trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([300])
    await handle.trigger('dblclick')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([300])
  })

  it('禁用时不响应拖拽', async () => {
    const wrapper = mount(SplitPane, { props: { modelValue: 280, disabled: true } })
    wrapper.find('[data-test="split-handle"]').element.dispatchEvent(pointerEvent('pointerdown', 300))
    window.dispatchEvent(pointerEvent('pointermove', 340))
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
