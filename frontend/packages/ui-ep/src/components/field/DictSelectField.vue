<script setup lang="ts">
// 字典选择字段（06_06 真实实现）：字典下拉（小字典全量 / 大字典远程搜索 + 虚拟滚动）、禁用项、级联父值、
// 多选与上限、只读回显；数据通路经注入式字典数据源与缓存能力（未注入即占位零请求），保留 06_01 冻结对外契约。
import { ElOption, ElSelect, ElSelectV2 } from 'element-plus'
import {
  DICT_EMPTY_TEXT,
  DICT_PLACEHOLDER_TEXT,
  DICT_SEARCH_DEBOUNCE,
  normalizeDictValues,
  type BaseDictStore,
  type DictItem,
  type DictSourceAdapter,
  type DictStorageChannel,
} from '@bms/core'
import { computed, onScopeDispose, watch } from 'vue'

import { useBaseDictSelect } from '../../composables/useBaseDictSelect'
import { debounce } from '../../utils/debounce'
import EmptyState from '../feedback/EmptyState.vue'
import SelectInput from '../input/SelectInput.vue'
import type { InputOptions } from '../input/types'

/** 字段值类型（单值 / 多选数组）。 */
export type DictFieldValue = string | number | (string | number)[]

interface Props {
  /** 值（受控）。 */
  modelValue?: DictFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 静态选项（未注入数据源时的兼容通路，沿用 `06_01` 就绪语义）。 */
  options?: InputOptions
  /** 多选。 */
  multiple?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 字典类型码（真实取数必填）。 */
  dictType?: string
  /** 可搜索（远程搜索 / 本地过滤）。 */
  searchable?: boolean
  /** 字典数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 缓存能力（缺省由投影内建；跨件共享请外部传入）。 */
  store?: BaseDictStore
  /** 本地二次缓存通道（缺省由投影内建 localStorage 通道）。 */
  storage?: DictStorageChannel | undefined
  /** 语言（缺省默认语言）。 */
  locale?: string
  /** 级联父值（空串 = 顶层）。 */
  parentId?: string
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 只读回显。 */
  readonly?: boolean
  /** 必填。 */
  required?: boolean
  /** 外部错误文案（优先）。 */
  errorMessage?: string
  /** 空态文案。 */
  emptyText?: string
  /** 可清空。 */
  clearable?: boolean
  /** 标签折叠阈值（超过折叠为「首项 +N」；≤ 0 不折叠）。 */
  collapseAfter?: number
  /** 下拉是否展示语义色点。 */
  showColor?: boolean
  /** 只读是否以标签形态呈现。 */
  readonlyTag?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  options: () => [],
  multiple: false,
  disabled: false,
  placeholder: '请选择',
  degradeText: DICT_PLACEHOLDER_TEXT,
  dictType: '',
  searchable: true,
  source: undefined,
  store: undefined,
  storage: undefined,
  locale: undefined,
  parentId: '',
  limit: 0,
  readonly: false,
  required: false,
  errorMessage: '',
  emptyText: DICT_EMPTY_TEXT,
  clearable: true,
  collapseAfter: 1,
  showColor: false,
  readonlyTag: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: DictFieldValue | undefined]
  change: [value: DictFieldValue | undefined]
  retry: []
  invalid: [message: string]
  'limit-exceed': [limit: number]
  loaded: [payload: { dictType: string; hasMore: boolean; total: number }]
}>()

const api = useBaseDictSelect({
  ready: props.ready,
  dictType: props.dictType,
  multiple: props.multiple,
  limit: props.limit,
  parentId: props.parentId,
  locale: props.locale,
  source: props.source,
  store: props.store,
  storage: props.storage,
  disabled: props.disabled,
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.dictType,
  (next) => api.setDictType(next),
)
watch(
  () => props.multiple,
  (next) => api.setMultiple(next),
)
watch(
  () => props.limit,
  (next) => api.setLimit(next),
)
watch(
  () => props.parentId,
  (next) => api.setParent(next),
  { immediate: true },
)
watch(
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.modelValue,
  (next) => api.syncValue(next),
  { immediate: true },
)

api.onValueChange((next) => {
  const value = toFieldValue(next)
  emit('update:modelValue', value)
  emit('change', value)
})

const loadDebounced = debounce(() => {
  void api.load()
}, DICT_SEARCH_DEBOUNCE)
onScopeDispose(() => loadDebounced.cancel())

const useStaticOptions = computed(() => props.source === undefined && props.options.length > 0)
const selectModelValue = computed(() => api.value.value)
const tag = computed(() => {
  const visible = props.collapseAfter > 0 ? api.selectedItems.value.slice(0, props.collapseAfter) : api.selectedItems.value
  const overflow = api.selectedItems.value.length - visible.length
  return { visible, overflow }
})

const internalError = computed(() => {
  if (props.errorMessage !== '') {
    return props.errorMessage
  }
  if (api.errorText.value !== '') {
    return api.errorText.value
  }
  if (props.required && api.selectedValues.value.length === 0) {
    return '该字段为必填项'
  }
  return ''
})

watch(internalError, (message) => {
  if (message !== '') {
    emit('invalid', message)
  }
})

/**
 * 远程搜索（300ms 防抖）。
 *
 * @param keyword 关键词。
 */
function onRemoteSearch(keyword: string): void {
  api.setKeyword(keyword)
  loadDebounced()
}

/**
 * 下拉展开（首次展开触发首屏候选）。
 *
 * @param visible 是否展开。
 */
function onVisibleChange(visible: boolean): void {
  if (visible && api.items.value.length === 0) {
    void api.load()
  }
}

/**
 * 受控控件选择变更（截断超限并回写）。
 *
 * @param next 控件值。
 */
function onSelectUpdate(next: unknown): void {
  if (!props.multiple) {
    const single = Array.isArray(next) ? next[0] : next
    api.setValue(single === undefined || single === null ? undefined : String(single))
    return
  }
  const desired = normalizeDictValues(next, true)
  const limited = props.limit > 0 ? desired.slice(0, props.limit) : desired
  const exceeded = desired.length > limited.length
  api.setLimitExceeded(exceeded)
  if (exceeded) {
    emit('limit-exceed', props.limit)
  }
  api.setValue(limited)
}

/** 重试加载（失效缓存后重取）。 */
function onRetry(): void {
  api.invalidate()
  void api.load()
  emit('retry')
}

/**
 * 核心值 → 字段值（空数组归一为 `undefined`）。
 *
 * @param value 核心值。
 */
function toFieldValue(value: string | string[] | undefined): DictFieldValue | undefined {
  if (Array.isArray(value)) {
    return value.length === 0 ? undefined : value
  }
  return value
}

/**
 * 选项语义色点样式（仅消费令牌语义，不写死色值）。
 *
 * @param item 条目。
 */
function colorClass(item: DictItem): string {
  return item.color === undefined ? '' : `bms-dict-select-field__dot--${item.color}`
}
</script>

<template>
  <div
    class="bms-dict-select-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-large="api.isLarge.value"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <select-input
      v-else-if="useStaticOptions"
      :model-value="modelValue"
      :options="options"
      :multiple="multiple"
      :searchable="searchable"
      :disabled="api.disabled.value"
      :placeholder="placeholder"
      @update:model-value="emit('update:modelValue', $event)"
      @change="emit('change', $event)"
    />

    <div v-else-if="readonly" class="bms-dict-select-field__readonly" data-test="dict-readonly">
      <template v-if="readonlyTag">
        <span v-for="item in tag.visible" :key="item.value" class="bms-dict-select-field__label">
          <span v-if="showColor" class="bms-dict-select-field__dot" :class="colorClass(item)" />
          {{ api.labelOf(item.value) }}
        </span>
      </template>
      <template v-else>
        <span>{{ api.selectionText() }}</span>
      </template>
      <span v-if="tag.overflow > 0" class="bms-dict-select-field__overflow" data-test="dict-tag-overflow">
        +{{ tag.overflow }}
      </span>
    </div>

    <el-select-v2
      v-else-if="api.isLarge.value"
      class="bms-dict-select-field__control"
      :model-value="selectModelValue"
      :options="api.items.value.map((item) => ({ value: item.value, label: api.labelOf(item.value), disabled: item.status === 'disabled' }))"
      :multiple="multiple"
      :filterable="searchable"
      :remote="searchable"
      :remote-method="onRemoteSearch"
      :loading="api.loading.value"
      :disabled="api.disabled.value"
      :clearable="clearable"
      :collapse-tags="collapseAfter > 0"
      :max-collapse-tags="collapseAfter > 0 ? collapseAfter : undefined"
      :placeholder="placeholder"
      data-test="dict-select"
      @visible-change="onVisibleChange"
      @update:model-value="onSelectUpdate"
    >
      <template #empty>
        <slot name="empty">
          <empty-state type="result" :description="emptyText" />
        </slot>
      </template>
    </el-select-v2>

    <el-select
      v-else
      class="bms-dict-select-field__control"
      :model-value="selectModelValue"
      :multiple="multiple"
      :filterable="searchable"
      :remote="searchable"
      :remote-method="onRemoteSearch"
      :loading="api.loading.value"
      :disabled="api.disabled.value"
      :clearable="clearable"
      :collapse-tags="collapseAfter > 0"
      :max-collapse-tags="collapseAfter > 0 ? collapseAfter : undefined"
      :placeholder="placeholder"
      data-test="dict-select"
      @visible-change="onVisibleChange"
      @update:model-value="onSelectUpdate"
    >
      <el-option
        v-for="item in api.items.value"
        :key="item.value"
        :label="api.labelOf(item.value)"
        :value="item.value"
        :disabled="item.status === 'disabled'"
        :data-test="`dict-option-${item.value}`"
      >
        <slot name="option" :item="item">
          <span class="bms-dict-select-field__option">
            <span v-if="showColor" class="bms-dict-select-field__dot" :class="colorClass(item)" />
            <span>{{ api.labelOf(item.value) }}</span>
            <span v-if="item.status === 'disabled'" class="bms-dict-select-field__marker" data-test="dict-marker-disabled">
              停用
            </span>
          </span>
        </slot>
      </el-option>
      <template #prefix>
        <slot name="prefix" />
      </template>
      <template #empty>
        <slot name="empty">
          <empty-state type="result" :description="emptyText" data-test="dict-empty" />
        </slot>
      </template>
    </el-select>

    <p v-if="internalError !== ''" class="bms-field-error" data-test="dict-error">{{ internalError }}</p>
    <button
      v-if="api.error.value"
      type="button"
      class="bms-dict-select-field__retry"
      data-test="dict-retry"
      @click="onRetry"
    >
      重试
    </button>
  </div>
</template>

<style scoped>
.bms-dict-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-dict-select-field__control {
  width: 100%;
}
.bms-dict-select-field__option {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}
.bms-dict-select-field__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bms-color-text-secondary);
}
.bms-dict-select-field__dot--success {
  background: var(--bms-color-success);
}
.bms-dict-select-field__dot--warning {
  background: var(--bms-color-warning);
}
.bms-dict-select-field__dot--danger {
  background: var(--bms-color-danger);
}
.bms-dict-select-field__dot--info {
  background: var(--bms-color-info);
}
.bms-dict-select-field__dot--primary {
  background: var(--bms-color-primary);
}
.bms-dict-select-field__marker {
  color: var(--bms-dict-marker-disabled-color);
  font-size: 12px;
}
.bms-dict-select-field__readonly {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
}
.bms-dict-select-field__label,
.bms-dict-select-field__overflow {
  display: inline-flex;
  align-items: center;
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-dict-tag-bg);
  border: 1px solid var(--bms-dict-border);
  border-radius: var(--bms-radius-sm);
}
.bms-dict-select-field__retry {
  align-self: flex-start;
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
