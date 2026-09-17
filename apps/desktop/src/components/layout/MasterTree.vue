<script setup lang="ts">
/**
 * 主树：分类 / 组织 / 目录树的搜索、选中、多选、懒加载、计数与维护入口。
 *
 * 契约见《组件设计 · 树形主从布局》§3.1：树渲染基于 `el-tree` 自实现，数据契约
 * （`{ id, parentId, label, children, leaf?, count? }`）与 `BaseTree` / `useTreeData` 对齐
 * （字段类树控件交付后对齐）；维护动作仅 **emit**（弹窗由业务实现）；空树 / 加载态复用
 * 反馈件（`03_02`）。
 */

import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, onMounted, ref, useAttrs, watch } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'
import { EmptyState, SkeletonBlock } from '@/components/feedback'
import { hasPerm } from '@/utils/perm'

import type { TreeNode } from './useMasterDetail'

const props = withDefaults(
  defineProps<{
    /** 树数据（`{ id, parentId?, label, children?, leaf?, count? }`） */
    treeData?: TreeNode[]
    loadMode?: 'all' | 'lazy'
    /** 懒加载函数（`loadMode='lazy'`） */
    loadChildren?: (node: TreeNode) => Promise<TreeNode[]>
    /** 多选（从区按并集过滤） */
    checkable?: boolean
    /** 节点右侧显示记录数（`count`） */
    showCount?: boolean
    /** 是否显示增删改 / 刷新工具栏 */
    toolbar?: boolean
    /** 树节点增删改所需权限码（无权限隐藏入口） */
    managePermission?: string[]
    defaultExpandAll?: boolean
    emptyText?: string
    loading?: boolean
  }>(),
  {
    treeData: () => [],
    loadMode: 'all',
    loadChildren: undefined,
    checkable: false,
    showCount: false,
    toolbar: true,
    managePermission: () => [],
    defaultExpandAll: false,
    emptyText: '',
    loading: false,
  },
)

const emit = defineEmits<{
  select: [node: TreeNode | null]
  'node-create': [parent: TreeNode | null]
  'node-edit': [node: TreeNode]
  'node-delete': [node: TreeNode]
  refresh: [parent: TreeNode | null]
  check: [nodes: TreeNode[]]
  'load-error': [error: unknown]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'master-tree' })
const { t } = useI18n()
const attrs = useAttrs()

interface TreeExpose {
  filter: (value: string) => void
  getCheckedNodes: () => TreeNode[]
  setCurrentKey: (key: string | null) => void
}

const treeRef = ref<TreeExpose | null>(null)
const keyword = ref('')
let filterTimer: ReturnType<typeof setTimeout> | null = null

watch(keyword, (value) => {
  if (filterTimer) {
    clearTimeout(filterTimer)
  }
  filterTimer = setTimeout(() => treeRef.value?.filter(value.trim()), 200)
})

onBeforeUnmount(() => {
  if (filterTimer) {
    clearTimeout(filterTimer)
  }
})

const currentNode = ref<TreeNode | null>(null)

const canManage = computed(
  () => props.managePermission.length === 0 || hasPerm(props.managePermission),
)
const isEmpty = computed(
  () => props.loadMode === 'all' && !props.loading && props.treeData.length === 0,
)
const emptyTitle = computed(() => props.emptyText || t('tree.empty'))
const emptyAction = computed(() => (canManage.value ? { text: t('tree.create') } : undefined))

/** 懒加载（适配 `el-tree` 的 `(node, resolve, reject)` 签名） */
function onLoad(
  node: { data?: TreeNode },
  resolve: (data: TreeNode[]) => void,
  reject?: (error?: Error) => void,
): void {
  const target = node.data ?? (node as unknown as TreeNode)
  if (!props.loadChildren) {
    resolve([])
    return
  }
  props.loadChildren(target)
    .then((data) => resolve(data))
    .catch((error: unknown) => {
      emit('load-error', error)
      reject?.(error instanceof Error ? error : new Error(String(error)))
    })
}

function filterNode(value: string, data: TreeNode): boolean {
  if (!value) {
    return true
  }
  return data.label.toLowerCase().includes(value.toLowerCase())
}

function onNodeClick(data: TreeNode): void {
  currentNode.value = data
  emit('select', data)
}

function onCheck(): void {
  emit('check', treeRef.value?.getCheckedNodes() ?? [])
}

function actionCreate(parent: TreeNode | null): void {
  emit('node-create', parent)
}

function actionEdit(): void {
  if (currentNode.value) {
    emit('node-edit', currentNode.value)
  }
}

function actionDelete(): void {
  if (currentNode.value) {
    emit('node-delete', currentNode.value)
  }
}

function actionRefresh(): void {
  emit('refresh', null)
}

/* ===== 右键菜单 ===== */
const menu = ref({ visible: false, x: 0, y: 0, node: null as TreeNode | null })

function onNodeContextMenu(event: MouseEvent, data: TreeNode): void {
  currentNode.value = data
  menu.value = { visible: true, x: event.clientX, y: event.clientY, node: data }
}

function closeMenu(): void {
  menu.value.visible = false
}

function onDocumentClick(): void {
  if (menu.value.visible) {
    closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

function runMenu(action: 'create' | 'edit' | 'delete' | 'refresh'): void {
  closeMenu()
  if (action === 'create') {
    actionCreate(currentNode.value)
    return
  }
  if (action === 'edit') {
    actionEdit()
    return
  }
  if (action === 'delete') {
    actionDelete()
    return
  }
  emit('refresh', currentNode.value)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('master-tree'), cls], style: sty, ...rest })
})

defineExpose({
  filter: (value: string) => treeRef.value?.filter(value),
  getCheckedNodes: () => treeRef.value?.getCheckedNodes() ?? [],
  clearSearch: () => {
    keyword.value = ''
  },
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('master-tree')">
    <div v-if="toolbar" :class="base.nsClass('master-tree-toolbar')">
      <el-input v-model="keyword" size="small" clearable :placeholder="t('tree.searchPlaceholder')" />
      <div v-if="canManage" :class="base.nsClass('master-tree-actions')">
        <el-button size="small" @click="actionCreate(null)">{{ t('tree.create') }}</el-button>
        <el-button size="small" :disabled="!currentNode" @click="actionEdit">
          {{ t('tree.edit') }}
        </el-button>
        <el-button size="small" :disabled="!currentNode" @click="actionDelete">
          {{ t('tree.delete') }}
        </el-button>
        <el-button size="small" @click="actionRefresh">{{ t('tree.refresh') }}</el-button>
      </div>
    </div>

    <div :class="base.nsClass('master-tree-body')">
      <SkeletonBlock v-if="loading" variant="list" :rows="6" />
      <EmptyState
        v-else-if="isEmpty"
        type="custom"
        size="small"
        :title="emptyTitle"
        :action="emptyAction"
        @action="actionCreate(null)"
      />
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        node-key="id"
        :props="{ label: 'label', children: 'children', isLeaf: 'leaf' }"
        :show-checkbox="checkable"
        :lazy="loadMode === 'lazy'"
        :load="onLoad"
        :default-expand-all="defaultExpandAll"
        :expand-on-click-node="false"
        :filter-node-method="filterNode"
        @node-click="onNodeClick"
        @check="onCheck"
        @node-contextmenu="onNodeContextMenu"
      >
        <template #default="{ data }">
          <span :class="base.nsClass('master-tree-node')">
            <span :class="base.nsClass('master-tree-node-label')">{{ data.label }}</span>
            <span
              v-if="showCount && typeof data.count === 'number'"
              :class="base.nsClass('master-tree-node-count')"
            >
              {{ data.count }}
            </span>
          </span>
        </template>
      </el-tree>
    </div>

    <div
      v-if="menu.visible"
      :class="base.nsClass('master-tree-menu')"
      :style="{ left: `${menu.x}px`, top: `${menu.y}px` }"
    >
      <button
        v-if="canManage"
        type="button"
        :class="base.nsClass('master-tree-menu-item')"
        @click="runMenu('create')"
      >
        {{ t('tree.create') }}
      </button>
      <button
        v-if="canManage"
        type="button"
        :class="base.nsClass('master-tree-menu-item')"
        @click="runMenu('edit')"
      >
        {{ t('tree.edit') }}
      </button>
      <button
        v-if="canManage"
        type="button"
        :class="base.nsClass('master-tree-menu-item')"
        @click="runMenu('delete')"
      >
        {{ t('tree.delete') }}
      </button>
      <button
        type="button"
        :class="base.nsClass('master-tree-menu-item')"
        @click="runMenu('refresh')"
      >
        {{ t('tree.refresh') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.bms-master-tree {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2);
  min-height: 0;
}

.bms-master-tree-toolbar {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
}

.bms-master-tree-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
}

.bms-master-tree-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.bms-master-tree-node {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-1);
  min-width: 0;
}

.bms-master-tree-node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-master-tree-node-count {
  padding: 0 6px;
  border-radius: 8px;
  background: var(--bms-color-bg-page);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  line-height: 16px;
}

.bms-master-tree-menu {
  position: fixed;
  z-index: 2200;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  padding: var(--bms-space-1);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-bg);
  box-shadow: var(--bms-shadow-md);
}

.bms-master-tree-menu-item {
  padding: 6px 10px;
  border: 0;
  border-radius: var(--bms-radius-sm);
  background: transparent;
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  text-align: left;
  cursor: pointer;
}

.bms-master-tree-menu-item:hover {
  background: var(--bms-color-bg-page);
}
</style>
