<script setup lang="ts">
// 应用根组件：主框架装配（侧栏菜单 + 多标签 + 路由出口 keep-alive）+ 模块边界兜底 + 模块区域插槽。
import { PLACEHOLDER_MENU } from '@bms/core'
import { MainLayout, ModuleAreaOutlet, useSideMenu, useTabNav } from '@bms/ui-ep'
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ModuleBoundary from '@/components/ModuleBoundary.vue'
import { moduleMenuGroups } from '@/module/host'
import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

// 占位阶段：菜单显隐暂全量放行，真实权限码过滤随认证 / RBAC 接入。
const sideMenu = useSideMenu({ menu: PLACEHOLDER_MENU, canAccess: () => true })
const tabNav = useTabNav({ storageKey: 'bms:desktop:tabs' })

// 模块菜单装配泛化：模块经路由 meta 声明菜单（title / icon / group / groupIcon / devOnly），
// 宿主从注册表快照按来源分组装配（不再硬编码 demo 分组）；`devOnly` 项生产态隐藏。
const menu = computed(() => {
  void registriesRevision.value
  return [...sideMenu.menu.value, ...moduleMenuGroups(import.meta.env.DEV)]
})

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
  <!-- 会话就绪前（首屏静默续期 / 登录页判定）：骨架屏等待态，不闪登录页、不白屏。 -->
  <div v-if="!session.ready" class="app-skeleton" data-test="app-skeleton" aria-busy="true">
    <div class="app-skeleton__header"></div>
    <div class="app-skeleton__body">
      <div class="app-skeleton__side"></div>
      <div class="app-skeleton__content">
        <div class="app-skeleton__row"></div>
        <div class="app-skeleton__row app-skeleton__row--short"></div>
        <div class="app-skeleton__block"></div>
      </div>
    </div>
  </div>
  <main-layout
    v-else
    :menu="menu"
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
    <template #header-right>
      <module-area-outlet area="layout.header" :registries="registries" :revision="registriesRevision" />
    </template>
    <module-boundary>
      <router-view v-slot="{ Component }">
        <keep-alive :include="keepAliveNames">
          <component :is="Component" :key="route.fullPath" />
        </keep-alive>
      </router-view>
    </module-boundary>
  </main-layout>
</template>

<style scoped>
.app-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  box-sizing: border-box;
  height: 100vh;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-bg);
}

.app-skeleton__header,
.app-skeleton__side,
.app-skeleton__row,
.app-skeleton__block {
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-fill);
  animation: app-skeleton-pulse 1.4s ease-in-out infinite;
}

.app-skeleton__header {
  height: 48px;
  flex: none;
}

.app-skeleton__body {
  display: flex;
  flex: 1;
  gap: var(--bms-spacing-lg);
  min-height: 0;
}

.app-skeleton__side {
  width: 200px;
  flex: none;
}

.app-skeleton__content {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  min-width: 0;
}

.app-skeleton__row {
  height: 32px;
  flex: none;
}

.app-skeleton__row--short {
  width: 40%;
}

.app-skeleton__block {
  flex: 1;
}

@keyframes app-skeleton-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.55;
  }
}
</style>
