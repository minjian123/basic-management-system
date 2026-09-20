<script setup lang="ts">
// 快捷入口宫格（07_02）：图标 + 文案 + 跳转，权限过滤、分组、角标与列数自适应。
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'

import { useBaseAccess } from '../../composables/useBaseAccess'
import { observeResize, supportsResize } from '../../utils/observe'

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
}

const props = withDefaults(defineProps<Props>(), {
  entries: () => [],
  columns: 'auto',
  iconSize: 22,
  showLabel: true,
  filterByPerm: true,
  permissions: () => [],
  editable: false,
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

function onEntry(entry: QuickEntryItem): void {
  emit('open', entry)
  if (entry.route) {
    emit('navigate', entry)
  }
}
</script>

<template>
  <div
    ref="container"
    class="bms-quick-entry"
    :data-columns="columnCount"
    :data-editable="editable || undefined"
  >
    <div v-if="visibleEntries.length === 0" class="bms-quick-entry__empty" data-test="empty">
      <slot name="empty">暂无快捷入口</slot>
    </div>
    <div v-for="group in groups" :key="group.group" class="bms-quick-entry__group">
      <div v-if="group.group !== ''" class="bms-quick-entry__group-title" data-test="group-title">
        {{ group.group }}
      </div>
      <div class="bms-quick-entry__grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <button
          v-for="entry in group.items"
          :key="entry.key"
          type="button"
          class="bms-quick-entry__item"
          :data-test="`entry-${entry.key}`"
          @click="onEntry(entry)"
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
        </button>
      </div>
    </div>
  </div>
</template>
