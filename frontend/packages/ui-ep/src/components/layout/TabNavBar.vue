<script setup lang="ts">
// 页签导航条：页签列表 + 关闭按钮 + 超出折叠 + 右键菜单。
import { computed, ref } from 'vue'

import type { TabNavItem } from '../../composables/useTabNav'

import { useBaseLayout } from '../../composables/useBaseLayout'
import TabNavContextMenu from './TabNavContextMenu.vue'

interface Props {
  /** 页签。 */
  tabs: TabNavItem[]
  /** 当前激活键。 */
  activeKey: string
  /** 可见页签数（超出折叠进「更多」；0 表示不折叠）。 */
  maxVisible?: number
}

const props = withDefaults(defineProps<Props>(), { maxVisible: 0 })

const { hidden } = useBaseLayout()

const emit = defineEmits<{
  select: [key: string]
  close: [key: string]
  'close-others': [key: string]
  'close-right': [key: string]
  'close-all': []
  refresh: [key: string]
}>()

const showMore = ref(false)
const context = ref<{ visible: boolean; x: number; y: number; key: string }>({
  visible: false,
  x: 0,
  y: 0,
  key: '',
})

const visibleTabs = computed(() => (props.maxVisible > 0 ? props.tabs.slice(0, props.maxVisible) : props.tabs))
const moreTabs = computed(() => (props.maxVisible > 0 ? props.tabs.slice(props.maxVisible) : []))
const contextItem = computed(() => props.tabs.find((tab) => tab.key === context.value.key))

function onContextMenu(event: MouseEvent, tab: TabNavItem): void {
  event.preventDefault()
  context.value = { visible: true, x: event.clientX, y: event.clientY, key: tab.key }
}

function onAction(action: string): void {
  const key = context.value.key
  context.value.visible = false
  if (action === 'close-all') {
    emit('close-all')
    return
  }
  if (action === 'close') {
    emit('close', key)
    return
  }
  if (action === 'close-others') {
    emit('close-others', key)
    return
  }
  if (action === 'close-right') {
    emit('close-right', key)
    return
  }
  if (action === 'refresh') {
    emit('refresh', key)
  }
}

function onMoreSelect(key: string): void {
  showMore.value = false
  emit('select', key)
}
</script>

<template>
  <div v-show="!hidden" class="bms-tab-nav" data-test="tab-nav">
    <div
      v-for="tab in visibleTabs"
      :key="tab.key"
      class="bms-tab-nav__item"
      :class="{ 'is-active': tab.key === activeKey }"
      :data-test="`tab-${tab.key}`"
      @click="emit('select', tab.key)"
      @contextmenu="onContextMenu($event, tab)"
    >
      <span class="bms-tab-nav__title">{{ tab.title }}</span>
      <button
        v-if="tab.closable !== false"
        class="bms-tab-nav__close"
        :data-test="`tab-close-${tab.key}`"
        @click.stop="emit('close', tab.key)"
      >
        ×
      </button>
    </div>
    <div v-if="moreTabs.length > 0" class="bms-tab-nav__more">
      <button data-test="tab-more" @click="showMore = !showMore">更多</button>
      <div v-if="showMore" class="bms-tab-nav__more-list">
        <button
          v-for="tab in moreTabs"
          :key="tab.key"
          :data-test="`tab-more-${tab.key}`"
          @click="onMoreSelect(tab.key)"
        >
          {{ tab.title }}
        </button>
      </div>
    </div>
    <tab-nav-context-menu
      :visible="context.visible"
      :x="context.x"
      :y="context.y"
      :item="contextItem"
      @action="onAction"
    />
  </div>
</template>

<style scoped>
/* 页签容器不设 overflow（避免裁剪「更多」下拉与右键菜单浮层）；页签按需收缩并省略标题 */
.bms-tab-nav {
  display: flex;
  flex: none;
  align-items: stretch;
  box-sizing: border-box;
  min-width: 0;
  background: var(--bms-color-fill);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-tab-nav__item {
  display: inline-flex;
  flex: 0 1 auto;
  align-items: center;
  min-width: 64px;
  max-width: 180px;
  height: 36px;
  padding: 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  user-select: none;
  background: var(--bms-color-fill);
  border-right: 1px solid var(--bms-color-border);
  border-bottom: 2px solid transparent;
  gap: var(--bms-space-2);
}

.bms-tab-nav__item:hover {
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
}

.bms-tab-nav__item.is-active {
  color: var(--bms-color-primary);
  background: var(--bms-color-bg);
  border-bottom-color: var(--bms-color-primary);
}

.bms-tab-nav__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-tab-nav__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  line-height: 1;
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--bms-radius-sm);
}

.bms-tab-nav__close:hover {
  color: var(--bms-color-white);
  background: var(--bms-color-text-secondary);
}

.bms-tab-nav__more {
  position: relative;
  display: flex;
  flex: none;
  align-items: center;
  margin-left: auto;
  padding: 0 var(--bms-space-2);
  border-left: 1px solid var(--bms-color-border);
}

.bms-tab-nav__more button {
  height: 28px;
  padding: 0 var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--bms-radius-sm);
}

.bms-tab-nav__more button:hover {
  color: var(--bms-color-primary);
  background: var(--bms-color-bg);
}

.bms-tab-nav__more-list {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-width: 160px;
  max-height: 280px;
  padding: var(--bms-space-1);
  overflow-y: auto;
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  box-shadow: var(--bms-shadow-sm);
}

.bms-tab-nav__more-list button {
  width: 100%;
  text-align: left;
}
</style>
