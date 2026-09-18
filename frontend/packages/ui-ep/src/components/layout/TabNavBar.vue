<script setup lang="ts">
// 页签导航条：页签列表 + 关闭按钮 + 超出折叠 + 右键菜单。
import { computed, ref } from 'vue'

import type { TabNavItem } from '../../composables/useTabNav'
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
  <div class="bms-tab-nav" data-test="tab-nav">
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
