<script setup lang="ts">
// 查询筛选区（07_05）：条件模型与按类型分发的条件渲染 / 折叠与窄屏 / 查询·重置·条件摘要 / 查询方案。
import {
  FILTER_WIDGET_BY_TYPE,
  FieldRendererRegistry,
  QUERY_COLLAPSE_THRESHOLD,
  QUERY_MAX_PER_ROW,
  QUERY_NARROW_BREAKPOINT,
  QUERY_SCHEME_SCOPE_LABELS,
  buildQueryParams,
  defaultOperatorOf,
  filterActiveConditions,
  summarizeConditions,
  toConditionValue,
  validateConditionRange,
  type ConditionSummary,
  type FilterCondition,
  type FilterField,
  type QuerySchemeEntry,
} from '@bms/core'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseQueryScheme } from '../../composables/useBaseQueryScheme'
import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 查询事件载荷。 */
export interface QueryFilterSearchPayload {
  /** 生效条件。 */
  conditions: FilterCondition[]
  /** 关键字。 */
  keyword: string
  /** 序列化后的查询参数。 */
  params: Record<string, unknown>
}

interface Props {
  /** 数据通路是否就绪（缺省 false，占位零请求）。 */
  ready?: boolean
  /** 查询类字段声明。 */
  fields?: FilterField[]
  /** 条件模型（`v-model:conditions`）。 */
  conditions?: FilterCondition[]
  /** 关键字（`v-model:keyword`）。 */
  keyword?: string
  /** 是否折叠（受控；未传时按条件数自动判定）。 */
  collapsed?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 宽屏一行条件数。 */
  maxPerRow?: number
  /** 折叠阈值（条件数 ≤ 阈值不折叠）。 */
  collapseThreshold?: number
  /** 是否展示查询方案入口。 */
  showScheme?: boolean
  /** 可用查询方案。 */
  schemes?: QuerySchemeEntry[]
  /** 当前应用方案名。 */
  activeScheme?: string
  /** 是否展示高级查询入口（字典类条件）。 */
  showAdvanced?: boolean
  /** 失效条件提示。 */
  invalidHint?: boolean
  /** 窄屏断点。 */
  narrowBreakpoint?: number
  /** 视口宽度（大于 0 时覆盖自动探测）。 */
  viewportWidth?: number
  /** 降级文案。 */
  degradeText?: string
  /** 字段渲染器注册表（宿主注入；未登记类型回落具名插槽与内置轻量控件）。 */
  renderers?: FieldRendererRegistry
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  fields: () => [],
  conditions: () => [],
  keyword: '',
  collapsed: undefined,
  loading: false,
  maxPerRow: QUERY_MAX_PER_ROW,
  collapseThreshold: QUERY_COLLAPSE_THRESHOLD,
  showScheme: false,
  schemes: () => [],
  activeScheme: '',
  showAdvanced: true,
  invalidHint: false,
  narrowBreakpoint: QUERY_NARROW_BREAKPOINT,
  viewportWidth: 0,
  degradeText: '查询条件未就绪（占位）',
  renderers: undefined,
})

const emit = defineEmits<{
  'update:conditions': [conditions: FilterCondition[]]
  'update:keyword': [keyword: string]
  'update:collapsed': [collapsed: boolean]
  search: [payload: QueryFilterSearchPayload]
  reset: [payload: QueryFilterSearchPayload]
  'scheme-change': [name: string]
  'save-scheme': [name: string]
  'save-as-scheme': [name: string]
  'set-default-scheme': [name: string]
  'rename-scheme': [oldName: string, newName: string]
  'delete-scheme': [name: string]
  advanced: [field: FilterField]
  invalid: [message: string]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })
const scheme = useBaseQueryScheme({ fields: props.fields })

const detectedWidth = ref(0)
const collapsedState = ref<boolean | undefined>(undefined)
const schemePanelOpen = ref(false)

/** 监听视口宽度（窄屏口径）。 */
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

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

watch(
  () => props.conditions,
  (next) => scheme.setConditions(next),
  { immediate: true, deep: true },
)

watch(
  () => props.keyword,
  (next) => scheme.setKeyword(next),
)

watch(
  () => props.schemes,
  (next) => scheme.setSchemes(next),
  { immediate: true, deep: true },
)

/** 生效视口宽度。 */
const width = computed(() => (props.viewportWidth > 0 ? props.viewportWidth : detectedWidth.value))

/** 是否窄屏（仅保留关键字 + 查询 / 重置）。 */
const narrow = computed(() => width.value > 0 && width.value < props.narrowBreakpoint)

/** 查询类字段（`query !== false`）。 */
const queryFields = computed(() => props.fields.filter((field) => field.query !== false))

/** 是否自动折叠。 */
const autoCollapsed = computed(() => queryFields.value.length > props.collapseThreshold)

/** 生效折叠态（受控优先，其次用户操作，最后按阈值自动判定）。 */
const isCollapsed = computed(() => props.collapsed ?? collapsedState.value ?? autoCollapsed.value)

/** 折叠时保留的字段数（首行）。 */
const foldLimit = computed(() => (isCollapsed.value ? props.maxPerRow : queryFields.value.length))

/** 是否存在被折叠隐藏的条件。 */
const foldable = computed(() => !narrow.value && queryFields.value.length > props.maxPerRow)

/** 生效条件（参与摘要与请求）。 */
const activeConditions = computed(() => filterActiveConditions(scheme.conditions.value))

/** 条件摘要。 */
const summaries = computed<ConditionSummary[]>(() => summarizeConditions(scheme.conditions.value, props.fields))

/**
 * 取字段当前条件（缺省按类型补操作符）。
 *
 * @param field 字段声明。
 * @returns 条件。
 */
function conditionOf(field: FilterField): FilterCondition {
  return (
    scheme.conditions.value.find((condition) => condition.field === field.key) ?? {
      field: field.key,
      operator: defaultOperatorOf(field.type),
      value: undefined,
    }
  )
}

/**
 * 取字段文本值（区间取首个端点）。
 *
 * @param field 字段声明。
 * @returns 文本值。
 */
function textValueOf(field: FilterField): string {
  const value = conditionOf(field).value
  if (Array.isArray(value)) {
    const first = value[0]
    return first === undefined || first === null ? '' : String(first)
  }
  if (value === undefined || value === null) {
    return ''
  }
  return String(value)
}

/**
 * 取字段多值。
 *
 * @param field 字段声明。
 * @returns 多值清单。
 */
function listValueOf(field: FilterField): string[] {
  const value = conditionOf(field).value
  if (Array.isArray(value)) {
    return value.map((item) => String(item))
  }
  return value === undefined || value === null || value === '' ? [] : [String(value)]
}

/**
 * 区间端点值。
 *
 * @param field 字段声明。
 * @param index 端点序号（0 起 / 1 止）。
 * @returns 端点文本。
 */
function rangeValueOf(field: FilterField, index: number): string {
  const value = conditionOf(field).value
  if (!Array.isArray(value)) {
    return ''
  }
  const entry = value[index]
  return entry === undefined || entry === null ? '' : String(entry)
}

/**
 * 写入字段条件（无则追加）。
 *
 * @param field 字段声明。
 * @param next 新值。
 */
function setValue(field: FilterField, next: unknown): void {
  const updated = toConditionValue(conditionOf(field), next)
  const rest = scheme.conditions.value.filter((condition) => condition.field !== field.key)
  const conditions = [...rest, updated]
  scheme.setConditions(conditions)
  emit(
    'update:conditions',
    conditions.map((condition) => ({ ...condition })),
  )
}

/**
 * 写入区间端点。
 *
 * @param field 字段声明。
 * @param index 端点序号。
 * @param next 端点值。
 */
function setRange(field: FilterField, index: number, next: string): void {
  const start = rangeValueOf(field, 0)
  const end = rangeValueOf(field, 1)
  setValue(field, index === 0 ? [next, end] : [start, next])
}

/**
 * 控件类型（按操作符与字段类型分发）。
 *
 * @param field 字段声明。
 * @returns 控件语义。
 */
function widgetOf(field: FilterField): string {
  const operator = conditionOf(field).operator
  if (operator === 'between') {
    return field.type === 'date' || field.type === 'datetime' ? 'date-range' : 'number-range'
  }
  if (operator === 'in') {
    return 'multi-select'
  }
  return FILTER_WIDGET_BY_TYPE[field.type] ?? 'text'
}

/**
 * 注册表渲染器（未登记返回 `undefined`，回落具名插槽与内置控件）。
 *
 * @param field 字段声明。
 * @returns 渲染器组件。
 */
function registeredRenderer(field: FilterField): unknown {
  if (props.renderers === undefined) {
    return undefined
  }
  return props.renderers.resolveByType(FILTER_WIDGET_BY_TYPE[field.type] ?? field.type)?.component
}

/**
 * 是否字典类条件（挂高级查询入口）。
 *
 * @param field 字段声明。
 * @returns 是否展示入口。
 */
function hasAdvanced(field: FilterField): boolean {
  return props.showAdvanced && (field.type === 'select' || field.type === 'multi_select')
}

/**
 * 是否展示某字段（折叠与窄屏口径）。
 *
 * @param field 字段声明。
 * @returns 是否可见。
 */
function isVisible(field: FilterField): boolean {
  return !narrow.value && queryFields.value.slice(0, foldLimit.value).some((item) => item.key === field.key)
}

/** 切换折叠（受控时仅上抛，不本地改写）。 */
function toggleCollapse(): void {
  const next = !isCollapsed.value
  if (props.collapsed === undefined) {
    collapsedState.value = next
  }
  emit('update:collapsed', next)
}

/**
 * 组装查询载荷（条件非法时返回 `undefined` 并上抛 `invalid`）。
 *
 * @returns 载荷。
 */
function payload(): QueryFilterSearchPayload | undefined {
  for (const condition of activeConditions.value) {
    const field = props.fields.find((item) => item.key === condition.field)
    const message = validateConditionRange(condition, field)
    if (message !== undefined) {
      emit('invalid', message)
      return undefined
    }
  }
  return {
    conditions: activeConditions.value.map((condition) => ({ ...condition })),
    keyword: scheme.keyword.value,
    params: buildQueryParams(scheme.conditions.value, scheme.keyword.value),
  }
}

/** 执行查询（收集条件 → 序列化 → 上抛）。 */
function onSearch(): void {
  const result = payload()
  if (result !== undefined) {
    emit('search', result)
  }
}

/** 重置条件（回字段默认值并立即重查）。 */
function onReset(): void {
  const defaults = props.fields
    .filter((field) => field.defaultValue !== undefined)
    .map((field) => ({ field: field.key, operator: defaultOperatorOf(field.type), value: field.defaultValue }))
  scheme.setConditions(defaults)
  scheme.setKeyword('')
  emit(
    'update:conditions',
    defaults.map((condition) => ({ ...condition })),
  )
  emit('update:keyword', '')
  emit('reset', payload() ?? { conditions: [], keyword: '', params: {} })
}

/**
 * 移除单个条件并立即重查。
 *
 * @param field 条件字段名。
 */
function removeCondition(field: string): void {
  const conditions = scheme.conditions.value.filter((condition) => condition.field !== field)
  scheme.setConditions(conditions)
  emit(
    'update:conditions',
    conditions.map((condition) => ({ ...condition })),
  )
  emit('search', payload() ?? { conditions: [], keyword: '', params: {} })
}

/** 清空全部条件（等价重置）。 */
function clearAll(): void {
  onReset()
}

/**
 * 关键字输入。
 *
 * @param event 输入事件。
 */
function onKeywordInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  scheme.setKeyword(value)
  emit('update:keyword', value)
}

/**
 * 文本 / 数值输入。
 *
 * @param event 输入事件。
 * @param field 字段声明。
 */
function onTextInput(event: Event, field: FilterField): void {
  setValue(field, (event.target as HTMLInputElement).value)
}

/**
 * 区间端点输入。
 *
 * @param event 输入事件。
 * @param field 字段声明。
 * @param index 端点序号。
 */
function onRangeInput(event: Event, field: FilterField, index: number): void {
  setRange(field, index, (event.target as HTMLInputElement).value)
}

/**
 * 单选下拉变更。
 *
 * @param event 变更事件。
 * @param field 字段声明。
 */
function onSelectChange(event: Event, field: FilterField): void {
  setValue(field, (event.target as HTMLSelectElement).value)
}

/**
 * 多选下拉变更。
 *
 * @param event 变更事件。
 * @param field 字段声明。
 */
function onMultiChange(event: Event, field: FilterField): void {
  const options = Array.from((event.target as HTMLSelectElement).selectedOptions).map((option) => option.value)
  setValue(field, options)
}

/**
 * 回车触发查询（文本类条件）。
 *
 * @param event 键盘事件。
 */
function onEnter(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    onSearch()
  }
}

/**
 * 应用查询方案。
 *
 * @param name 方案名。
 */
function applyScheme(name: string): void {
  const conditions = scheme.applyScheme(name)
  schemePanelOpen.value = false
  if (conditions !== undefined) {
    emit(
      'update:conditions',
      conditions.map((condition) => ({ ...condition })),
    )
    emit('scheme-change', name)
  }
}

/**
 * 保存当前条件为方案。
 *
 * @param name 方案名。
 */
function saveScheme(name: string): void {
  scheme.saveScheme(name)
  emit('save-scheme', name)
}

/**
 * 另存为方案。
 *
 * @param name 方案名。
 */
function saveAsScheme(name: string): void {
  scheme.saveScheme(name)
  emit('save-as-scheme', name)
}

/**
 * 设为默认方案。
 *
 * @param name 方案名。
 */
function setDefaultScheme(name: string): void {
  scheme.setDefaultScheme(name)
  emit('set-default-scheme', name)
}

/**
 * 删除方案。
 *
 * @param name 方案名。
 */
function deleteScheme(name: string): void {
  scheme.removeScheme(name)
  emit('delete-scheme', name)
}

/**
 * 打开高级查询（字典类条件）。
 *
 * @param field 字段声明。
 */
function openAdvanced(field: FilterField): void {
  emit('advanced', field)
}
</script>

<template>
  <div
    class="bms-query-filter"
    data-test="query-filter"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-collapsed="isCollapsed"
    :data-narrow="narrow"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-query-filter__placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-query-filter__grid" :style="{ gridTemplateColumns: `repeat(${maxPerRow}, minmax(0, 1fr))` }">
        <div class="bms-query-filter__field" data-test="field-keyword">
          <label class="bms-query-filter__label" for="bms-query-keyword">关键字</label>
          <input
            id="bms-query-keyword"
            class="bms-query-filter__control"
            data-test="keyword"
            :value="scheme.keyword.value"
            @input="onKeywordInput"
            @keydown="onEnter"
          />
        </div>
        <div
          v-for="field in queryFields"
          v-show="isVisible(field)"
          :key="field.key"
          class="bms-query-filter__field"
          :data-test="`field-${field.key}`"
        >
          <label class="bms-query-filter__label">{{ field.label }}</label>
          <div class="bms-query-filter__control-wrap">
            <slot :name="`field-${field.key}`" :field="field" :condition="conditionOf(field)" :set-value="setValue">
              <component
                :is="registeredRenderer(field)"
                v-if="registeredRenderer(field) !== undefined"
                :value="conditionOf(field).value"
                :field-key="field.key"
                @update:value="setValue(field, $event)"
              />
              <template v-else-if="widgetOf(field) === 'number-range' || widgetOf(field) === 'date-range'">
                <input
                  class="bms-query-filter__control"
                  :data-test="`input-${field.key}`"
                  :placeholder="field.placeholder"
                  :value="rangeValueOf(field, 0)"
                  @input="onRangeInput($event, field, 0)"
                  @keydown="onEnter"
                />
                <span class="bms-query-filter__tilde">~</span>
                <input
                  class="bms-query-filter__control"
                  :data-test="`input-${field.key}-end`"
                  :value="rangeValueOf(field, 1)"
                  @input="onRangeInput($event, field, 1)"
                  @keydown="onEnter"
                />
              </template>
              <template v-else-if="widgetOf(field) === 'multi-select'">
                <select
                  class="bms-query-filter__control"
                  multiple
                  :data-test="`input-${field.key}`"
                  @change="onMultiChange($event, field)"
                >
                  <option
                    v-for="option in field.options ?? []"
                    :key="String(option.value)"
                    :value="option.value"
                    :selected="listValueOf(field).includes(String(option.value))"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </template>
              <template v-else-if="widgetOf(field) === 'select'">
                <select
                  class="bms-query-filter__control"
                  :data-test="`input-${field.key}`"
                  :value="textValueOf(field)"
                  @change="onSelectChange($event, field)"
                >
                  <option value="">全部</option>
                  <option v-for="option in field.options ?? []" :key="String(option.value)" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </template>
              <template v-else-if="widgetOf(field) === 'switch'">
                <select
                  class="bms-query-filter__control"
                  :data-test="`input-${field.key}`"
                  :value="textValueOf(field)"
                  @change="onSelectChange($event, field)"
                >
                  <option value="">全部</option>
                  <option value="1">是</option>
                  <option value="0">否</option>
                </select>
              </template>
              <template v-else>
                <input
                  class="bms-query-filter__control"
                  :data-test="`input-${field.key}`"
                  :placeholder="field.placeholder"
                  :value="textValueOf(field)"
                  @input="onTextInput($event, field)"
                  @keydown="onEnter"
                />
              </template>
            </slot>
            <button
              v-if="hasAdvanced(field)"
              type="button"
              class="bms-query-filter__advanced"
              :data-test="`advanced-${field.key}`"
              @click="openAdvanced(field)"
            >
              高级
            </button>
          </div>
        </div>
        <div class="bms-query-filter__actions">
          <button type="button" class="is-primary" data-test="search" @click="onSearch">查询</button>
          <button type="button" data-test="reset" @click="onReset">重置</button>
          <button v-if="foldable" type="button" data-test="collapse-toggle" @click="toggleCollapse">
            {{ isCollapsed ? '展开' : '收起' }}
          </button>
          <button
            v-if="showScheme"
            type="button"
            data-test="scheme-trigger"
            @click="schemePanelOpen = !schemePanelOpen"
          >
            查询方案
          </button>
          <slot name="actions" />
        </div>
      </div>

      <div v-if="invalidHint" class="bms-query-filter__hint" data-test="invalid-hint">部分筛选条件已失效，已忽略</div>

      <div v-if="schemePanelOpen" class="bms-query-filter__schemes" data-test="scheme-panel">
        <slot name="scheme-panel" :schemes="schemes" :apply="applyScheme" :save="saveScheme">
          <div
            v-for="entry in schemes"
            :key="entry.name"
            class="bms-query-filter__scheme"
            :data-test="`scheme-item-${entry.name}`"
          >
            <button type="button" @click="applyScheme(entry.name)">
              {{ entry.name }}（{{ QUERY_SCHEME_SCOPE_LABELS[entry.scope] }}）
            </button>
            <button type="button" :data-test="`scheme-default-${entry.name}`" @click="setDefaultScheme(entry.name)">
              设默认
            </button>
            <button type="button" :data-test="`scheme-delete-${entry.name}`" @click="deleteScheme(entry.name)">
              删除
            </button>
          </div>
          <div v-if="schemes.length === 0" class="bms-query-filter__scheme-empty">无匹配方案</div>
          <button
            type="button"
            data-test="scheme-save"
            @click="saveScheme(activeScheme === '' ? '新方案' : activeScheme)"
          >
            保存当前
          </button>
          <button type="button" data-test="scheme-save-as" @click="saveAsScheme('另存方案')">另存为</button>
          <button
            type="button"
            data-test="scheme-rename"
            @click="emit('rename-scheme', activeScheme, `${activeScheme}_新`)"
          >
            重命名
          </button>
        </slot>
      </div>

      <div v-if="summaries.length > 0" class="bms-query-filter__summary" data-test="summary">
        <slot name="summary" :summaries="summaries">
          <span
            v-for="item in summaries"
            :key="item.field"
            class="bms-query-filter__chip"
            :data-test="`chip-${item.field}`"
          >
            {{ item.text }}
            <button type="button" :data-test="`chip-remove-${item.field}`" @click="removeCondition(item.field)">
              ×
            </button>
          </span>
          <button type="button" class="bms-query-filter__clear" data-test="clear-all" @click="clearAll">
            清空全部
          </button>
        </slot>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-query-filter {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
  padding: var(--bms-spacing-lg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-bg);
}

.bms-query-filter__grid {
  display: grid;
  gap: var(--bms-spacing-md);
  align-items: end;
}

.bms-query-filter__field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
  min-width: 0;
}

.bms-query-filter__label {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-query-filter__control-wrap {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}

.bms-query-filter__control {
  flex: 1 1 auto;
  min-width: 0;
  height: var(--bms-control-height);
  padding: 0 var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size);
}

.bms-query-filter__tilde {
  color: var(--bms-color-text-secondary);
}

.bms-query-filter__actions {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
  justify-content: flex-end;
}

.bms-query-filter__actions button {
  height: var(--bms-control-height);
  padding: 0 var(--bms-spacing-lg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg);
  color: var(--bms-color-text);
  cursor: pointer;
}

.bms-query-filter__actions button.is-primary {
  border-color: var(--bms-color-primary);
  background: var(--bms-color-primary);
  color: var(--bms-color-bg);
}

.bms-query-filter__advanced {
  flex: 0 0 auto;
  color: var(--bms-color-primary);
  background: none;
  border: none;
  cursor: pointer;
}

.bms-query-filter__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-spacing-md);
}

.bms-query-filter__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  padding: 0 var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  color: var(--bms-color-text);
  font-size: 12px;
}

.bms-query-filter__chip button,
.bms-query-filter__clear {
  color: var(--bms-color-primary);
  background: none;
  border: none;
  cursor: pointer;
}

.bms-query-filter__schemes {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
  padding: var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-query-filter__scheme {
  display: flex;
  gap: var(--bms-spacing-md);
}

.bms-query-filter__scheme button {
  color: var(--bms-color-primary);
  background: none;
  border: none;
  cursor: pointer;
}

.bms-query-filter__hint {
  color: var(--bms-color-warning);
  font-size: 12px;
}

.bms-query-filter__placeholder,
.bms-query-filter__scheme-empty {
  color: var(--bms-color-text-secondary);
}
</style>
