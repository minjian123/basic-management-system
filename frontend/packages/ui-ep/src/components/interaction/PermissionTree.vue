<script setup lang="ts">
// 菜单树内部子件（08-4-4，新口径）：仅菜单入口树——三态勾选、搜索、展开收起、挂接缺失标记；树机制经树族投影。
import {
  flattenMenus,
  menuCheckState,
  type FormMeta,
  type PermissionEntry,
  type PermissionMenuNode,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseTreeData } from '../../composables/useBaseTreeData'
import IconRenderer from './IconRenderer.vue'

interface Props {
  /** 菜单树（仅菜单入口）。 */
  menus?: PermissionMenuNode[]
  /** 表单清单（判定挂接缺失）。 */
  forms?: FormMeta[]
  /** 授权条目（判定勾选三态）。 */
  entries?: PermissionEntry[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 搜索词（`v-model:keyword`）。 */
  keyword?: string
  /** 当前选中菜单 id。 */
  selectedId?: string
  /** 是否展示图标。 */
  showIcon?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  menus: () => [],
  forms: () => [],
  entries: () => [],
  disabled: false,
  keyword: '',
  selectedId: '',
  showIcon: true,
  emptyText: '暂无菜单数据',
})

const emit = defineEmits<{
  check: [payload: { id: string; checked: boolean }]
  select: [id: string]
  'update:keyword': [value: string]
}>()

const { tree, setNodes } = useBaseTreeData()
/** 展开态变更序号（树族展开集合非响应式，件层以此触发重算）。 */
const expandedTick = ref(0)
/** 是否已完成首次展开。 */
const expandedOnce = ref(false)

watch(
  () => props.menus,
  (list) => {
    setNodes(list.map((node) => ({ key: node.id, children: node.children?.map((child) => ({ key: child.id })) })))
    if (!expandedOnce.value && list.length > 0) {
      for (const node of list) {
        if (node.children !== undefined && node.children.length > 0) {
          tree.expand(node.id, true)
        }
      }
      expandedOnce.value = true
    }
  },
  { immediate: true },
)

/** 生效搜索词。 */
const keyword = computed(() => props.keyword.trim())

/** 菜单是否挂接缺失（无关联表单）。 */
function detached(id: string): boolean {
  return !props.forms.some((form) => form.menuIds.includes(id))
}

/** 菜单勾选三态。 */
function stateOf(id: string): string {
  return menuCheckState(props.menus, props.entries, id)
}

/** 节点是否展开。 */
function isExpanded(id: string): boolean {
  void expandedTick.value
  return tree.expanded.has(id)
}

/** 可见节点（搜索命中自身或后代时保留分支）。 */
const visible = computed(() => {
  const text = keyword.value
  const match = (node: PermissionMenuNode): boolean =>
    node.name.includes(text) || (node.children ?? []).some((child) => match(child))
  return flattenMenus(props.menus).filter((entry) => {
    if (text === '') {
      const parentVisible = true
      return parentVisible
    }
    return match(entry.node)
  })
})

/** 展开 / 收起。 */
function toggleExpand(id: string): void {
  tree.expand(id, !tree.expanded.has(id))
  expandedTick.value += 1
}

/** 勾选 / 取消勾选。 */
function onCheck(id: string, event: Event): void {
  emit('check', { id, checked: (event.target as HTMLInputElement).checked })
}
</script>

<template>
  <div class="bms-permission-tree" data-test="permission-tree" :data-disabled="disabled || undefined">
    <div class="bms-permission-tree__toolbar" data-test="tree-toolbar">
      <input
        type="search"
        data-test="tree-search"
        placeholder="搜索菜单"
        :value="keyword"
        :disabled="disabled"
        @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
      />
    </div>

    <p v-if="visible.length === 0" data-test="empty">{{ emptyText }}</p>

    <div
      v-for="entry in visible"
      :key="entry.node.id"
      class="bms-permission-tree__node"
      :data-test="`node-${entry.node.id}`"
      :data-depth="entry.depth"
      :data-state="stateOf(entry.node.id)"
      :data-detached="detached(entry.node.id) || undefined"
      :data-active="selectedId === entry.node.id || undefined"
      :style="{ paddingLeft: `${entry.depth * 16}px` }"
    >
      <button
        v-if="entry.node.children !== undefined && entry.node.children.length > 0"
        type="button"
        data-test="tree-expand"
        :data-test-key="entry.node.id"
        @click="toggleExpand(entry.node.id)"
      >
        {{ isExpanded(entry.node.id) ? '▾' : '▸' }}
      </button>

      <label>
        <input
          type="checkbox"
          :data-test="`node-check-${entry.node.id}`"
          :checked="stateOf(entry.node.id) === 'checked'"
          :disabled="disabled || detached(entry.node.id)"
          @change="onCheck(entry.node.id, $event)"
        />
      </label>
      <i v-if="stateOf(entry.node.id) === 'indeterminate'" data-test="indeterminate" />

      <span v-if="showIcon && entry.node.icon" class="bms-permission-tree__icon">
        <IconRenderer :name="entry.node.icon" :size="14" />
      </span>

      <button type="button" data-test="tree-label" @click="emit('select', entry.node.id)">
        {{ entry.node.name }}
      </button>
      <span v-if="detached(entry.node.id)" data-test="detached">未挂接</span>
    </div>
  </div>
</template>
