<script setup lang="ts">
// 应用根组件：主框架装配（侧栏菜单 + 多标签 + 路由出口 keep-alive）。
import { PLACEHOLDER_MENU } from '@bms/core'
import { MainLayout, useSideMenu, useTabNav } from '@bms/ui-ep'
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()

// 占位阶段：菜单显隐暂全量放行，真实权限码过滤随认证 / RBAC 接入。
const sideMenu = useSideMenu({ menu: PLACEHOLDER_MENU, canAccess: () => true })
const tabNav = useTabNav({ storageKey: 'bms:desktop:tabs' })

watch(
  () => route.fullPath,
  () => {
    tabNav.open({
      key: route.fullPath,
      title: String(route.meta.title ?? route.name ?? route.path),
      path: route.fullPath,
      name: typeof route.name === 'string' ? route.name : '',
      keepAlive: route.meta.keepAlive === true,
      closable: route.path !== '/',
    })
  },
  { immediate: true },
)

// keep-alive 名单：`meta.keepAlive`（页签 keepAlive）∩ 已打开页签，按组件名缓存。
const keepAliveNames = computed(() =>
  tabNav.tabs.value
    .filter((item) => item.keepAlive === true && tabNav.cachedKeys.value.includes(item.key))
    .map((item) => item.name)
    .filter((name): name is string => typeof name === 'string' && name !== ''),
)

function onMenuSelect(path: string): void {
  void router.push(path)
}

function onTabSelect(key: string): void {
  void router.push(key)
}

async function onTabClose(key: string): Promise<void> {
  const active = tabNav.activeKey.value
  const closed = await tabNav.close(key)
  if (closed && key === route.fullPath) {
    void router.push(active)
  }
}
</script>

<template>
  <main-layout
    :menu="sideMenu.menu.value"
    :active-path="route.path"
    :tabs="tabNav.tabs.value"
    :active-tab-key="tabNav.activeKey.value"
    app-title="BMS"
    storage-key="bms:desktop:layout"
    @menu-select="onMenuSelect"
    @tab-select="onTabSelect"
    @tab-close="onTabClose"
    @tab-close-others="tabNav.closeOthers"
    @tab-close-right="tabNav.closeRight"
    @tab-close-all="tabNav.closeAll"
    @tab-refresh="tabNav.refresh"
  >
    <router-view v-slot="{ Component }">
      <keep-alive :include="keepAliveNames">
        <component :is="Component" :key="route.fullPath" />
      </keep-alive>
    </router-view>
  </main-layout>
</template>
