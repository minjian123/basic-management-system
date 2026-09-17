<script setup lang="ts">
/**
 * 侧边菜单：动态菜单树渲染、折叠、搜索、当前高亮、徽标可选、外链（《组件设计 · 侧边菜单》）。
 *
 * - 数据源：`menus` 传数组即受控；传 `null` 消费 `stores/menu.ts`（占位 loader 可注入）；
 * - 渲染基于 `el-menu`（收起仅图标 + hover 弹层 / `unique-open` 手风琴复用 EP 行为）；
 * - 高亮 `default-active` + 父级自动展开；搜索本地过滤（保留父链）；`external` 新开窗口；
 * - 图标（`IconDisplay`）回补前不渲染；折叠状态持久化归宿主（`03_05`）。
 */

import { ElInput, ElMenu } from 'element-plus'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/menu/style/css'

import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref, useAttrs, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useComponentBase } from '@bms/vue'
import EmptyState from '../feedback/EmptyState.vue'
import MenuNode from './MenuNode.vue'
import { getMenuSource } from './menuSource'
import { filterMenuTree, findAncestorKeys, menuKey, sortVisible, type MenuItem } from './types'

const props = withDefaults(
  defineProps<{
    /** 菜单树；传数组即受控，传 `null` 即消费 menu store（占位 loader 可注入） */
    menus?: MenuItem[] | null
    collapsed?: boolean
    /** 当前路由 path（高亮与父级自动展开） */
    activePath?: string
    /** 是否显示菜单搜索（布局设计：> 30 项时提供） */
    searchable?: boolean
    /** 同级只展开一个子菜单（手风琴） */
    uniqueOpen?: boolean
    theme?: 'light' | 'dark'
  }>(),
  {
    menus: null,
    collapsed: false,
    activePath: '',
    searchable: true,
    uniqueOpen: false,
    theme: 'light',
  },
)

const emit = defineEmits<{ navigate: [item: MenuItem] }>()

const base = useComponentBase({ ns: 'bms', identifier: 'side-menu' })
const { t } = useI18n()
const attrs = useAttrs()
const router = useRouter()

/** 受控性在生命周期内固定：传 `menus` 数组即受控 */
const controlled = props.menus !== null
const keyword = ref('')

interface MenuExpose {
  open?: (index: string) => void
  close?: (index: string) => void
}
const menuRef = ref<MenuExpose | null>(null)

const source = computed<MenuItem[]>(() =>
  sortVisible(controlled ? (props.menus ?? []) : (getMenuSource()?.visibleMenus() ?? [])),
)
/** 非受控初始展开集（注入读取一次；后续展开由 EP 承接并回写注入点） */
const initialOpeneds = controlled ? undefined : (getMenuSource()?.expandedKeys() ?? [])
const filteredSource = computed(() => filterMenuTree(source.value, keyword.value))

function openChain(path: string): void {
  const chain = findAncestorKeys(source.value, path) ?? []
  void nextTick(() => {
    for (const key of chain) {
      menuRef.value?.open?.(key)
    }
  })
  if (!controlled) {
    getMenuSource()?.expandByPath(path)
  }
}

watch(() => props.activePath, (path) => {
  if (path) {
    openChain(path)
  }
}, { immediate: true })

function findItem(items: MenuItem[], key: string): MenuItem | null {
  for (const item of items) {
    if (menuKey(item) === key) {
      return item
    }
    if (item.children) {
      const found = findItem(item.children, key)
      if (found) {
        return found
      }
    }
  }
  return null
}

function onSelect(index: string): void {
  const item = findItem(filteredSource.value, index)
  if (!item) {
    return
  }
  if (item.external && item.path) {
    if (typeof window !== 'undefined') {
      window.open(item.path, '_blank')
    }
    return
  }
  emit('navigate', item)
  if (router && item.path) {
    void router.push(item.path)
  }
}

function onOpen(index: string): void {
  if (!controlled) {
    getMenuSource()?.setExpanded(index, true)
  }
}

function onClose(index: string): void {
  if (!controlled) {
    getMenuSource()?.setExpanded(index, false)
  }
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('side-menu'), props.theme === 'dark' && base.nsClass('side-menu--dark'), cls],
    style: sty,
    ...rest,
  })
})

defineExpose({
  /** 设置搜索关键词（`''` 清除） */
  filter: (value: string) => {
    keyword.value = value
  },
  /** 展开目标 path 的祖先链（并持久化，非受控） */
  expandByPath: (path: string) => openChain(path),
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('side-menu')">
    <div v-if="searchable && !collapsed" :class="base.nsClass('side-menu-search')">
      <el-input
        v-model="keyword"
        size="small"
        clearable
        :placeholder="t('menu.searchPlaceholder')"
      />
    </div>

    <el-menu
      ref="menuRef"
      :collapse="collapsed"
      :default-active="activePath"
      :default-openeds="initialOpeneds"
      :unique-opened="uniqueOpen"
      :collapse-transition="false"
      @select="onSelect"
      @open="onOpen"
      @close="onClose"
    >
      <MenuNode
        v-for="item in filteredSource"
        :key="menuKey(item)"
        :node="item"
        :keyword="keyword"
      />
    </el-menu>

    <EmptyState
      v-if="filteredSource.length === 0"
      type="custom"
      size="small"
      :title="keyword ? t('menu.noMatch') : t('menu.empty')"
    />
  </div>
</template>

<style scoped>
.bms-side-menu {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  padding: var(--bms-space-1);
  background: var(--bms-color-bg);
  overflow-y: auto;
}

.bms-side-menu-search {
  padding: var(--bms-space-1) var(--bms-space-1) 0;
}

.bms-side-menu--dark {
  background: var(--bms-color-bg-page);
}
</style>
