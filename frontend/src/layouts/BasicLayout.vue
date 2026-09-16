<script setup lang="ts">
/**
 * 管理端宿主布局：`AppLayout` 组装（侧栏 / 顶栏占位 / 标签栏 / 内容区）。
 *
 * - 菜单：`SideMenu` 消费 `stores/menu`（占位 loader 由 `main.ts` 注入）；菜单 → 路由注册见 `router/menuRoutes.ts`；
 * - 标签：`TabsNav` 非受控（路由 watch 开签）；内容区 keep-alive 按 `:include`（已开标签签精确缓存；
 *   关闭标签即时释放）+ `:max`（= maxOpen 12）上限兜底；refresh 以版本 key 重挂载；
 * - 折叠：`usePersistedState`（本地键 `bms:pref:sidebar-collapsed`）；窄屏侧栏抽屉（`AppLayout` 能力）。
 */

import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { usePersistedState } from '@/components/base/persisted-state'
import AppLayout from '@/components/layout/AppLayout.vue'
import { SideMenu } from '@/components/menu'
import { TabsNav } from '@/components/tabs'

interface TabsNavExpose {
  openTab: (tab: { key: string; name?: string; title: string; path: string }) => void
  closeTab: (key: string) => void
  readonly cachedNames: string[]
}

const route = useRoute()
const { t } = useI18n()

const collapsedStore = usePersistedState<boolean>({ key: 'sidebar-collapsed', defaultValue: false })
const collapsed = computed({
  get: () => Boolean(collapsedStore.get()),
  set: (value: boolean) => collapsedStore.set(value),
})

const layoutRef = ref<{ toggleSidebar: () => void } | null>(null)
const tabsRef = ref<TabsNavExpose | null>(null)
const refreshVersions = reactive<Record<string, number>>({})

/**
 * keep-alive 精确缓存集（已开标签签；`:include`）。
 *
 * - 首签在 setup 预置（首渲染即命中，避免空 `:include` 空数组被判定为「不匹配」而不缓存）；
 * - 开签随路由（`syncTabFromRoute`）；关闭 / 批量关闭 / 超限自动关闭经 `TabsNav` 事件重读其清单
 *   （`cachedNames`），移除即释放对应缓存（keep-alive 按组件名 prune）；
 * - 列表为空时传 `undefined`（不做裁剪）。
 */
const openedKeys = ref<string[]>(route.name ? [String(route.name)] : [])

function syncOpenedFromTabs(): void {
  const names = tabsRef.value?.cachedNames
  if (names) {
    openedKeys.value = [...names]
  }
}

function syncTabFromRoute(): void {
  if (!route.name) {
    return
  }
  const key = String(route.name)
  tabsRef.value?.openTab({
    key,
    name: key,
    title: (route.meta.title as string | undefined) ?? key,
    path: route.path,
  })
  if (!openedKeys.value.includes(key)) {
    openedKeys.value = [...openedKeys.value, key]
  }
}

// 首签在挂载后打开（模板 ref 已绑定）；后续随路由变化
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
        ref="tabsRef"
        @refresh="onRefresh"
        @close="syncOpenedFromTabs"
        @close-others="syncOpenedFromTabs"
        @close-right="syncOpenedFromTabs"
        @close-all="syncOpenedFromTabs"
        @exceed="syncOpenedFromTabs"
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
