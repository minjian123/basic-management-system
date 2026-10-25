<script setup lang="ts">
// 岗位选择字段（06_05）：远程搜索、多选与上限、状态过滤、编码展示、只读回显、已删除 / 停用占位。
import { ElOption, ElSelect } from 'element-plus'
import {
  ORG_EMPTY_TEXT,
  ORG_PLACEHOLDER_TEXT,
  ORG_SEARCH_DEBOUNCE,
  normalizeOrgIds,
  orgTagSummary,
  type OrgSourceAdapter,
  type OrgStatus,
} from '@bms/core'
import { computed, onScopeDispose, watch } from 'vue'

import { useBaseOrgSelect } from '../../composables/useBaseOrgSelect'
import { debounce } from '../../utils/debounce'
import EmptyState from '../feedback/EmptyState.vue'

/** 字段值类型。 */
export type PostFieldValue = string | number | (string | number)[]

interface Props {
  /** 值（受控）。 */
  modelValue?: PostFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 组织数据源（未注入即占位零请求）。 */
  source?: OrgSourceAdapter
  /** 多选（缺省多选）。 */
  multiple?: boolean
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 部门过滤标识。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤（空串不限定）。 */
  status?: OrgStatus | ''
  /** 下拉是否展示编码。 */
  showCode?: boolean
  /** 可搜索（远程搜索）。 */
  searchable?: boolean
  /** 可清空。 */
  clearable?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读回显。 */
  readonly?: boolean
  /** 必填。 */
  required?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  source: undefined,
  multiple: true,
  limit: 0,
  deptId: '',
  includeChildren: false,
  status: '',
  showCode: true,
  searchable: true,
  clearable: true,
  disabled: false,
  readonly: false,
  required: false,
  placeholder: '请选择岗位',
  degradeText: ORG_PLACEHOLDER_TEXT,
  emptyText: ORG_EMPTY_TEXT,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: PostFieldValue | undefined]
  change: [value: PostFieldValue | undefined]
  retry: []
  invalid: [message: string]
  'limit-exceed': [limit: number]
}>()

const api = useBaseOrgSelect({
  ready: props.ready,
  kind: 'post',
  multiple: props.multiple,
  limit: props.limit,
  source: props.source,
  disabled: props.disabled,
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.source,
  (next) => api.setSource(next),
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
  () => props.status,
  (next) => api.setStatus(next),
  { immediate: true },
)
watch(
  [() => props.deptId, () => props.includeChildren],
  ([nextDept, nextChildren]) => api.setDeptFilter(nextDept, nextChildren),
  { immediate: true },
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
}, ORG_SEARCH_DEBOUNCE)
onScopeDispose(() => loadDebounced.cancel())

const tag = computed(() => orgTagSummary(api.selectedItems.value, 1))

const internalError = computed(() => {
  if (props.errorMessage !== '') {
    return props.errorMessage
  }
  if (api.errorText.value !== '') {
    return api.errorText.value
  }
  if (props.required && api.selectedIds.value.length === 0) {
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
 * 控件选择变更（截断超限并回写）。
 *
 * @param next 控件值。
 */
function onSelectUpdate(next: unknown): void {
  if (!props.multiple) {
    const single = Array.isArray(next) ? next[0] : next
    api.setValue(single === undefined || single === null ? undefined : String(single))
    return
  }
  const desired = normalizeOrgIds(next, true)
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
 * 岗位展示文案（含编码）。
 *
 * @param id 标识。
 */
function postLabel(id: string): string {
  const item = api.select.itemOf(id)
  const label = api.labelOf(id)
  if (!props.showCode || item?.code === undefined || item.code === '') {
    return label
  }
  return `${label}（${item.code}）`
}

/**
 * 核心值 → 字段值（空数组归一为 `undefined`）。
 *
 * @param value 核心值。
 */
function toFieldValue(value: string | string[] | undefined): PostFieldValue | undefined {
  if (Array.isArray(value)) {
    return value.length === 0 ? undefined : value
  }
  return value
}
</script>

<template>
  <div
    class="bms-post-select-field"
    data-test="post-select-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <div v-else-if="readonly" class="bms-post-select-field__readonly" data-test="post-readonly">
      <span v-for="item in tag.visible" :key="item.id" class="bms-post-select-field__label">{{ postLabel(item.id) }}</span>
      <span v-if="tag.overflow > 0" class="bms-post-select-field__overflow" data-test="post-tag-overflow">+{{ tag.overflow }}</span>
      <span v-if="api.selectedItems.value.length === 0">—</span>
    </div>

    <template v-else>
      <el-select
        class="bms-post-select-field__control"
        data-test="post-select"
        :model-value="api.value.value"
        :multiple="multiple"
        :filterable="searchable"
        :remote="searchable"
        :remote-method="onRemoteSearch"
        :loading="api.loading.value"
        :disabled="api.disabled.value"
        :clearable="clearable"
        :collapse-tags="true"
        :max-collapse-tags="1"
        :placeholder="placeholder"
        @visible-change="onVisibleChange"
        @update:model-value="onSelectUpdate"
      >
        <el-option
          v-for="item in api.items.value"
          :key="item.id"
          :label="postLabel(item.id)"
          :value="item.id"
          :disabled="item.deleted || item.status === 'disabled'"
          :data-test="`post-option-${item.id}`"
        >
          <slot name="option" :item="item">
            <span class="bms-post-select-field__option">
              <span>{{ api.labelOf(item.id) }}</span>
              <span v-if="showCode && item.code" class="bms-post-select-field__code" data-test="post-code">{{ item.code }}</span>
            </span>
          </slot>
        </el-option>
        <template #empty>
          <slot name="empty">
            <empty-state type="result" :description="emptyText" />
          </slot>
        </template>
      </el-select>
    </template>

    <p v-if="internalError !== ''" class="bms-field-error" data-test="post-error">{{ internalError }}</p>
    <button
      v-if="api.error.value"
      type="button"
      class="bms-post-select-field__retry"
      data-test="post-retry"
      @click="onRetry"
    >
      重试
    </button>
  </div>
</template>

<style scoped>
.bms-post-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-post-select-field__control {
  width: 100%;
}
.bms-post-select-field__option {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}
.bms-post-select-field__code {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
.bms-post-select-field__readonly {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
}
.bms-post-select-field__label,
.bms-post-select-field__overflow {
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-org-tag-bg);
  border: 1px solid var(--bms-org-border);
  border-radius: var(--bms-radius-sm);
}
.bms-post-select-field__retry {
  align-self: flex-start;
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
