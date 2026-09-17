<script setup lang="ts">
/**
 * 管理端宿主布局（S5a 切流）：`@bms/ui-ep` 的 `AppLayout` / `SideMenu` / `TabsNav` 组装。
 *
 * - 菜单：`SideMenu` 非受控消费菜单状态注入点（`adapters/ui-bootstrap.ts` 接线菜单 store）；
 * - 标签：`TabsNav` 受控（`adapters/use-app-tabs.ts` → `@bms/vue` `useTabs`，核心 `BaseTabs` 单源）；
 *   路由 watch 开签；内容区 keep-alive 按 `:include`（`cachedNames` 精确缓存）+ `:max` 上限兜底；
 *   refresh 以版本 key 重挂载；
 * - 折叠：`usePersistedState`（本地键 `bms:pref:sidebar-collapsed`）；窄屏侧栏抽屉（`AppLayout` 能力）。
 */

import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { AppLayout, SideMenu, TabsNav } from '@bms/ui-ep'
import { usePersistedState } from '@bms/vue'

import { useAppTabs } from '@/adapters/use-app-tabs'

const route = useRoute()
const { t } = useI18n()

const collapsedStore = usePersistedState<boolean>({ key: 'sidebar-collapsed', defaultValue: false })
const collapsed = computed({
  get: () => Boolean(collapsedStore.get()),
  set: (value: boolean) => collapsedStore.set(value),
})

const layoutRef = ref<{ toggleSidebar: () => void } | null>(null)
const appTabs = useAppTabs()
const refreshVersions = reactive<Record<string, number>>({})

/** keep-alive 精确缓存集（已开标签；`:include`） */
const openedKeys = computed(() => appTabs.cachedNames)

function syncTabFromRoute(): void {
  if (!route.name) {
    return
  }
  const key = String(route.name)
  appTabs.open({
    key,
    name: key,
    title: (route.meta.title as string | undefined) ?? key,
    path: route.path,
  })
}

onMounted(syncTabFromRoute)
watch(() => route.fullPath, syncTabFromRoute)

/** 内容区 key：标签键（路由 name）+ refresh 版本（变更即重挂载） */
const contentKey = computed(() => {
  const name = String(route.name ?? route.path)
  return `${name}#${refreshVersions[name] ?? 0}`
})

function onRefresh(key: string): void {
  refreshVersions[key] = (refreshVersions[key] ?? 0) + 1
}

function onToggleSidebar(): void {
  layoutRef.value?.toggleSidebar()
}
</script>

<template>
  <AppLayout ref="layoutRef" v-model:collapsed="collapsed">
    <template #sidebar>
      <SideMenu :collapsed="collapsed" :active-path="route.path" />
    </template>

    <template #header>
      <el-button size="small" text @click="onToggleSidebar">☰</el-button>
      <span class="bms-layout-header-title">{{ route.meta.title ?? t('app.title') }}</span>
      <span class="bms-layout-header-spacer" />
      <span class="bms-layout-header-placeholder">🌐</span>
      <span class="bms-layout-header-placeholder">🔍</span>
      <span class="bms-layout-header-placeholder">🔔</span>
      <span class="bms-layout-header-placeholder">👤</span>
    </template>

    <template #tabs>
      <TabsNav
        :tabs="appTabs.tabs"
        :active-key="appTabs.activeKey"
        @select="appTabs.activate"
        @close="appTabs.close"
        @close-others="appTabs.closeOthers"
        @close-right="appTabs.closeRight"
        @close-all="appTabs.closeAll"
        @refresh="onRefresh"
      />
    </template>

    <router-view v-slot="{ Component }">
      <keep-alive :include="openedKeys.length ? openedKeys : undefined" :max="12">
        <component :is="Component" :key="contentKey" />
      </keep-alive>
    </router-view>
  </AppLayout>
</template>

<style scoped>
.bms-layout-header-title {
  font-weight: var(--bms-font-weight-medium);
}

.bms-layout-header-spacer {
  flex: 1;
}

.bms-layout-header-placeholder {
  color: var(--bms-color-text-secondary);
  cursor: default;
}
</style>
