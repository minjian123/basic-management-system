<script setup lang="ts">
// 描述列表（07_05）：响应式列数与跨列 / 描述项各类型只读回显 / 长文本折叠 / 空值占位 / 脱敏切换。
import {
  EMPTY_PLACEHOLDER,
  FILTER_WIDGET_BY_TYPE,
  FieldRendererRegistry,
  formatAmount,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  mask,
  type StatusSemantic,
} from '@bms/core'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'

import StatusTag from './StatusTag.vue'

/** 描述项类型。 */
export type DescItemType =
  | 'text'
  | 'longtext'
  | 'number'
  | 'amount'
  | 'percent'
  | 'date'
  | 'datetime'
  | 'dict'
  | 'enum'
  | 'switch'
  | 'status'
  | 'dept'
  | 'file'
  | 'rich'
  | 'custom'

/** 描述项配置。 */
export interface DescItem {
  /** 字段名。 */
  key: string
  /** 字段文案。 */
  label: string
  /** 字段类型（决定值渲染器；缺省按原值文本）。 */
  type?: DescItemType
  /** 字典类型（配合注入的翻译处理函数）。 */
  dictType?: string
  /** 枚举选项。 */
  options?: { label: string; value: unknown }[]
  /** 状态色映射（`值 → 语义色`）。 */
  statusMap?: Record<string, StatusSemantic>
  /** 数值精度。 */
  precision?: number
  /** 是否脱敏。 */
  mask?: boolean
  /** 指定列跨度（1..列数）。 */
  span?: number
  /** 是否跨整行。 */
  crossColumn?: boolean
  /** 是否折叠长文本。 */
  collapse?: boolean
  /** 自定义空值占位。 */
  emptyText?: string
}

/** 分组配置。 */
export interface DescGroup {
  /** 分组标题。 */
  title: string
  /** 分组内字段名。 */
  keys: string[]
}

/** 长文本折叠阈值（字符数）。 */
const DESC_COLLAPSE_LENGTH = 120

interface Props {
  /** 描述项配置。 */
  items?: DescItem[]
  /** 数据源（单条记录）。 */
  data?: Record<string, unknown>
  /** 列数（`auto` 按断点 1536 / 1024 解析）。 */
  columns?: 1 | 2 | 3 | 'auto'
  /** 是否带边框。 */
  border?: boolean
  /** 密度。 */
  density?: 'default' | 'small'
  /** label 位置。 */
  labelPlacement?: 'left' | 'top'
  /** 标题。 */
  title?: string
  /** 分组（未列入分组的项归入首组之后）。 */
  groups?: DescGroup[]
  /** 全部纯文本（不使用状态标签）。 */
  plainText?: boolean
  /** 空值占位。 */
  emptyText?: string
  /** 脱敏字段集（覆盖描述项 `mask`）。 */
  masked?: string[]
  /** 是否具备查看明文权限。 */
  plainEnabled?: boolean
  /** 视口宽度（大于 0 时覆盖自动探测，便于测试与固定容器场景）。 */
  viewportWidth?: number
  /** 字段渲染器注册表（宿主注入；未登记类型回落内置轻量渲染）。 */
  renderers?: FieldRendererRegistry
  /** 字典 label 翻译（宿主注入；未注入即显示原值，不发请求）。 */
  translator?: (dictType: string, value: unknown) => string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  data: () => ({}),
  columns: 'auto',
  border: true,
  density: 'default',
  labelPlacement: 'left',
  title: '',
  groups: () => [],
  plainText: false,
  emptyText: EMPTY_PLACEHOLDER,
  masked: () => [],
  plainEnabled: false,
  viewportWidth: 0,
  renderers: undefined,
  translator: undefined,
})

const emit = defineEmits<{
  'plain-toggle': [key: string, plain: boolean]
  'item-click': [key: string, value: unknown]
  'collapse-toggle': [key: string, collapsed: boolean]
}>()

const base = useBaseDisplay<Record<string, unknown>>()
const collapsed = ref<string[]>([])

watch(
  () => props.data,
  (next) => base.setValue(next),
  { immediate: true },
)

/** 数据源（经展示件投影的值语义面）。 */
const dataSource = computed<Record<string, unknown>>(() => base.value.value ?? {})
const revealed = ref<string[]>([])
const detectedWidth = ref(0)

/** 监听视口宽度（`auto` 列数用）。 */
function onResize(): void {
  const scope = globalThis as { innerWidth?: number }
  detectedWidth.value = scope.innerWidth ?? 0
}

onMounted(() => {
  onResize()
  globalThis.addEventListener?.('resize', onResize)
})

onBeforeUnmount(() => {
  globalThis.removeEventListener?.('resize', onResize)
})

/** 生效视口宽度。 */
const width = computed(() => (props.viewportWidth > 0 ? props.viewportWidth : detectedWidth.value))

/** 生效列数（`auto` 按断点解析）。 */
const columns = computed<number>(() => {
  if (props.columns !== 'auto') {
    return props.columns
  }
  if (width.value >= 1536) {
    return 3
  }
  return width.value >= 1024 ? 2 : 1
})

/** 分组后的描述项（未分组项归入 `__ungrouped`）。 */
const sections = computed<{ title: string; items: DescItem[] }[]>(() => {
  if (props.groups.length === 0) {
    return [{ title: '', items: props.items }]
  }
  const grouped = new Set<string>()
  const result = props.groups.map((group) => {
    const items = props.items.filter((item) => group.keys.includes(item.key))
    for (const item of items) {
      grouped.add(item.key)
    }
    return { title: group.title, items }
  })
  const rest = props.items.filter((item) => !grouped.has(item.key))
  if (rest.length > 0) {
    result.push({ title: '', items: rest })
  }
  return result.filter((section) => section.items.length > 0)
})

/** 原始值。 */
function rawValue(item: DescItem): unknown {
  return dataSource.value[item.key]
}

/** 是否空值（空串 / null / undefined / 空数组）。 */
function isBlank(value: unknown): boolean {
  if (value === null || value === undefined || value === '') {
    return true
  }
  return Array.isArray(value) && value.length === 0
}

/** 是否脱敏。 */
function isMasked(item: DescItem): boolean {
  return props.masked.includes(item.key) || item.mask === true
}

/** 是否已展开明文。 */
function isRevealed(item: DescItem): boolean {
  return revealed.value.includes(item.key)
}

/** 是否已折叠。 */
function isCollapsed(item: DescItem): boolean {
  return collapsed.value.includes(item.key)
}

/** 是否展示折叠入口（长文本超阈值）。 */
function collapsible(item: DescItem): boolean {
  const value = rawValue(item)
  return item.collapse === true && typeof value === 'string' && value.length > DESC_COLLAPSE_LENGTH
}

/** 富文本摘要（去标签取前 120 字符）。 */
function richSummary(value: string): string {
  return value.replace(/<[^>]*>/gu, '').slice(0, DESC_COLLAPSE_LENGTH)
}

/** 选项翻译。 */
function optionLabel(item: DescItem, value: unknown): string | undefined {
  return item.options?.find((option) => String(option.value) === String(value))?.label
}

/** 值文本（各类型只读回显）。 */
function valueText(item: DescItem): string {
  const value = rawValue(item)
  if (isBlank(value)) {
    return item.emptyText ?? props.emptyText
  }
  if (isMasked(item) && !isRevealed(item)) {
    return mask(String(value))
  }
  if (Array.isArray(value) && item.type !== 'file') {
    return value.map((entry) => singleText(item, entry)).join('、')
  }
  return singleText(item, value)
}

/** 单值文本。 */
function singleText(item: DescItem, value: unknown): string {
  switch (item.type) {
    case 'number':
      return formatNumber(Number(value))
    case 'amount':
      return formatAmount(Number(value), { precision: item.precision })
    case 'percent':
      return formatPercent(Number(value), { precision: item.precision })
    case 'date':
      return formatDate(String(value))
    case 'datetime':
      return formatDateTime(String(value))
    case 'switch':
      return value === true || value === 1 || value === '1' ? '是' : '否'
    case 'file':
      return `${Array.isArray(value) ? (value as unknown[]).length : 1} 个文件`
    case 'rich':
      return richSummary(String(value))
    case 'dict':
      return (
        (item.dictType !== undefined ? props.translator?.(item.dictType, value) : undefined) ??
        optionLabel(item, value) ??
        String(value)
      )
    case 'enum':
      return optionLabel(item, value) ?? String(value)
    default:
      return String(value)
  }
}

/** 注册表渲染器（未登记返回 `undefined`，回落内置轻量渲染）。 */
function registeredRenderer(item: DescItem): unknown {
  if (item.type === undefined || props.renderers === undefined) {
    return undefined
  }
  const widget = FILTER_WIDGET_BY_TYPE[item.type as keyof typeof FILTER_WIDGET_BY_TYPE] ?? item.type
  return props.renderers.resolveByType(widget)?.component
}

/** 值是否为状态类（走状态标签）。 */
function isStatusItem(item: DescItem): boolean {
  return !props.plainText && item.type === 'status'
}

/** 描述项栅格跨度。 */
function itemSpan(item: DescItem): number {
  if (item.crossColumn === true) {
    return columns.value
  }
  if (item.span !== undefined) {
    return Math.min(columns.value, Math.max(1, item.span))
  }
  if (item.type === 'longtext' || item.type === 'rich' || item.type === 'file') {
    return columns.value
  }
  return 1
}

/** 描述项行内样式。 */
function itemStyle(item: DescItem): Record<string, string> {
  return { gridColumn: `span ${itemSpan(item)}` }
}

/**
 * 切换长文本折叠。
 *
 * @param item 描述项。
 */
function toggleCollapse(item: DescItem): void {
  const next = isCollapsed(item) ? collapsed.value.filter((key) => key !== item.key) : [...collapsed.value, item.key]
  collapsed.value = next
  emit('collapse-toggle', item.key, next.includes(item.key))
}

/**
 * 切换脱敏明文。
 *
 * @param item 描述项。
 */
function togglePlain(item: DescItem): void {
  const next = isRevealed(item) ? revealed.value.filter((key) => key !== item.key) : [...revealed.value, item.key]
  revealed.value = next
  emit('plain-toggle', item.key, next.includes(item.key))
}

/**
 * 点击描述项。
 *
 * @param item 描述项。
 */
function onClickItem(item: DescItem): void {
  emit('item-click', item.key, rawValue(item))
}
</script>

<template>
  <div
    class="bms-description-list"
    :class="[
      `bms-description-list--${labelPlacement}`,
      density === 'small' ? 'is-small' : '',
      border ? 'is-border' : '',
    ]"
    data-test="description-list"
    :data-columns="columns"
    :data-density="density"
  >
    <div v-if="title !== ''" class="bms-description-list__title">
      <slot name="title">{{ title }}</slot>
    </div>
    <div
      v-for="(section, sectionIndex) in sections"
      :key="sectionIndex"
      class="bms-description-list__section"
      :data-test="`desc-group-${sectionIndex}`"
    >
      <div v-if="section.title !== ''" class="bms-description-list__group-title">{{ section.title }}</div>
      <div class="bms-description-list__grid" :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }">
        <div
          v-for="item in section.items"
          :key="item.key"
          class="bms-description-list__item"
          :data-test="`desc-item-${item.key}`"
          :style="itemStyle(item)"
          @click="onClickItem(item)"
        >
          <span class="bms-description-list__label" :data-test="`desc-label-${item.key}`">
            <slot :name="`label-${item.key}`" :item="item">{{ item.label }}</slot>
          </span>
          <span class="bms-description-list__value" :data-test="`desc-value-${item.key}`">
            <slot :name="`item-${item.key}`" :item="item" :value="rawValue(item)">
              <template v-if="isBlank(rawValue(item))">
                <span class="bms-description-list__empty" :data-test="`desc-empty-${item.key}`">
                  {{ item.emptyText ?? emptyText }}
                </span>
              </template>
              <template v-else-if="isStatusItem(item)">
                <StatusTag :value="String(rawValue(item))" :color-map="item.statusMap" size="small" />
              </template>
              <template v-else>
                <component
                  :is="registeredRenderer(item)"
                  v-if="registeredRenderer(item) !== undefined"
                  :value="rawValue(item)"
                  :field-key="item.key"
                />
                <template v-else>
                  <span :class="isCollapsed(item) && collapsible(item) ? 'is-collapsed' : ''">{{
                    valueText(item)
                  }}</span>
                  <button
                    v-if="collapsible(item)"
                    type="button"
                    class="bms-description-list__toggle"
                    :data-test="`desc-collapse-${item.key}`"
                    @click.stop="toggleCollapse(item)"
                  >
                    {{ isCollapsed(item) ? '展开' : '收起' }}
                  </button>
                </template>
                <button
                  v-if="isMasked(item) && plainEnabled"
                  type="button"
                  class="bms-description-list__toggle"
                  :data-test="`desc-plain-${item.key}`"
                  @click.stop="togglePlain(item)"
                >
                  {{ isRevealed(item) ? '隐藏' : '查看明文' }}
                </button>
              </template>
            </slot>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-description-list {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size);
}

.bms-description-list__grid {
  display: grid;
  gap: var(--bms-spacing-md) var(--bms-spacing-lg);
}

.bms-description-list__item {
  display: flex;
  gap: var(--bms-spacing-md);
  min-width: 0;
}

.bms-description-list--top .bms-description-list__item {
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}

.bms-description-list.is-border .bms-description-list__grid {
  padding: var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-description-list__label {
  flex: 0 0 auto;
  color: var(--bms-color-text-secondary);
}

.bms-description-list__value {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  min-width: 0;
  word-break: break-word;
}

.bms-description-list__value .is-collapsed {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.bms-description-list__empty {
  color: var(--bms-color-text-secondary);
}

.bms-description-list__toggle {
  color: var(--bms-color-primary);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}

.bms-description-list__title,
.bms-description-list__group-title {
  font-weight: 600;
}

.bms-description-list__group-title {
  margin-bottom: var(--bms-spacing-sm);
}
</style>
