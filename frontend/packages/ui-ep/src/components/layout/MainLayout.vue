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
  /** 侧栏多级展开互斥。 */
  uniqueOpened?: boolean
  /** 侧栏默认展开的子菜单路径（展开态持久化用）。 */
  defaultOpeneds?: string[]
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
  uniqueOpened: true,
  defaultOpeneds: undefined,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'update:showTabs': [value: boolean]
  'menu-select': [path: string]
  'menu-open': [index: string]
  'menu-close': [index: string]
  'tab-select': [key: string]
  'tab-close': [key: string]
  'tab-close-others': [key: string]
  'tab-close-right': [key: string]
  'tab-close-all': []
  'tab-refresh': [key: string]
  'breakpoint-change': [name: string]
}>()

const { hidden } = useBaseLayout()
const persisted = useBasePersistedState({ stateKey: props.storageKey, storage: 'session' })
const { collapsed: collapsedState, setCollapsed, toggle } = useBaseContainer({ collapsible: true, collapsed: false })
const { breakpoint, isMobile, isNarrow } = useResponsive({ breakpoints: props.breakpoints })

const drawerOpen = ref(false)

const restored = (persisted.local.value as { collapsed?: boolean } | undefined)?.collapsed
setCollapsed(props.collapsed ?? restored ?? false)

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
  persisted.persist()
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

const sidebarWidth = computed(() =>
  collapsedState.value
    ? 'var(--bms-layout-sidebar-collapsed-width, 64px)'
    : 'var(--bms-layout-sidebar-width, 220px)',
)

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
    <!-- 顶栏：56px 全宽横条（跨侧栏，随侧栏折叠联动；《布局设计 · 导航》§1.1 / §3） -->
    <header class="bms-main-layout__header">
      <div class="bms-main-layout__header-left">
        <button class="bms-main-layout__toggle" data-test="layout-toggle" aria-label="折叠/展开侧边栏" @click="onToggle">
          ☰
        </button>
        <slot name="header-left" />
      </div>
      <div class="bms-main-layout__header-right">
        <slot name="header-right" />
      </div>
    </header>

    <div class="bms-main-layout__body">
      <aside v-if="showSidebar && !isMobile" class="bms-main-layout__sidebar" :style="{ width: sidebarWidth }">
        <div class="bms-main-layout__logo">
          <slot name="logo">
            <span class="bms-main-layout__logo-mark" aria-hidden="true">☰</span>
            <span class="bms-main-layout__logo-title">{{ appTitle }}</span>
          </slot>
        </div>
        <side-menu
          :menu="menu"
          :active-path="activePath"
          :collapsed="collapsedState"
          :unique-opened="uniqueOpened"
          :default-openeds="defaultOpeneds"
          @select="emit('menu-select', $event)"
          @open="emit('menu-open', $event)"
          @close="emit('menu-close', $event)"
        />
      </aside>

      <el-drawer v-if="showSidebar && isMobile" v-model="drawerOpen" direction="ltr" size="240px" :with-header="false">
        <side-menu
          :menu="menu"
          :active-path="activePath"
          :searchable="false"
          :unique-opened="uniqueOpened"
          :default-openeds="defaultOpeneds"
          @select="emit('menu-select', $event)"
          @open="emit('menu-open', $event)"
          @close="emit('menu-close', $event)"
        />
      </el-drawer>

      <div class="bms-main-layout__main">
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
  </div>
</template>

<style scoped>
.bms-main-layout {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

/* 顶栏以下的双栏区（侧栏 + 内容栏）；顶栏为全宽横条，不在此容器内。 */
.bms-main-layout__body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.bms-main-layout__sidebar {
  display: flex;
  flex: none;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--bms-color-bg);
  border-right: 1px solid var(--bms-color-border);
  transition: width 0.2s ease;
}

.bms-main-layout__logo {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-3) var(--bms-space-4);
  font-weight: 600;
  color: var(--bms-color-text);
  white-space: nowrap;
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-main-layout__logo-mark {
  flex: none;
  color: var(--bms-color-text-secondary);
}

.bms-main-layout__logo-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.bms-main-layout.is-collapsed .bms-main-layout__logo {
  justify-content: center;
  padding: var(--bms-space-3) 0;
}

.bms-main-layout.is-collapsed .bms-main-layout__logo-title {
  display: none;
}

.bms-main-layout__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.bms-main-layout__header {
  display: flex;
  flex: none;
  align-items: center;
  height: var(--bms-layout-header-height);
  padding: 0 var(--bms-space-4);
  gap: var(--bms-space-4);
  background: var(--bms-color-bg);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-main-layout__header-left,
.bms-main-layout__header-right {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--bms-space-3);
}

.bms-main-layout__header-right {
  margin-left: auto;
}

.bms-main-layout__toggle {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--bms-control-height);
  height: var(--bms-control-height);
  padding: 0;
  font-size: var(--bms-font-size-lg);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--bms-radius-md);
}

.bms-main-layout__toggle:hover {
  color: var(--bms-color-primary);
  background: var(--bms-color-fill);
}

.bms-main-layout__toggle:focus-visible {
  outline: 2px solid var(--bms-color-focus-ring);
  outline-offset: 1px;
}

.bms-main-layout__tabs {
  flex: none;
}

.bms-main-layout__content {
  flex: 1;
  min-height: 0;
  padding: var(--bms-layout-content-padding, 24px);
  overflow: auto;
  background: var(--bms-color-bg-page);
}
</style>
