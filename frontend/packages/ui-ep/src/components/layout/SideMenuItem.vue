<script setup lang="ts">
// 侧边菜单项（递归）：有子节点渲染子菜单，否则渲染菜单项（含徽标）。
import type { MenuNode } from '@bms/core'
import { ElBadge, ElMenuItem, ElSubMenu } from 'element-plus'

defineOptions({ name: 'SideMenuItem' })

interface Props {
  /** 菜单节点。 */
  node: MenuNode
  /** 是否展示徽标。 */
  showBadge?: boolean
}

withDefaults(defineProps<Props>(), { showBadge: true })
</script>

<template>
  <el-sub-menu v-if="node.children !== undefined && node.children.length > 0" :index="node.path">
    <template #title>
      <span class="bms-side-menu__title" :data-test="`menu-sub-${node.path}`">{{ node.title }}</span>
    </template>
    <side-menu-item v-for="child in node.children" :key="child.path" :node="child" :show-badge="showBadge" />
  </el-sub-menu>
  <el-menu-item v-else :index="node.path">
    <span class="bms-side-menu__title" :data-test="`menu-item-${node.path}`">
      <el-badge v-if="showBadge && node.badge !== undefined" :value="node.badge" class="bms-side-menu__badge">
        {{ node.title }}
      </el-badge>
      <template v-else>{{ node.title }}</template>
    </span>
  </el-menu-item>
</template>
