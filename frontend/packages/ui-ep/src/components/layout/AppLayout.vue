<script setup lang="ts">
/**
 * 主框架布局壳：侧栏 / 顶栏 / 标签栏 / 内容区区域编排（《组件设计 · 主框架布局壳》）。
 *
 * - 范围边界：侧边菜单（`03_04`）、多标签（`03_03`）、顶栏元素归各专用组件 / 使用方插槽，本件只做骨架与区域；
 * - 折叠：`collapsed`（v-model）220 ↔ 64px；窄屏（< 768px）侧栏收进抽屉（`sidebar` 插槽不双渲染）；
 * - 令牌消费（背景 / 边框 / 间距）；顶栏高度与侧栏宽度支持覆盖。
 */

import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'

import { computed, onBeforeUnmount, onMounted, ref, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    collapsed?: boolean
    showTabs?: boolean
    showSidebar?: boolean
    headerHeight?: number
    sidebarWidth?: number
  }>(),
  { collapsed: false, showTabs: true, showSidebar: true, headerHeight: 56, sidebarWidth: 220 },
)

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'resize-breakpoint': [mode: 'wide' | 'narrow']
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'app-layout' })
const attrs = useAttrs()

const isNarrow = ref(false)
const drawerVisible = ref(false)
let mql: MediaQueryList | null = null

function onMqlChange(event: MediaQueryListEvent): void {
  isNarrow.value = event.matches
  emit('resize-breakpoint', event.matches ? 'narrow' : 'wide')
  if (!event.matches) {
    drawerVisible.value = false
  }
}

onMounted(() => {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    mql = window.matchMedia('(max-width: 767px)')
    isNarrow.value = mql.matches
    mql.addEventListener('change', onMqlChange)
  }
})

onBeforeUnmount(() => {
  mql?.removeEventListener('change', onMqlChange)
})

const sidebarSize = computed(() => (props.collapsed ? 64 : props.sidebarWidth))

/** 顶栏折叠按钮入口：宽屏切换折叠；窄屏切换侧栏抽屉 */
function toggleSidebar(): void {
  if (isNarrow.value) {
    drawerVisible.value = !drawerVisible.value
    return
  }
  emit('update:collapsed', !props.collapsed)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('app-layout'), isNarrow.value && 'is-narrow', cls],
    style: sty,
    ...rest,
  })
})

defineExpose({ toggleSidebar })
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('app-layout')">
    <aside
      v-if="showSidebar && !isNarrow"
      :class="base.nsClass('app-layout-sidebar')"
      :style="{ width: `${sidebarSize}px` }"
    >
      <slot name="sidebar" />
    </aside>

    <div :class="base.nsClass('app-layout-main')">
      <header :class="base.nsClass('app-layout-header')" :style="{ height: `${headerHeight}px` }">
        <slot name="header" />
      </header>

      <div v-if="showTabs" :class="base.nsClass('app-layout-tabs')">
        <slot name="tabs" />
      </div>

      <main :class="base.nsClass('app-layout-content')">
        <slot />
      </main>

      <footer v-if="$slots.footer" :class="base.nsClass('app-layout-footer')">
        <slot name="footer" />
      </footer>
    </div>

    <el-drawer
      v-if="showSidebar"
      v-model="drawerVisible"
      direction="ltr"
      size="240px"
      :with-header="false"
    >
      <slot name="sidebar" />
    </el-drawer>
  </div>
</template>

<style scoped>
.bms-app-layout {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--bms-color-bg-page);
}

.bms-app-layout-sidebar {
  flex: none;
  min-height: 0;
  overflow: hidden auto;
  border-right: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
  transition: width 0.2s ease;
}

.bms-app-layout-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.bms-app-layout-header {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-2);
  padding: 0 var(--bms-space-3);
  border-bottom: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
}

.bms-app-layout-tabs {
  flex: none;
}

.bms-app-layout-content {
  flex: 1;
  min-height: 0;
  padding: var(--bms-space-4);
  overflow: auto;
}

.bms-app-layout-footer {
  flex: none;
  border-top: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
}
</style>
