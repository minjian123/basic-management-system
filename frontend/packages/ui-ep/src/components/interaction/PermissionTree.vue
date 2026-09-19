<script setup lang="ts">
// 权限树件（08_04_02）：三态勾选 / 隐含推导只读 / 动作默认全无 / 挂接缺失禁用 / 搜索与展开收起；树机制经树族基类。
import {
  resolveCheckState,
  flattenPermissionTree,
  type FlatPermissionNode,
  type PermissionCheckState,
  type PermissionNode,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseTreeData } from '../../composables/useBaseTreeData'
import IconRenderer from './IconRenderer.vue'

interface Props {
  /** 权限树（菜单 → 表单 → 业务 → 动作）。 */
  nodes?: PermissionNode[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 搜索词（`v-model:keyword`）。 */
  keyword?: string
  /** 当前选中节点键。 */
  selectedKey?: string
  /** 是否展示图标。 */
  showIcon?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  nodes: () => [],
  disabled: false,
  keyword: '',
  selectedKey: '',
  showIcon: true,
  emptyText: '暂无权限数据',
})

const emit = defineEmits<{
  check: [payload: { key: string; checked: boolean }]
  select: [key: string]
  'update:keyword': [value: string]
}>()

const { tree, filterText, setNodes, setFilterText } = useBaseTreeData()
/** 是否已完成首次展开（后续节点变更保留用户折叠状态）。 */
const expandedOnce = ref(false)
/** 展开态变更序号（树族展开集合为非响应式，件层以此触发重算）。 */
const expandedTick = ref(0)

watch(
  () => props.nodes,
  (list) => {
    setNodes(list)
    if (!expandedOnce.value && list.length > 0) {
      for (const entry of flattenPermissionTree(list)) {
        if (entry.node.children !== undefined && entry.node.children.length > 0) {
          tree.expand(entry.node.key, true)
        }
      }
      expandedOnce.value = true
    }
  },
  { immediate: true },
)

watch(
  () => props.keyword,
  (text) => setFilterText(text),
  { immediate: true },
)

/** 生效搜索词（经树族过滤文本）。 */
const activeKeyword = computed(() => filterText.value.trim())

/** 搜索命中（节点自身或其任一后代命中）。 */
function matches(node: PermissionNode): boolean {
  if (node.label.includes(activeKeyword.value) || node.key.includes(activeKeyword.value)) {
    return true
  }
  return (node.children ?? []).some((child) => matches(child))
}

/** 节点是否展开（读取展开态序号以建立响应式依赖）。 */
function isExpanded(key: string): boolean {
  void expandedTick.value
  return tree.expanded.has(key)
}

/** 是否全部展开（工具栏文案用）。 */
const allExpanded = computed(() => {
  void expandedTick.value
  const expandable = flattenPermissionTree(props.nodes).filter(
    (entry) => entry.node.children !== undefined && entry.node.children.length > 0,
  )
  return expandable.length > 0 && expandable.every((entry) => tree.expanded.has(entry.node.key))
})

/** 可见节点（搜索过滤 + 展开收起；搜索时强制展开命中分支）。 */
const visibleNodes = computed<FlatPermissionNode[]>(() => {
  const result: FlatPermissionNode[] = []
  const walk = (list: readonly PermissionNode[], depth: number): void => {
    for (const node of list) {
      if (activeKeyword.value !== '' && !matches(node)) {
        continue
      }
      result.push({ node, depth })
      const hasChildren = node.children !== undefined && node.children.length > 0
      if (hasChildren && (activeKeyword.value !== '' || isExpanded(node.key))) {
        walk(node.children ?? [], depth + 1)
      }
    }
  }
  walk(props.nodes, 0)
  return result
})

/** 业务节点（推导只读）与挂接缺失节点不可授予。 */
function grantable(node: PermissionNode): boolean {
  return node.type !== 'business' && node.detached !== true
}

/** 节点勾选三态。 */
function stateOf(node: PermissionNode): PermissionCheckState {
  return resolveCheckState(node)
}

/** 展开 / 收起节点。 */
function toggleExpand(key: string): void {
  tree.expand(key, !tree.expanded.has(key))
  expandedTick.value += 1
}

/** 全部展开 / 全部收起。 */
function toggleAll(): void {
  const expandable = flattenPermissionTree(props.nodes).filter(
    (entry) => entry.node.children !== undefined && entry.node.children.length > 0,
  )
  const next = !allExpanded.value
  for (const entry of expandable) {
    tree.expand(entry.node.key, next)
  }
  expandedTick.value += 1
}

/** 勾选 / 取消勾选。 */
function onCheck(node: PermissionNode): void {
  emit('check', { key: node.key, checked: node.checked !== true })
}
</script>

<template>
  <div class="bms-permission-tree" data-test="permission-tree" :data-disabled="disabled || undefined">
    <div class="bms-permission-tree__toolbar" data-test="tree-toolbar">
      <input
        type="search"
        data-test="tree-search"
        placeholder="搜索菜单 / 表单 / 动作"
        :value="keyword"
        @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
      />
      <button type="button" data-test="tree-toggle-all" @click="toggleAll">
        {{ allExpanded ? '收起全部' : '展开全部' }}
      </button>
    </div>

    <p v-if="visibleNodes.length === 0" data-test="empty">{{ emptyText }}</p>

    <div
      v-for="entry in visibleNodes"
      :key="entry.node.key"
      class="bms-permission-tree__node"
      :data-test="`node-${entry.node.key}`"
      :data-type="entry.node.type"
      :data-depth="entry.depth"
      :data-state="stateOf(entry.node)"
      :data-detached="entry.node.detached || undefined"
      :data-active="selectedKey === entry.node.key || undefined"
      :style="{ paddingLeft: `${entry.depth * 16}px` }"
    >
      <button
        v-if="entry.node.children !== undefined && entry.node.children.length > 0"
        type="button"
        data-test="tree-expand"
        :data-test-key="entry.node.key"
        @click="toggleExpand(entry.node.key)"
      >
        {{ isExpanded(entry.node.key) ? '▾' : '▸' }}
      </button>

      <label>
        <input
          type="checkbox"
          :data-test="`node-check-${entry.node.key}`"
          :checked="entry.node.checked === true"
          :disabled="disabled || !grantable(entry.node)"
          @change="onCheck(entry.node)"
        />
      </label>
      <i v-if="stateOf(entry.node) === 'indeterminate'" class="bms-permission-tree__half" data-test="indeterminate" />

      <span v-if="showIcon && entry.node.icon" class="bms-permission-tree__icon">
        <IconRenderer :name="entry.node.icon" :size="14" />
      </span>

      <button type="button" data-test="tree-label" @click="emit('select', entry.node.key)">
        {{ entry.node.label }}
      </button>

      <em v-if="entry.node.type === 'business'" data-test="derived">推导</em>
      <span v-if="entry.node.detached" data-test="detached">未挂接</span>
    </div>
  </div>
</template>
