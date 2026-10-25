<script setup lang="ts">
// 侧边菜单项（递归）：有子节点渲染子菜单，否则渲染菜单项（含图标与徽标）。
import type { MenuNode } from '@bms/core'
import { ElBadge, ElMenuItem, ElSubMenu } from 'element-plus'

import { useBaseLayout } from '../../composables/useBaseLayout'
import IconRenderer from '../interaction/IconRenderer.vue'

defineOptions({ name: 'SideMenuItem' })

interface Props {
  /** 菜单节点。 */
  node: MenuNode
  /** 是否展示徽标。 */
  showBadge?: boolean
}

withDefaults(defineProps<Props>(), { showBadge: true })

const { hidden } = useBaseLayout()
</script>

<template>
  <el-sub-menu v-if="node.children !== undefined && node.children.length > 0" v-show="!hidden" :index="node.path">
    <template #title>
      <!-- 图标置于标题 span 之外：Element Plus 折叠态会隐藏 `.el-sub-menu__title > span`，包在 span 内会被一并隐藏 -->
      <i v-if="node.icon" class="bms-side-menu__icon">
        <icon-renderer :name="node.icon" :size="16" fallback="" />
      </i>
      <span class="bms-side-menu__title" :data-test="`menu-sub-${node.path}`">{{ node.title }}</span>
    </template>
    <side-menu-item v-for="child in node.children" :key="child.path" :node="child" :show-badge="showBadge" />
  </el-sub-menu>
  <el-menu-item v-else v-show="!hidden" :index="node.path">
    <i v-if="node.icon" class="bms-side-menu__icon">
      <icon-renderer :name="node.icon" :size="16" fallback="" />
    </i>
    <span class="bms-side-menu__title" :data-test="`menu-item-${node.path}`">
      <el-badge v-if="showBadge && node.badge !== undefined" :value="node.badge" class="bms-side-menu__badge">
        {{ node.title }}
      </el-badge>
      <template v-else>{{ node.title }}</template>
    </span>
  </el-menu-item>
</template>

<style scoped>
.bms-side-menu__icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  margin-right: var(--bms-space-2);
  font-style: normal;
}

.bms-side-menu__title {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  gap: var(--bms-space-2);
}

.bms-side-menu__badge {
  margin-right: var(--bms-space-4);
}
</style>
