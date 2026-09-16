<script setup lang="ts">
/**
 * 树域组件包装（`BaseTree`）：树域基类的组件轨（**框架无关**）。
 *
 * 契约见《组件设计 · 树域基类》：`data` / `load`（根与子级）、归一键、勾选（含级联策略）、
 * 单选高亮、手风琴、关键字过滤（保留命中节点及祖先路径）、初始全展开；
 * 事件 `select` / `check` / `node-click` / `node-expand` / `node-collapse` / `loaded`。
 * 兜底渲染递归原生列表；具体树控件（`el-tree` / Vant）由子类插槽接入。
 */

import { computed, h, onMounted, onUnmounted, useAttrs, useSlots, type VNode } from 'vue'

import { normalizeClassList, type ComponentDensity, type ComponentSize } from '@/base/BaseComponent'
import { useComponentBase } from '@/base/useComponentBase'

import type { TreeNode } from '../tree-data/useTreeData'
import { useTreeBase } from './useTreeBase'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    ns?: string
    identifier?: string
    size?: ComponentSize
    density?: ComponentDensity
    loading?: boolean
    disabled?: boolean
    visible?: boolean
    dataTest?: string
    data?: TreeNode[]
    load?: (node?: TreeNode) => Promise<unknown[]>
    nodeKey?: string
    labelKey?: string
    childrenKey?: string
    checkable?: boolean
    checkStrictly?: boolean
    selectable?: boolean
    accordion?: boolean
    filterable?: boolean
    defaultExpandAll?: boolean
  }>(),
  {
    ns: 'bms',
    identifier: '',
    size: 'default',
    density: undefined,
    loading: false,
    disabled: false,
    visible: true,
    dataTest: '',
    data: () => [],
    load: undefined,
    nodeKey: 'id',
    labelKey: 'label',
    childrenKey: 'children',
    checkable: false,
    checkStrictly: false,
    selectable: true,
    accordion: false,
    filterable: false,
    defaultExpandAll: false,
  },
)

const emit = defineEmits<{
  /** 节点选中（单选） */
  select: [node: TreeNode]
  /** 勾选变化（含级联结果） */
  check: [checkedKeys: string[]]
  'node-click': [node: TreeNode]
  'node-expand': [node: TreeNode]
  'node-collapse': [node: TreeNode]
  /** 懒加载子级完成 */
  loaded: [node: TreeNode]
}>()

const attrs = useAttrs()
const slots = useSlots()
const base = useComponentBase(props)

const treeBase = useTreeBase({
  data: () => props.data,
  ...(props.load ? { load: props.load } : {}),
  nodeKey: props.nodeKey,
  labelKey: props.labelKey,
  childrenKey: props.childrenKey,
  checkable: () => props.checkable,
  checkStrictly: () => props.checkStrictly,
  selectable: () => props.selectable,
  accordion: () => props.accordion,
  filterable: () => props.filterable,
  defaultExpandAll: props.defaultExpandAll,
  onSelect: (node) => emit('select', node),
  onCheck: (checkedKeys) => emit('check', checkedKeys),
  onLoaded: (node) => emit('loaded', node),
})

const rootAttrs = computed(() => {
  const classes = [...normalizeClassList(base.nsClass('tree')), ...normalizeClassList(attrs.class)]
  const external: Record<string, unknown> = {}
  if (attrs.style !== undefined) {
    external.style = attrs.style
  }
  const merged = base.rootAttrs(external)
  if (classes.length > 0) {
    merged.class = classes
  }
  return merged
})

const hasChildren = (node: TreeNode): boolean => (node.children?.length ?? 0) > 0 || node.isLeaf === false

const onNodeClick = (node: TreeNode): void => {
  emit('node-click', node)
  treeBase.select(node)
}

const onToggle = (node: TreeNode): void => {
  const wasExpanded = treeBase.expandedKeys.includes(node.key)
  if (!wasExpanded && (node.children?.length ?? 0) === 0 && node.isLeaf !== true) {
    void treeBase.loadChildren(node).then(() => {
      treeBase.toggleExpand(node.key)
      emit('node-expand', node)
    })
    return
  }
  treeBase.toggleExpand(node.key)
  if (wasExpanded) {
    emit('node-collapse', node)
  } else {
    emit('node-expand', node)
  }
}

const onCheck = (node: TreeNode): void => {
  const next = !treeBase.checkedKeys.includes(node.key)
  treeBase.check(node.key, next)
}

const renderNodes = (nodes: TreeNode[], level: number): VNode[] =>
  nodes.map((node) => {
    const expanded = treeBase.expandedKeys.includes(node.key)
    const checked = treeBase.checkedKeys.includes(node.key)
    const children = node.children ?? []
    return h('li', { key: node.key, class: 'bms-tree__node', 'data-key': node.key }, [
      h(
        'div',
        {
          class: ['bms-tree__row', ...(treeBase.selectedKey === node.key ? ['is-selected'] : [])],
          style: { paddingLeft: `${level * 16}px` },
          onClick: () => onNodeClick(node),
        },
        [
          hasChildren(node)
            ? h(
                'button',
                {
                  type: 'button',
                  class: 'bms-tree__toggle',
                  onClick: (event: MouseEvent) => {
                    event.stopPropagation()
                    onToggle(node)
                  },
                },
                expanded ? '−' : '+',
              )
            : null,
          props.checkable
            ? h('input', {
                type: 'checkbox',
                checked,
                class: 'bms-tree__check',
                onClick: (event: MouseEvent) => event.stopPropagation(),
                onChange: () => onCheck(node),
              })
            : null,
          h('span', { class: 'bms-tree__label' }, slots.default ? slots.default({ node }) : node.label),
          slots.actions ? h('span', { class: 'bms-tree__actions' }, slots.actions({ node })) : null,
        ],
      ),
      expanded && children.length > 0
        ? h('ul', { class: 'bms-tree__children' }, renderNodes(children, level + 1))
        : null,
    ])
  })

const TreeList = () => h('ul', { class: 'bms-tree__list' }, renderNodes(treeBase.treeData, 0))

onMounted(() => {
  base.notifyLifecycle('mounted')
})

onUnmounted(() => {
  base.notifyLifecycle('unmounted')
  base.dispose()
})

defineExpose({ base, mechanisms: base.mechanisms, treeBase })
</script>

<template>
  <div v-if="base.visible" v-bind="rootAttrs">
    <component :is="TreeList" v-if="treeBase.treeData.length > 0" />
    <slot v-else name="empty" />
  </div>
</template>
