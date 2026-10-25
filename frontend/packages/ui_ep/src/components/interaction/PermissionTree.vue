<script setup lang="ts">
// 菜单树内部子件（08-4-4，新口径）：仅菜单入口树——三态勾选、搜索、展开收起、挂接缺失标记；树机制经树族投影。
// 样式（11-01）：模板改组件库件承载（el-input 搜索 / el-checkbox 三态 / el-button 展开），补 <style scoped> 消费 --bms-* 令牌。
import {
  flattenMenus,
  menuCheckState,
  type FormMeta,
  type PermissionEntry,
  type PermissionMenuNode,
} from '@bms/core'
import { ElButton, ElCheckbox, ElInput } from 'element-plus'
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
      return true
    }
    return match(entry.node)
  })
})

/** 展开 / 收起。 */
function toggleExpand(id: string): void {
  tree.expand(id, !tree.expanded.has(id))
  expandedTick.value += 1
}

/** 勾选 / 取消勾选（el-checkbox 值变更）。 */
function onCheck(id: string, value: boolean | string | number): void {
  emit('check', { id, checked: value === true })
}
</script>

<template>
  <div class="bms-permission-tree" data-test="permission-tree" :data-disabled="disabled || undefined">
    <div class="bms-permission-tree__toolbar" data-test="tree-toolbar">
      <el-input
        data-test="tree-search"
        :model-value="keyword"
        placeholder="搜索菜单"
        size="small"
        clearable
        :disabled="disabled"
        @update:model-value="emit('update:keyword', $event)"
      />
    </div>

    <p v-if="visible.length === 0" class="bms-permission-tree__empty" data-test="empty">{{ emptyText }}</p>

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
      <el-button
        v-if="entry.node.children !== undefined && entry.node.children.length > 0"
        class="bms-permission-tree__expand"
        data-test="tree-expand"
        :data-test-key="entry.node.id"
        text
        size="small"
        :disabled="disabled"
        @click="toggleExpand(entry.node.id)"
      >
        {{ isExpanded(entry.node.id) ? '▾' : '▸' }}
      </el-button>
      <span v-else class="bms-permission-tree__spacer" aria-hidden="true" />

      <el-checkbox
        :data-test="`node-check-${entry.node.id}`"
        :model-value="stateOf(entry.node.id) === 'checked'"
        :indeterminate="stateOf(entry.node.id) === 'indeterminate'"
        :disabled="disabled || detached(entry.node.id)"
        @update:model-value="onCheck(entry.node.id, $event)"
      />
      <i v-if="stateOf(entry.node.id) === 'indeterminate'" data-test="indeterminate" />

      <span v-if="showIcon && entry.node.icon" class="bms-permission-tree__icon">
        <IconRenderer :name="entry.node.icon" :size="14" />
      </span>

      <el-button
        class="bms-permission-tree__label"
        data-test="tree-label"
        text
        :disabled="disabled"
        @click="emit('select', entry.node.id)"
      >
        {{ entry.node.name }}
      </el-button>
      <span v-if="detached(entry.node.id)" class="bms-permission-tree__detached" data-test="detached">未挂接</span>
    </div>
  </div>
</template>

<style scoped>
.bms-permission-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

.bms-permission-tree__toolbar {
  flex: none;
  padding-bottom: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-permission-tree__empty {
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-permission-tree__node {
  display: flex;
  align-items: center;
  gap: var(--bms-space-1);
  min-height: var(--bms-control-height);
  padding-right: var(--bms-space-2);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-permission-tree__node:hover {
  background: var(--bms-color-fill);
}

.bms-permission-tree__node[data-active] {
  background: var(--bms-color-primary-light);
  box-shadow: inset 2px 0 0 var(--bms-color-primary);
}

.bms-permission-tree__node[data-disabled] {
  opacity: 0.7;
}

.bms-permission-tree__expand {
  flex: none;
  width: 20px;
  padding: 0;
  color: var(--bms-color-text-secondary);
}

.bms-permission-tree__spacer {
  flex: none;
  width: 20px;
}

.bms-permission-tree__icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  color: var(--bms-color-text-secondary);
}

.bms-permission-tree__label {
  flex: 1;
  min-width: 0;
  justify-content: flex-start;
  overflow: hidden;
  color: var(--bms-color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-permission-tree__detached {
  flex: none;
  padding: 0 var(--bms-space-1);
  color: var(--bms-perm-detached-color);
  font-size: var(--bms-font-size-xs);
  font-style: normal;
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}
</style>
