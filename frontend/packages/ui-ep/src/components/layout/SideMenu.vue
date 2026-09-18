<script setup lang="ts">
// 侧边菜单：多级菜单渲染 + 折叠 + 搜索过滤 + 徽标 + 展开互斥。
import { filterMenuByKeyword, type MenuNode } from '@bms/core'
import { ElInput, ElMenu } from 'element-plus'
import { computed, ref } from 'vue'

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
  searchable: true,
  searchPlaceholder: '搜索菜单',
  showBadge: true,
})

const emit = defineEmits<{ select: [path: string]; 'update:collapsed': [value: boolean]; search: [keyword: string] }>()

const keyword = ref('')
const filteredMenu = computed(() => filterMenuByKeyword(props.menu, keyword.value))

function onSearch(): void {
  emit('search', keyword.value)
}
</script>

<template>
  <div class="bms-side-menu" :class="{ 'is-collapsed': collapsed }">
    <div v-if="$slots.logo" class="bms-side-menu__logo">
      <slot name="logo" />
    </div>
    <div v-if="searchable" class="bms-side-menu__search">
      <el-input v-model="keyword" :placeholder="searchPlaceholder" clearable @input="onSearch" />
    </div>
    <el-menu
      class="bms-side-menu__menu"
      :default-active="activePath"
      :collapse="collapsed"
      :unique-opened="uniqueOpened"
      @select="emit('select', $event)"
    >
      <side-menu-item v-for="node in filteredMenu" :key="node.path" :node="node" :show-badge="showBadge" />
    </el-menu>
    <div v-if="$slots.footer" class="bms-side-menu__footer">
      <slot name="footer" />
    </div>
  </div>
</template>
