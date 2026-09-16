<script setup lang="ts">
/**
 * 页面级标签栏（多标签导航）：固定首签 / 打开与激活 / 关闭激活相邻 / 右键菜单 / 溢出滚动 /
 * keep-alive 缓存键 / 脏数据关闭确认 / 打开上限。
 *
 * 契约见《组件设计 · 多标签导航》§3 ~ §5：状态核心经**页签状态片段 `useTabs`**
 * （传 `tabs` 即受控、所有变更经 `update:*` 回写；不传即非受控、内部自管并经 `defineExpose` 操作）；
 * 缓存键清单供宿主 `keep-alive :include`（宿主接线归 `03_05`）；关闭确认复用 `useConfirm`（`03_01`）。
 */

import { useI18n } from 'vue-i18n'
import {
  computed,
  getCurrentInstance,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  useAttrs,
  watch,
  type ComponentPublicInstance,
} from 'vue'

import { useComponentBase } from '@/base/useComponentBase'
import { useTabs } from '@/components/base/tabs'

import { confirmDirtyClose } from './confirmClose'
import type { TabNavItem } from './types'

const props = withDefaults(
  defineProps<{
    /** 标签项；传数组即受控，传 null 即非受控（内部自管） */
    tabs?: TabNavItem[] | null
    activeKey?: string | null
    /** 固定标签（工作台，不可关，首位） */
    pinnedKey?: string | null
    /** 最大打开数（非受控打开超限：关闭最久未激活的可关闭标签） */
    maxOpen?: number
    /** 关闭前检查 `dirty`（确认） */
    closableTip?: boolean
    /** 拖拽排序（受控模式下 emit `update:tabs` 新顺序；非受控不支持） */
    draggable?: boolean
    /** 显示刷新图标（emit `refresh`，重挂载由宿主实现） */
    transform?: boolean
  }>(),
  {
    tabs: null,
    activeKey: null,
    pinnedKey: null,
    maxOpen: 12,
    closableTip: true,
    draggable: false,
    transform: false,
  },
)

const emit = defineEmits<{
  select: [key: string]
  close: [key: string]
  'close-others': [key: string]
  'close-right': [key: string]
  'close-all': []
  refresh: [key: string]
  /** 非受控超限自动关闭（key 为被关闭者；宿主可提示） */
  exceed: [key: string]
  'update:activeKey': [key: string]
  'update:tabs': [items: TabNavItem[]]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'tabs-nav' })
const { t } = useI18n()
const attrs = useAttrs()
/** 捕获组件实例（`getCurrentInstance` 仅 setup 期有效，供导航取 router） */
const instance = getCurrentInstance()

/** 受控性在组件生命周期内固定：传 `tabs` 即受控（变更经 `update:*` 回写） */
const controlled = props.tabs !== null

const tabsApi = useTabs({
  ...(controlled ? { tabs: computed(() => props.tabs as TabNavItem[]) } : {}),
  ...(props.activeKey !== null ? { activeKey: computed(() => props.activeKey as string) } : {}),
  onChange: ({ tabs, activeKey }) => {
    if (controlled) {
      emit('update:tabs', tabs as TabNavItem[])
    }
    emit('update:activeKey', activeKey)
  },
})

/** 激活时间记录（上限 LRU 依据） */
const lastActiveAt = ref<Record<string, number>>({})
watch(
  () => tabsApi.activeKey,
  (key) => {
    if (key) {
      lastActiveAt.value[key] = Date.now()
    }
  },
  { immediate: true },
)

function list(): TabNavItem[] {
  return tabsApi.tabs as TabNavItem[]
}

function findTab(key: string): TabNavItem | undefined {
  return tabsApi.find(key) as TabNavItem | undefined
}

function isClosable(tab: TabNavItem): boolean {
  return !tab.pinned && tab.closable !== false
}

/** 打开标签（非受控：上限 LRU；受控：仅 emit `update:*`） */
function openTab(tab: TabNavItem): void {
  if (!controlled && !tabsApi.has(tab.key) && list().length >= props.maxOpen) {
    const victim = list()
      .filter((item) => isClosable(item) && item.key !== props.pinnedKey)
      .sort((a, b) => (lastActiveAt.value[a.key] ?? 0) - (lastActiveAt.value[b.key] ?? 0))[0]
    if (victim) {
      tabsApi.close(victim.key)
      emit('exceed', victim.key)
    }
  }
  tabsApi.open(tab)
  lastActiveAt.value[tab.key] = Date.now()
}

/** 关闭激活相邻：优先右邻，无则左邻，无则空 */
function nextActiveAfterClose(key: string): string {
  const items = list()
  const index = items.findIndex((item) => item.key === key)
  return items[index + 1]?.key ?? items[index - 1]?.key ?? ''
}

function applyTabs(next: TabNavItem[], nextActive?: string): void {
  if (controlled) {
    emit('update:tabs', next)
    if (nextActive !== undefined) {
      emit('update:activeKey', nextActive)
    }
    return
  }
  // 非受控：经片段同步（先关闭被移除项，再对剩余重排——片段无整体写接口，逐项处理）
  for (const item of [...list()]) {
    if (!next.some((entry) => entry.key === item.key)) {
      tabsApi.close(item.key)
    }
  }
  for (const item of next) {
    if (!tabsApi.has(item.key)) {
      tabsApi.open(item)
    }
  }
  if (nextActive !== undefined) {
    tabsApi.activate(nextActive)
  }
}

async function closeTab(key: string): Promise<void> {
  const tab = findTab(key)
  if (!tab || !isClosable(tab)) {
    return
  }
  const allowed = await confirmDirtyClose(tab, props.closableTip)
  if (!allowed) {
    return
  }
  const nextActive = tabsApi.activeKey === key ? nextActiveAfterClose(key) : undefined
  if (controlled) {
    emit('update:tabs', list().filter((item) => item.key !== key))
    if (nextActive !== undefined) {
      emit('update:activeKey', nextActive)
    }
  } else {
    tabsApi.close(key)
    if (nextActive) {
      tabsApi.activate(nextActive)
    }
  }
  emit('close', key)
}

async function closeOthers(key: string): Promise<void> {
  const dirty = list().some((item) => item.key !== key && !item.pinned && item.dirty)
  const allowed = await confirmDirtyClose({ dirty }, props.closableTip)
  if (!allowed) {
    return
  }
  const next = list().filter((item) => item.key === key || item.pinned)
  applyTabs(next, key)
  emit('close-others', key)
}

async function closeRight(key: string): Promise<void> {
  const items = list()
  const index = items.findIndex((item) => item.key === key)
  if (index < 0) {
    return
  }
  const removed = items.slice(index + 1).filter((item) => !item.pinned)
  const allowed = await confirmDirtyClose({ dirty: removed.some((item) => item.dirty) }, props.closableTip)
  if (!allowed) {
    return
  }
  const keep = new Set(removed.map((item) => item.key))
  applyTabs(
    items.filter((item) => !keep.has(item.key)),
    keep.has(tabsApi.activeKey) ? key : undefined,
  )
  emit('close-right', key)
}

async function closeAll(): Promise<void> {
  const removed = list().filter((item) => !item.pinned)
  const allowed = await confirmDirtyClose({ dirty: removed.some((item) => item.dirty) }, props.closableTip)
  if (!allowed) {
    return
  }
  const next = list().filter((item) => item.pinned)
  const nextActive = next.some((item) => item.key === props.pinnedKey) ? (props.pinnedKey as string) : (next[0]?.key ?? '')
  applyTabs(next, nextActive)
  emit('close-all')
}

function onSelect(tab: TabNavItem): void {
  lastActiveAt.value[tab.key] = Date.now()
  if (controlled) {
    emit('update:activeKey', tab.key)
  } else {
    tabsApi.activate(tab.key)
  }
  emit('select', tab.key)
  const router = instance?.appContext.config.globalProperties.$router as
    | { push?: (target: string) => void }
    | undefined
  if (router?.push && tab.path) {
    void router.push(tab.path)
  }
}

/* ===== 右键菜单 ===== */
const menu = ref({ visible: false, x: 0, y: 0, key: '' })

function openMenu(event: MouseEvent, tab: TabNavItem): void {
  menu.value = { visible: true, x: event.clientX, y: event.clientY, key: tab.key }
}

function closeMenu(): void {
  menu.value.visible = false
}

function onDocumentClick(): void {
  if (menu.value.visible) {
    closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

const menuTab = computed(() => findTab(menu.value.key))
const menuCloseDisabled = computed(() => {
  const tab = menuTab.value
  return !tab || !isClosable(tab)
})
const menuCloseRightDisabled = computed(() => {
  const items = list()
  const index = items.findIndex((item) => item.key === menu.value.key)
  return index < 0 || !items.slice(index + 1).some((item) => isClosable(item))
})

function runMenu(action: 'refresh' | 'close' | 'close-others' | 'close-right' | 'close-all'): void {
  const key = menu.value.key
  closeMenu()
  if (action === 'refresh') {
    emit('refresh', key)
    return
  }
  if (action === 'close') {
    void closeTab(key)
    return
  }
  if (action === 'close-others') {
    void closeOthers(key)
    return
  }
  if (action === 'close-right') {
    void closeRight(key)
    return
  }
  void closeAll()
}

/* ===== 溢出滚动 / 拖拽 ===== */
const scrollerRef = ref<HTMLElement | null>(null)
const itemRefs = new Map<string, HTMLElement>()

function setItemRef(key: string, el: Element | ComponentPublicInstance | null): void {
  if (el instanceof HTMLElement) {
    itemRefs.set(key, el)
  } else {
    itemRefs.delete(key)
  }
}

watch(
  () => tabsApi.activeKey,
  async () => {
    await nextTick()
    const el = itemRefs.get(tabsApi.activeKey)
    el?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' })
  },
)

function onWheel(event: WheelEvent): void {
  const el = scrollerRef.value
  if (!el) {
    return
  }
  el.scrollLeft += event.deltaY !== 0 ? event.deltaY : event.deltaX
}

const dragKey = ref<string | null>(null)

function onDragStart(tab: TabNavItem): void {
  if (!props.draggable) {
    return
  }
  dragKey.value = tab.key
}

function onDrop(target: TabNavItem): void {
  const from = dragKey.value
  dragKey.value = null
  if (!from || from === target.key || !controlled) {
    return
  }
  const items = [...list()]
  const fromIndex = items.findIndex((item) => item.key === from)
  const toIndex = items.findIndex((item) => item.key === target.key)
  if (fromIndex < 0 || toIndex < 0) {
    return
  }
  const [moved] = items.splice(fromIndex, 1)
  items.splice(toIndex, 0, moved)
  emit('update:tabs', items)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('tabs-nav'), cls], style: sty, ...rest })
})

defineExpose({
  openTab,
  closeTab,
  closeOthers,
  closeRight,
  closeAll,
  activate: (key: string) => {
    if (controlled) {
      emit('update:activeKey', key)
    } else {
      tabsApi.activate(key)
    }
  },
  get tabs() {
    return list()
  },
  get activeKey() {
    return tabsApi.activeKey
  },
  get cachedNames() {
    return tabsApi.cachedNames
  },
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('tabs-nav')">
    <div ref="scrollerRef" :class="base.nsClass('tabs-nav-scroller')" @wheel="onWheel">
      <div
        v-for="tab in tabsApi.tabs"
        :key="tab.key"
        :ref="(el) => setItemRef(tab.key, el)"
        :class="[
          base.nsClass('tabs-nav-item'),
          tab.key === tabsApi.activeKey && 'is-active',
          tab.pinned && 'is-pinned',
        ]"
        :draggable="draggable"
        @click="onSelect(tab as TabNavItem)"
        @contextmenu.prevent="openMenu($event, tab as TabNavItem)"
        @dragstart="onDragStart(tab as TabNavItem)"
        @dragover.prevent
        @drop="onDrop(tab as TabNavItem)"
      >
        <span v-if="(tab as TabNavItem).icon" :class="base.nsClass('tabs-nav-icon')">
          {{ (tab as TabNavItem).icon }}
        </span>
        <span :class="base.nsClass('tabs-nav-title')">{{ tab.title }}</span>
        <span v-if="(tab as TabNavItem).badge" :class="base.nsClass('tabs-nav-badge')">
          {{ (tab as TabNavItem).badge }}
        </span>
        <span
          v-if="transform && tab.key === tabsApi.activeKey"
          :class="base.nsClass('tabs-nav-refresh')"
          :title="t('tabs.refresh')"
          @click.stop="emit('refresh', tab.key)"
        >
          ⟳
        </span>
        <span
          v-if="!tab.pinned && tab.closable !== false"
          :class="base.nsClass('tabs-nav-close')"
          :title="t('tabs.closeCurrent')"
          @click.stop="closeTab(tab.key)"
        >
          ×
        </span>
      </div>
    </div>

    <div
      v-if="menu.visible"
      :class="base.nsClass('tabs-nav-menu')"
      :style="{ left: `${menu.x}px`, top: `${menu.y}px` }"
    >
      <button type="button" :class="base.nsClass('tabs-nav-menu-item')" @click="runMenu('refresh')">
        {{ t('tabs.refresh') }}
      </button>
      <button
        type="button"
        :class="base.nsClass('tabs-nav-menu-item')"
        :disabled="menuCloseDisabled"
        @click="runMenu('close')"
      >
        {{ t('tabs.closeCurrent') }}
      </button>
      <button
        type="button"
        :class="base.nsClass('tabs-nav-menu-item')"
        :disabled="menuCloseDisabled"
        @click="runMenu('close-others')"
      >
        {{ t('tabs.closeOthers') }}
      </button>
      <button
        type="button"
        :class="base.nsClass('tabs-nav-menu-item')"
        :disabled="menuCloseRightDisabled"
        @click="runMenu('close-right')"
      >
        {{ t('tabs.closeRight') }}
      </button>
      <button type="button" :class="base.nsClass('tabs-nav-menu-item')" @click="runMenu('close-all')">
        {{ t('tabs.closeAll') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.bms-tabs-nav {
  position: relative;
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
}

.bms-tabs-nav-scroller {
  display: flex;
  align-items: center;
  gap: var(--bms-space-1);
  padding: var(--bms-space-1) var(--bms-space-2);
  overflow-x: auto;
  scrollbar-width: none;
}

.bms-tabs-nav-scroller::-webkit-scrollbar {
  display: none;
}

.bms-tabs-nav-item {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-1);
  padding: var(--bms-space-1) 10px;
  border: 1px solid transparent;
  border-radius: var(--bms-radius-sm);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
}

.bms-tabs-nav-item:hover {
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.bms-tabs-nav-item.is-active {
  color: var(--bms-color-primary);
  border-color: var(--bms-color-border);
  background: var(--bms-color-bg);
}

.bms-tabs-nav-badge {
  padding: 0 6px;
  border-radius: 8px;
  background: var(--bms-color-danger);
  color: var(--bms-color-text-inverse);
  font-size: var(--bms-font-size-xs);
  line-height: 16px;
}

.bms-tabs-nav-close,
.bms-tabs-nav-refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--bms-size-icon-default);
  height: var(--bms-size-icon-default);
  border-radius: 50%;
  font-size: var(--bms-font-size-sm);
  line-height: 1;
}

.bms-tabs-nav-close:hover,
.bms-tabs-nav-refresh:hover {
  background: var(--bms-color-border);
  color: var(--bms-color-text);
}

.bms-tabs-nav-menu {
  position: fixed;
  z-index: 2200;
  display: flex;
  flex-direction: column;
  min-width: 132px;
  padding: var(--bms-space-1);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-bg);
  box-shadow: var(--bms-shadow-md);
}

.bms-tabs-nav-menu-item {
  padding: 6px 10px;
  border: 0;
  border-radius: var(--bms-radius-sm);
  background: transparent;
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  text-align: left;
  cursor: pointer;
}

.bms-tabs-nav-menu-item:hover:not(:disabled) {
  background: var(--bms-color-bg-page);
}

.bms-tabs-nav-menu-item:disabled {
  color: var(--bms-color-text-secondary);
  cursor: not-allowed;
}
</style>
