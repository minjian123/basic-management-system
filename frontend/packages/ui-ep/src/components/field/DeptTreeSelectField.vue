<script setup lang="ts">
// 部门树选择字段（06_05）：部门树一次性加载、单选 / 多选、路径回显、含下级透传；数据范围与脱敏由出口实现侧强制（前端不二次过滤）。
import {
  ORG_EMPTY_TEXT,
  ORG_PLACEHOLDER_TEXT,
  findOrgDeptPath,
  toOrgTreeNodes,
  type OrgSourceAdapter,
  type OrgStatus,
} from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseOrgSelect } from '../../composables/useBaseOrgSelect'
import TreeSelectField from './TreeSelectField.vue'

/** 字段值类型。 */
export type DeptFieldValue = string | string[] | undefined

interface Props {
  /** 值（受控；多选为数组）。 */
  modelValue?: DeptFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 组织数据源（未注入即占位零请求）。 */
  source?: OrgSourceAdapter
  /** 多选。 */
  multiple?: boolean
  /** 状态过滤（空串不限定）。 */
  status?: OrgStatus | ''
  /** 含下级（查询区过滤参数）。 */
  includeChildren?: boolean
  /** 是否展示「含下级」勾选。 */
  showIncludeChildren?: boolean
  /** 可搜索。 */
  searchable?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（路径回显）。 */
  readonly?: boolean
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
  multiple: false,
  status: '',
  includeChildren: false,
  showIncludeChildren: false,
  searchable: true,
  disabled: false,
  readonly: false,
  placeholder: '请选择部门',
  degradeText: ORG_PLACEHOLDER_TEXT,
  emptyText: ORG_EMPTY_TEXT,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: DeptFieldValue]
  change: [value: DeptFieldValue]
  'update:includeChildren': [value: boolean]
  retry: []
  invalid: [message: string]
}>()

const api = useBaseOrgSelect({
  ready: props.ready,
  kind: 'dept',
  multiple: props.multiple,
  source: props.source,
  disabled: props.disabled,
})

watch(
  () => props.ready,
  (next) => {
    api.setReady(next)
    if (next) {
      void api.loadDeptTree()
    }
  },
  { immediate: true },
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
  () => props.status,
  (next) => api.setStatus(next),
)
watch(
  () => props.modelValue,
  (next) => api.syncValue(next),
  { immediate: true },
)

api.onValueChange((next) => {
  emit('update:modelValue', next)
  emit('change', next)
})

const treeNodes = computed(() => toOrgTreeNodes(api.deptNodes.value))

const readonlyPaths = computed(() =>
  api.selectedIds.value.map((id) => {
    const path = findOrgDeptPath(api.deptNodes.value, id)
    return path.length > 0 ? path.join(' / ') : api.labelOf(id)
  }),
)

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : api.errorText.value))

/** 重试加载（失效部门树缓存后重取）。 */
function onRetry(): void {
  api.invalidate('dept')
  void api.loadDeptTree()
  emit('retry')
}

/**
 * 含下级勾选变更。
 *
 * @param event 变更事件。
 */
function onIncludeChange(event: Event): void {
  emit('update:includeChildren', (event.target as HTMLInputElement).checked)
}
</script>

<template>
  <div
    class="bms-dept-tree-select-field"
    data-test="dept-tree-select-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <div class="bms-dept-tree-select-field__row">
        <div v-if="readonly" class="bms-dept-tree-select-field__readonly" data-test="dept-readonly">
          <span v-for="(path, index) in readonlyPaths" :key="index">{{ path }}</span>
          <span v-if="readonlyPaths.length === 0">—</span>
        </div>
        <tree-select-field
          v-else
          class="bms-dept-tree-select-field__control"
          :model-value="modelValue"
          :data="treeNodes"
          :multiple="multiple"
          :searchable="searchable"
          :disabled="disabled"
          :placeholder="placeholder"
          :empty-text="emptyText"
          :error-message="errorMessage"
          @update:model-value="emit('update:modelValue', $event)"
          @change="emit('change', $event)"
          @invalid="emit('invalid', $event)"
        />
        <label v-if="showIncludeChildren && !readonly" class="bms-dept-tree-select-field__include">
          <input
            type="checkbox"
            :checked="includeChildren"
            :disabled="disabled"
            data-test="dept-include-children"
            @change="onIncludeChange"
          />
          含下级
        </label>
      </div>
      <p v-if="resolvedError !== ''" class="bms-field-error" data-test="dept-error">{{ resolvedError }}</p>
      <button
        v-if="api.error.value"
        type="button"
        class="bms-dept-tree-select-field__retry"
        data-test="dept-retry"
        @click="onRetry"
      >
        重试
      </button>
    </template>
  </div>
</template>

<style scoped>
.bms-dept-tree-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-dept-tree-select-field__row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}
.bms-dept-tree-select-field__control {
  flex: 1;
}
.bms-dept-tree-select-field__readonly {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
}
.bms-dept-tree-select-field__include {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text-secondary);
  white-space: nowrap;
}
.bms-dept-tree-select-field__retry {
  align-self: flex-start;
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
