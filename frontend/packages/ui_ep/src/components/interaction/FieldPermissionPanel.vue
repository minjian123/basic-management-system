<script setup lang="ts">
// 字段权限面板（08-4-4，新口径）：某表单的字段可见 / 可编辑清单——默认全开、授予后收窄、来源判定、批量。
// 样式（11-01）：矩阵改 el-table 承载（字段 / 可见 / 可编辑 / 来源四列，可见与可编辑用 el-switch），
// 工具栏改 el-input + el-checkbox + el-button，补 <style scoped> 消费 --bms-* 令牌。
import { fieldPermOf, type FieldMeta, type FieldPermEntry, type FieldPermPatch } from '@bms/core'
import { ElButton, ElCheckbox, ElInput, ElSwitch, ElTable, ElTableColumn } from 'element-plus'
import { computed, ref } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'

interface Props {
  /** 表单 id。 */
  formId?: string
  /** 该表单字段清单。 */
  fields?: FieldMeta[]
  /** 字段权限条目（仅收窄项）。 */
  fieldEntries?: FieldPermEntry[]
  /** 当前上下文来源菜单 id。 */
  sourceMenuId?: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  formId: '',
  fields: () => [],
  fieldEntries: () => [],
  sourceMenuId: '0',
  disabled: false,
  emptyText: '暂无字段',
})

const emit = defineEmits<{
  change: [payload: { fieldId: string; patch: FieldPermPatch }]
  batch: [payload: { kind: 'visible' | 'editable'; value: boolean }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 搜索词。 */
const keyword = ref('')
/** 仅显示已收窄。 */
const onlyNarrowed = ref(false)

/** 字段行（默认全开；含来源判定）。 */
const rows = computed(() =>
  props.fields
    .filter((field) => field.name.includes(keyword.value))
    .map((field) => {
      const entry = fieldPermOf(props.fieldEntries, props.formId, field.id)
      const narrowed = entry !== undefined && (entry.visible === false || entry.editable === false)
      return {
        id: field.id,
        name: field.name,
        visible: entry?.visible ?? true,
        editable: entry?.editable ?? true,
        readonly: entry !== undefined && entry.sourceMenuId !== props.sourceMenuId,
        narrowed,
      }
    })
    .filter((row) => !onlyNarrowed.value || row.narrowed),
)

/** 变更字段权限（`editable=false` 时联动不可见）。 */
function change(fieldId: string, patch: FieldPermPatch): void {
  emit('change', { fieldId, patch })
}

/** 可见开关变更。 */
function onVisible(id: string, value: boolean | string | number): void {
  change(id, { visible: value === true })
}

/** 可编辑开关变更。 */
function onEditable(id: string, value: boolean | string | number): void {
  change(id, { editable: value === true })
}
</script>

<template>
  <div class="bms-field-perm" data-test="field-perm" :data-disabled="disabled || undefined">
    <div class="bms-field-perm__toolbar">
      <el-input
        v-model="keyword"
        data-test="field-search"
        class="bms-field-perm__search"
        placeholder="搜索字段"
        size="small"
        clearable
        :disabled="disabled"
      />
      <el-checkbox v-model="onlyNarrowed" data-test="field-only-narrowed" :disabled="disabled">
        仅显示已收窄
      </el-checkbox>
      <div class="bms-field-perm__actions">
        <el-button
          data-test="field-batch-visible"
          size="small"
          :disabled="disabled"
          @click="emit('batch', { kind: 'visible', value: true })"
        >
          全选可见
        </el-button>
        <el-button
          data-test="field-batch-hidden"
          size="small"
          :disabled="disabled"
          @click="emit('batch', { kind: 'visible', value: false })"
        >
          全选不可见
        </el-button>
        <el-button
          data-test="field-batch-editable"
          size="small"
          :disabled="disabled"
          @click="emit('batch', { kind: 'editable', value: true })"
        >
          全选可编辑
        </el-button>
      </div>
    </div>

    <el-table
      v-if="rows.length > 0"
      class="bms-field-perm__table"
      data-test="field-table"
      :data="rows"
      size="small"
      border
      :row-key="(row: { id: string }) => row.id"
    >
      <el-table-column label="字段" min-width="160">
        <template #default="{ row }">
          <span :data-test="`field-row-${row.id}`">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="可见" width="90" align="center">
        <template #default="{ row }">
          <el-switch
            :data-test="`field-visible-${row.id}`"
            :model-value="row.visible"
            size="small"
            :disabled="disabled || row.readonly"
            @update:model-value="onVisible(row.id, $event)"
          />
        </template>
      </el-table-column>
      <el-table-column label="可编辑" width="90" align="center">
        <template #default="{ row }">
          <el-switch
            :data-test="`field-editable-${row.id}`"
            :model-value="row.editable"
            size="small"
            :disabled="disabled || row.readonly || !row.visible"
            @update:model-value="onEditable(row.id, $event)"
          />
        </template>
      </el-table-column>
      <el-table-column label="来源" width="150">
        <template #default="{ row }">
          <span v-if="row.readonly" class="bms-field-perm__readonly" data-test="field-readonly">来自其它来源</span>
          <span v-else class="bms-field-perm__own">直接授予</span>
        </template>
      </el-table-column>
    </el-table>

    <p v-if="rows.length === 0" class="bms-field-perm__empty" data-test="empty">{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.bms-field-perm {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-field-perm__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2) var(--bms-space-4);
}

.bms-field-perm__search {
  width: 200px;
}

.bms-field-perm__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  margin-left: auto;
}

.bms-field-perm__table {
  width: 100%;
}

.bms-field-perm__table :deep(.el-table__header th) {
  background: var(--bms-table-header-bg);
  color: var(--bms-color-text);
}

.bms-field-perm__table :deep(.el-table__border),
.bms-field-perm__table :deep(.el-table__inner-wrapper::before) {
  background-color: var(--bms-table-border);
}

.bms-field-perm__table :deep(.el-table__body tr:hover > td) {
  background: var(--bms-table-row-hover-bg);
}

.bms-field-perm__readonly {
  padding: 0 var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  font-style: normal;
  background: var(--bms-perm-readonly-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-field-perm__own {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-field-perm__empty {
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}
</style>
