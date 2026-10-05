<script setup lang="ts">
// 侧边菜单：多级菜单渲染 + 折叠 + 搜索过滤 + 徽标 + 展开互斥。
import { filterMenuByKeyword, type MenuNode } from '@bms/core'
import { ElInput, ElMenu } from 'element-plus'
import { computed, ref } from 'vue'

import { useBaseLayout } from '../../composables/useBaseLayout'
import SideMenuItem from './SideMenuItem.vue'

interface Props {
  /** 菜单树。 */
  menu: MenuNode[]
  /** 当前激活路径。 */
  activePath: string
  /** 是否折叠。 */
  collapsed?: boolean
  /** 多级展开互斥。 */
  uniqueOpened?: boolean
  /** 默认展开的子菜单路径（初始展开；后续展开态由 `open` / `close` 事件回传）。 */
  defaultOpeneds?: string[]
  /** 是否显示搜索框。 */
  searchable?: boolean
  /** 搜索占位。 */
  searchPlaceholder?: string
  /** 是否展示徽标。 */
  showBadge?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: false,
  uniqueOpened: true,
  defaultOpeneds: undefined,
  searchable: true,
  searchPlaceholder: '搜索菜单',
  showBadge: true,
})

const emit = defineEmits<{
  select: [path: string]
  'update:collapsed': [value: boolean]
  search: [keyword: string]
  open: [index: string]
  close: [index: string]
}>()

const { hidden } = useBaseLayout()
const keyword = ref('')
const filteredMenu = computed(() => filterMenuByKeyword(props.menu, keyword.value))

function onSearch(): void {
  emit('search', keyword.value)
}
</script>

<template>
  <div v-show="!hidden" class="bms-side-menu" :class="{ 'is-collapsed': collapsed }">
    <div v-if="$slots.logo" class="bms-side-menu__logo">
      <slot name="logo" />
    </div>
    <div v-if="searchable" class="bms-side-menu__search">
      <el-input v-model="keyword" size="small" :placeholder="searchPlaceholder" clearable @input="onSearch" />
    </div>
    <el-menu
      class="bms-side-menu__menu"
      :default-active="activePath"
      :collapse="collapsed"
      :unique-opened="uniqueOpened"
      :default-openeds="defaultOpeneds"
      @select="emit('select', $event)"
      @open="emit('open', $event)"
      @close="emit('close', $event)"
    >
      <side-menu-item v-for="node in filteredMenu" :key="node.path" :node="node" :show-badge="showBadge" />
    </el-menu>
    <div v-if="$slots.footer" class="bms-side-menu__footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.bms-side-menu {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--bms-color-bg);
}

.bms-side-menu__logo {
  display: flex;
  flex: none;
  align-items: center;
  height: var(--bms-layout-header-height);
  padding: 0 var(--bms-space-4);
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-side-menu__search {
  flex: none;
  padding: var(--bms-space-2) var(--bms-space-3);
}

.bms-side-menu__menu {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  border-right: none;
}

.bms-side-menu.is-collapsed .bms-side-menu__search {
  display: none;
}

.bms-side-menu__footer {
  flex: none;
  padding: var(--bms-space-2) var(--bms-space-3);
  border-top: 1px solid var(--bms-color-border);
}
</style>
