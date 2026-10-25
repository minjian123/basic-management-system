<script setup lang="ts">
// 组织选择字段（06_05 真实实现）：用户 / 岗位 / 部门三类远程搜索、多选与上限、只读回显、已删除 / 停用占位；
// 数据通路经注入式组织数据源（未注入即占位零请求），保留 06_01 冻结对外契约（仅向后兼容新增）。
import { ElOption, ElSelect } from 'element-plus'
import {
  ORG_EMPTY_TEXT,
  ORG_PLACEHOLDER_TEXT,
  ORG_SEARCH_DEBOUNCE,
  normalizeOrgIds,
  orgTagSummary,
  normalizeOrgKind,
  type BaseUserDisplay,
  type OrgKind,
  type OrgSourceAdapter,
  type OrgStatus,
} from '@bms/core'
import { computed, onScopeDispose, watch } from 'vue'

import { useBaseOrgSelect } from '../../composables/useBaseOrgSelect'
import { debounce } from '../../utils/debounce'
import EmptyState from '../feedback/EmptyState.vue'
import SelectInput from '../input/SelectInput.vue'
import type { InputOptions } from '../input/types'
import DeptTreeSelectField from './DeptTreeSelectField.vue'

/** 字段值类型（单值 / 多选数组）。 */
export type OrgFieldValue = string | number | (string | number)[]

interface Props {
  /** 值（受控）。 */
  modelValue?: OrgFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 静态选项（未注入数据源时的兼容通路，沿用 `06_01` 就绪语义）。 */
  options?: InputOptions
  /** 多选（组织字段缺省多选）。 */
  multiple?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 对象类型（`org` / `dept` 视为部门）。 */
  kind?: OrgKind
  /** 可搜索（远程搜索）。 */
  searchable?: boolean
  /** 组织数据源（未注入即占位零请求）。 */
  source?: OrgSourceAdapter
  /** 用户展示能力（缺省由投影内建花名册）。 */
  userDisplay?: BaseUserDisplay
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 状态过滤（空串不限定）。 */
  status?: OrgStatus | ''
  /** 部门过滤标识。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 部门树是否展示「含下级」勾选（查询区用法）。 */
  showIncludeChildren?: boolean
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
  /** 下拉是否展示头像（用户类型）。 */
  showAvatar?: boolean
  /** 下拉是否展示编码（岗位类型）。 */
  showCode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  options: () => [],
  multiple: true,
  disabled: false,
  placeholder: '请选择组织',
  degradeText: ORG_PLACEHOLDER_TEXT,
  kind: 'user',
  searchable: true,
  source: undefined,
  userDisplay: undefined,
  limit: 0,
  status: '',
  deptId: '',
  includeChildren: false,
  showIncludeChildren: false,
  readonly: false,
  required: false,
  errorMessage: '',
  emptyText: ORG_EMPTY_TEXT,
  clearable: true,
  collapseAfter: 1,
  showAvatar: false,
  showCode: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: OrgFieldValue | undefined]
  change: [value: OrgFieldValue | undefined]
  retry: []
  invalid: [message: string]
  'limit-exceed': [limit: number]
  'update:deptId': [value: string]
  'update:includeChildren': [value: boolean]
}>()

const api = useBaseOrgSelect({
  ready: props.ready,
  kind: props.kind,
  multiple: props.multiple,
  limit: props.limit,
  source: props.source,
  userDisplay: props.userDisplay,
  disabled: props.disabled,
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.kind,
  (next) => api.setKind(normalizeOrgKind(next) ?? 'user'),
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
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.userDisplay,
  (next) => api.setUserDisplay(next),
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

const isDept = computed(() => api.kind.value === 'dept')
const useStaticOptions = computed(() => props.source === undefined && props.options.length > 0)
const selectModelValue = computed(() => api.value.value)
const deptValue = computed<string | string[] | undefined>(() => {
  const current = props.modelValue
  if (Array.isArray(current)) {
    return current.map((item) => String(item))
  }
  return current === undefined ? undefined : String(current)
})
const tag = computed(() => orgTagSummary(api.selectedItems.value, props.collapseAfter))

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
  api.invalidate(isDept.value ? 'dept' : undefined)
  if (isDept.value) {
    void api.loadDeptTree()
  } else {
    void api.load()
  }
  emit('retry')
}

/**
 * 核心值 → 字段值（空数组归一为 `undefined`）。
 *
 * @param value 核心值。
 */
function toFieldValue(value: string | string[] | undefined): OrgFieldValue | undefined {
  if (Array.isArray(value)) {
    return value.length === 0 ? undefined : value
  }
  return value
}
</script>

<template>
  <div
    class="bms-org-select-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-kind="api.kind.value"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <dept-tree-select-field
      v-else-if="isDept"
      :model-value="deptValue"
      :ready="true"
      :source="source"
      :multiple="multiple"
      :disabled="disabled"
      :readonly="readonly"
      :status="status"
      :include-children="includeChildren"
      :show-include-children="showIncludeChildren"
      :placeholder="placeholder"
      :degrade-text="degradeText"
      :empty-text="emptyText"
      :error-message="errorMessage"
      @update:model-value="emit('update:modelValue', $event)"
      @change="emit('change', $event)"
      @update:include-children="emit('update:includeChildren', $event)"
      @retry="emit('retry')"
      @invalid="emit('invalid', $event)"
    />

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

    <div v-else-if="readonly" class="bms-org-select-field__readonly" data-test="org-readonly">
      <span v-for="item in tag.visible" :key="item.id" class="bms-org-select-field__label">{{ api.labelOf(item.id) }}</span>
      <span v-if="tag.overflow > 0" class="bms-org-select-field__overflow" data-test="org-tag-overflow">+{{ tag.overflow }}</span>
      <span v-if="api.selectedItems.value.length === 0">—</span>
    </div>

    <template v-else>
      <el-select
        class="bms-org-select-field__control"
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
        :data-test="'org-select'"
        @visible-change="onVisibleChange"
        @update:model-value="onSelectUpdate"
      >
        <el-option
          v-for="item in api.items.value"
          :key="item.id"
          :label="api.labelOf(item.id)"
          :value="item.id"
          :disabled="item.deleted || item.status === 'disabled'"
          :data-test="`org-option-${item.id}`"
        >
          <slot name="option" :item="item">
            <span class="bms-org-select-field__option">
              <img
                v-if="showAvatar && item.avatar"
                class="bms-org-select-field__avatar"
                :src="item.avatar"
                alt=""
              />
              <span>{{ item.name === '' ? item.id : item.name }}</span>
              <span v-if="item.deleted" class="bms-org-select-field__marker" data-test="org-marker-deleted">已删除</span>
              <span v-else-if="item.status === 'disabled'" class="bms-org-select-field__marker" data-test="org-marker-disabled">停用</span>
              <span v-if="showCode && item.code" class="bms-org-select-field__code">{{ item.code }}</span>
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

    <p v-if="internalError !== ''" class="bms-field-error" data-test="org-error">{{ internalError }}</p>
    <button
      v-if="api.error.value"
      type="button"
      class="bms-org-select-field__retry"
      data-test="org-retry"
      @click="onRetry"
    >
      重试
    </button>
  </div>
</template>

<style scoped>
.bms-org-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-org-select-field__control {
  width: 100%;
}
.bms-org-select-field__option {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}
.bms-org-select-field__avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
}
.bms-org-select-field__marker {
  color: var(--bms-org-marker-deleted-color);
  font-size: 12px;
}
.bms-org-select-field__code {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
.bms-org-select-field__readonly {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
}
.bms-org-select-field__label,
.bms-org-select-field__overflow {
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-org-tag-bg);
  border: 1px solid var(--bms-org-border);
  border-radius: var(--bms-radius-sm);
}
.bms-org-select-field__retry {
  align-self: flex-start;
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
