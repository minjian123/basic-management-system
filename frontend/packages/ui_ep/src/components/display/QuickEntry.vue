<script setup lang="ts">
// 快捷入口宫格（07_02）：图标 + 文案 + 跳转，权限过滤、分组、角标与列数自适应。
import { ElTooltip } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'

import { useBaseAccess } from '../../composables/useBaseAccess'
import { observeResize, supportsResize } from '../../utils/observe'
import SkeletonBlock from '../feedback/SkeletonBlock.vue'

/** 快捷入口项。 */
export interface QuickEntryItem {
  /** 唯一标识（菜单/表单 code）。 */
  key: string
  /** 名称。 */
  label: string
  /** icon key（`el:` / `biz:` / `custom:`）。 */
  icon?: string
  /** 目标路由。 */
  route?: string
  /** 角标。 */
  badge?: string | number
  /** 分组。 */
  group?: string
  /** 排序。 */
  order?: number
  /** 权限码（缺省视为公开）。 */
  perm?: string
}

interface Props {
  /** 入口项集合。 */
  entries?: QuickEntryItem[]
  /** 列数（3 / 4 / auto）。 */
  columns?: 3 | 4 | 'auto'
  /** 图标尺寸（px）。 */
  iconSize?: number
  /** 是否显示名称。 */
  showLabel?: boolean
  /** 是否按权限过滤。 */
  filterByPerm?: boolean
  /** 当前权限码（供权限过滤）。 */
  permissions?: string[]
  /** 是否可编辑（工作台编辑态）。 */
  editable?: boolean
  /** 入口配置是否加载中（加载态渲染骨架）。 */
  loading?: boolean
  /** 已注册路由清单（非空时未注册入口拦截跳转并告警）。 */
  routes?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  entries: () => [],
  columns: 'auto',
  iconSize: 22,
  showLabel: true,
  filterByPerm: true,
  permissions: () => [],
  editable: false,
  loading: false,
  routes: () => [],
})

const emit = defineEmits<{
  open: [entry: QuickEntryItem]
  navigate: [entry: QuickEntryItem]
  remove: [entry: QuickEntryItem]
  reorder: [entries: QuickEntryItem[]]
}>()

const access = useBaseAccess(props.permissions)
watch(
  () => props.permissions,
  (codes) => access.setCodes(codes),
)

const iconMap = ref<Record<string, Component>>({})
let iconsLoading: Promise<void> | undefined

function ensureIcons(): void {
  if (iconsLoading) {
    return
  }
  iconsLoading = import('@element-plus/icons-vue')
    .then((mod) => {
      iconMap.value = mod as unknown as Record<string, Component>
    })
    .catch(() => {
      iconsLoading = undefined
    })
}

function iconComponent(key?: string): Component | undefined {
  if (!key) {
    return undefined
  }
  const [prefix, raw] = key.includes(':') ? key.split(':', 2) : ['el', key]
  if (prefix !== 'el' || !raw) {
    return undefined
  }
  const name = raw.charAt(0).toUpperCase() + raw.slice(1)
  return iconMap.value[name]
}

const container = ref<HTMLElement>()
const autoColumns = ref(4)
let offResize: () => void = () => {}

onMounted(() => {
  if (props.entries.some((entry) => entry.icon?.startsWith('el:'))) {
    ensureIcons()
  }
  if (props.columns === 'auto' && supportsResize() && container.value !== undefined) {
    offResize = observeResize(container.value, (entry) => {
      const width = entry.contentRect.width
      autoColumns.value = width >= 320 ? 4 : 3
    })
  }
})
onBeforeUnmount(() => offResize())

const columnCount = computed(() => (props.columns === 'auto' ? autoColumns.value : props.columns))

const visibleEntries = computed<QuickEntryItem[]>(() => {
  const seen = new Set<string>()
  return props.entries
    .filter((entry) => !props.filterByPerm || access.canAccess(entry.perm))
    .filter((entry) => {
      if (seen.has(entry.key)) {
        return false
      }
      seen.add(entry.key)
      return true
    })
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0))
})

const groups = computed(() => {
  const map = new Map<string, QuickEntryItem[]>()
  for (const entry of visibleEntries.value) {
    const key = entry.group ?? ''
    const list = map.get(key)
    if (list) {
      list.push(entry)
    } else {
      map.set(key, [entry])
    }
  }
  return [...map.entries()].map(([group, items]) => ({ group, items }))
})

/**
 * 目标路由是否已注册（`routes` 为空视为不校验）。
 *
 * @param entry 入口项。
 * @returns 是否可跳转。
 */
function routeRegistered(entry: QuickEntryItem): boolean {
  if (props.routes.length === 0 || entry.route === undefined) {
    return true
  }
  return props.routes.includes(entry.route)
}

function onEntry(entry: QuickEntryItem): void {
  emit('open', entry)
  if (!entry.route) {
    return
  }
  if (!routeRegistered(entry)) {
    console.warn(`[QuickEntry] 目标路由未注册，已拦截跳转：${entry.route}`)
    return
  }
  emit('navigate', entry)
}

defineExpose({ visibleEntries })
</script>

<template>
  <div
    ref="container"
    class="bms-quick-entry"
    :data-columns="columnCount"
    :data-editable="editable || undefined"
    data-test="quick-entry"
  >
    <div v-if="loading" class="bms-quick-entry__loading" data-test="loading">
      <skeleton-block variant="card" :rows="2" />
    </div>
    <div v-else-if="visibleEntries.length === 0" class="bms-quick-entry__empty" data-test="empty">
      <slot name="empty">暂无快捷入口</slot>
    </div>
    <div v-for="group in groups" v-else :key="group.group" class="bms-quick-entry__group">
      <div v-if="group.group !== ''" class="bms-quick-entry__group-title" data-test="group-title">
        {{ group.group }}
      </div>
      <div class="bms-quick-entry__grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <el-tooltip v-for="entry in group.items" :key="entry.key" :content="entry.label" :disabled="showLabel">
          <div
            class="bms-quick-entry__item"
            role="button"
            tabindex="0"
            :data-test="`entry-${entry.key}`"
            :aria-label="entry.label"
            @click="onEntry(entry)"
            @keydown.enter.prevent="onEntry(entry)"
            @keydown.space.prevent="onEntry(entry)"
          >
            <span class="bms-quick-entry__icon" :style="{ fontSize: `${iconSize}px` }">
              <slot name="icon" :entry="entry">
                <component :is="iconComponent(entry.icon)" v-if="iconComponent(entry.icon)" />
                <span v-else data-test="icon-fallback">?</span>
              </slot>
            </span>
            <span v-if="showLabel" class="bms-quick-entry__label">{{ entry.label }}</span>
            <span v-if="entry.badge !== undefined" class="bms-quick-entry__badge" data-test="entry-badge">
              {{ entry.badge }}
            </span>
            <span
              v-if="editable"
              class="bms-quick-entry__remove"
              data-test="entry-remove"
              @click.stop="emit('remove', entry)"
            >
              ×
            </span>
          </div>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-quick-entry {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
}

.bms-quick-entry__group {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-quick-entry__group-title {
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
}

.bms-quick-entry__grid {
  display: grid;
  gap: var(--bms-space-3);
}

.bms-quick-entry__item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
  padding: var(--bms-space-2) var(--bms-space-1);
  cursor: pointer;
  border-radius: var(--bms-radius-md);
  transition: background-color 0.15s ease;
}

.bms-quick-entry__item:hover,
.bms-quick-entry__item:focus-visible {
  background: var(--bms-color-fill);
  outline: none;
}

.bms-quick-entry__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  color: var(--bms-color-primary);
  background: var(--bms-color-primary-light);
  border-radius: var(--bms-radius-lg);
}

.bms-quick-entry__label {
  overflow: hidden;
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text);
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.bms-quick-entry__badge {
  position: absolute;
  top: 2px;
  right: 25%;
  padding: 0 var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: 16px;
  color: var(--bms-color-text-inverse);
  background: var(--bms-notice-badge-bg);
  border-radius: var(--bms-radius-lg);
}

.bms-quick-entry__remove {
  position: absolute;
  top: 2px;
  left: 25%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: var(--bms-font-size-xs);
  line-height: 1;
  color: var(--bms-color-text-inverse);
  background: var(--bms-color-text-secondary);
  border-radius: 50%;
}

.bms-quick-entry__empty {
  padding: var(--bms-space-6);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  text-align: center;
}
</style>
