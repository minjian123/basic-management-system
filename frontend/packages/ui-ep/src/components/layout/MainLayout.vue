<script setup lang="ts">
// 主框架布局壳：侧栏 + 顶栏 + 多标签栏 + 内容区（折叠持久化 / 断点响应式 / 区域插槽）。
import type { MenuNode } from '@bms/core'
import { ElDrawer } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { useBaseLayout } from '../../composables/useBaseLayout'
import { useBasePersistedState } from '../../composables/useBasePersistedState'
import { useResponsive } from '../../composables/useResponsive'
import type { TabNavItem } from '../../composables/useTabNav'
import SideMenu from './SideMenu.vue'
import TabNavBar from './TabNavBar.vue'

interface Props {
  /** 菜单树。 */
  menu: MenuNode[]
  /** 当前激活路径。 */
  activePath: string
  /** 侧栏折叠（`v-model`）。 */
  collapsed?: boolean
  /** 是否显示多标签栏。 */
  showTabs?: boolean
  /** 是否显示侧栏。 */
  showSidebar?: boolean
  /** 页签。 */
  tabs?: TabNavItem[]
  /** 激活页签键。 */
  activeTabKey?: string
  /** 覆盖断点。 */
  breakpoints?: { mobile?: number; narrow?: number; wide?: number }
  /** 折叠持久化键。 */
  storageKey?: string
  /** 应用标题。 */
  appTitle?: string
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: undefined,
  showTabs: true,
  showSidebar: true,
  tabs: () => [],
  activeTabKey: '',
  breakpoints: undefined,
  storageKey: '',
  appTitle: '',
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'update:showTabs': [value: boolean]
  'menu-select': [path: string]
  'tab-select': [key: string]
  'tab-close': [key: string]
  'tab-close-others': [key: string]
  'tab-close-right': [key: string]
  'tab-close-all': []
  'tab-refresh': [key: string]
  'breakpoint-change': [name: string]
}>()

const { hidden } = useBaseLayout()
const persisted = useBasePersistedState({ stateKey: props.storageKey })
const { collapsed: collapsedState, setCollapsed, toggle } = useBaseContainer({ collapsible: true, collapsed: false })
const { breakpoint, isMobile, isNarrow } = useResponsive({ breakpoints: props.breakpoints })

const drawerOpen = ref(false)

const restored = (persisted.local.value as { collapsed?: boolean } | undefined)?.collapsed
setCollapsed(props.collapsed ?? restored ?? false)

function writeStorage(value: boolean): void {
  if (props.storageKey === '') {
    return
  }
  try {
    sessionStorage.setItem(props.storageKey, JSON.stringify({ collapsed: value }))
  } catch {
    // 隐私模式等场景降级为不持久化。
  }
}

watch(
  () => props.collapsed,
  (value) => {
    if (value !== undefined) {
      setCollapsed(value)
    }
  },
)
watch(collapsedState, (value) => {
  persisted.setLocal({ collapsed: value })
  writeStorage(value)
})
watch(
  () => breakpoint.value,
  (name) => {
    if (props.breakpoints === undefined && isNarrow.value) {
      setCollapsed(true)
    }
    emit('breakpoint-change', name)
  },
  { immediate: true },
)
watch(
  () => props.activePath,
  () => {
    drawerOpen.value = false
  },
)

const sidebarWidth = computed(() => (collapsedState.value ? '64px' : '220px'))

function onToggle(): void {
  if (isMobile.value) {
    drawerOpen.value = !drawerOpen.value
    return
  }
  toggle()
  emit('update:collapsed', collapsedState.value)
}

function onTabSelect(key: string): void {
  emit('tab-select', key)
}
</script>

<template>
  <div
    v-show="!hidden"
    class="bms-main-layout"
    :class="{ 'is-collapsed': collapsedState, 'is-mobile': isMobile }"
    :data-breakpoint="breakpoint"
  >
    <aside v-if="showSidebar && !isMobile" class="bms-main-layout__sidebar" :style="{ width: sidebarWidth }">
      <div class="bms-main-layout__logo">
        <slot name="logo">{{ appTitle }}</slot>
      </div>
      <side-menu :menu="menu" :active-path="activePath" :collapsed="collapsedState" @select="emit('menu-select', $event)" />
    </aside>

    <el-drawer v-if="showSidebar && isMobile" v-model="drawerOpen" direction="ltr" size="240px" :with-header="false">
      <side-menu :menu="menu" :active-path="activePath" :searchable="false" @select="emit('menu-select', $event)" />
    </el-drawer>

    <div class="bms-main-layout__main">
      <header class="bms-main-layout__header">
        <div class="bms-main-layout__header-left">
          <button class="bms-main-layout__toggle" data-test="layout-toggle" @click="onToggle">
            {{ collapsedState ? '»' : '«' }}
          </button>
          <slot name="header-left" />
        </div>
        <div class="bms-main-layout__header-right">
          <slot name="header-right" />
        </div>
      </header>

      <tab-nav-bar
        v-if="showTabs"
        class="bms-main-layout__tabs"
        :tabs="tabs"
        :active-key="activeTabKey"
        @select="onTabSelect"
        @close="emit('tab-close', $event)"
        @close-others="emit('tab-close-others', $event)"
        @close-right="emit('tab-close-right', $event)"
        @close-all="emit('tab-close-all')"
        @refresh="emit('tab-refresh', $event)"
      />

      <main class="bms-main-layout__content">
        <slot />
      </main>
    </div>
  </div>
</template>
