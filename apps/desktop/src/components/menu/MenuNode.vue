<script setup lang="ts">
/**
 * 菜单项（递归）：图标 / 子菜单 / 徽标 / 搜索命中高亮（《组件设计 · 侧边菜单》§2 / §4）。
 *
 * 渲染基于 `el-sub-menu` / `el-menu-item`（fold / hover 弹层 / unique-opened 复用 EP 行为）；
 * 点击导航由父级 `SideMenu` 经 `el-menu` 的 `select` 统一处理。
 */

import { computed } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

import { menuKey, type MenuItem } from './types'

defineOptions({ name: 'MenuNode' })

// 组件根（nsClass；渲染根为 Element Plus 菜单件，透传由其承接）
const base = useComponentBase({ ns: 'bms', identifier: 'menu-node' })

const props = withDefaults(
  defineProps<{
    node: MenuItem
    /** 层级（一级菜单配图标；深度建议 ≤ 3） */
    depth?: number
    /** 搜索关键词（命中高亮） */
    keyword?: string
  }>(),
  { depth: 0, keyword: '' },
)

const children = computed(() => props.node.children ?? [])
const hasChildren = computed(() => children.value.length > 0)
const index = computed(() => menuKey(props.node))
const highlighted = computed(() => {
  const kw = props.keyword.trim().toLowerCase()
  return kw.length > 0 && props.node.name.toLowerCase().includes(kw)
})
</script>

<template>
  <el-sub-menu v-if="hasChildren" :index="index">
    <template #title>
      <span :class="[base.nsClass('menu-label'), highlighted && 'is-hit']">{{ node.name }}</span>
      <span v-if="node.badge" :class="base.nsClass('menu-badge')">{{ node.badge }}</span>
    </template>
    <MenuNode
      v-for="child in children"
      :key="menuKey(child)"
      :node="child"
      :depth="depth + 1"
      :keyword="keyword"
    />
  </el-sub-menu>

  <el-menu-item v-else :index="index">
    <span :class="[base.nsClass('menu-label'), highlighted && 'is-hit']">{{ node.name }}</span>
    <span v-if="node.badge" :class="base.nsClass('menu-badge')">{{ node.badge }}</span>
  </el-menu-item>
</template>

<style scoped>
.bms-menu-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-menu-label.is-hit {
  color: var(--bms-color-primary);
  font-weight: var(--bms-font-weight-medium);
}

.bms-menu-badge {
  margin-left: auto;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--bms-color-danger);
  color: var(--bms-color-text-inverse);
  font-size: var(--bms-font-size-xs);
  line-height: 16px;
}
</style>
