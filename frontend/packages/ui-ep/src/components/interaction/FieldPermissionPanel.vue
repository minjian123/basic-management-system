<script setup lang="ts">
// 字段权限面板（08-4-4，新口径）：某表单的字段可见 / 可编辑清单——默认全开、授予后收窄、来源判定、批量。
import { fieldPermOf, type FieldMeta, type FieldPermEntry, type FieldPermPatch } from '@bms/core'
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
</script>

<template>
  <div class="bms-field-perm" data-test="field-perm" :data-disabled="disabled || undefined">
    <div class="bms-field-perm__toolbar">
      <input v-model="keyword" type="search" data-test="field-search" placeholder="搜索字段" :disabled="disabled" />
      <label>
        <input v-model="onlyNarrowed" type="checkbox" data-test="field-only-narrowed" :disabled="disabled" />
        仅显示已收窄
      </label>
      <button type="button" data-test="field-batch-visible" :disabled="disabled" @click="emit('batch', { kind: 'visible', value: true })">
        全选可见
      </button>
      <button type="button" data-test="field-batch-hidden" :disabled="disabled" @click="emit('batch', { kind: 'visible', value: false })">
        全选不可见
      </button>
      <button type="button" data-test="field-batch-editable" :disabled="disabled" @click="emit('batch', { kind: 'editable', value: true })">
        全选可编辑
      </button>
    </div>

    <p v-if="rows.length === 0" data-test="empty">{{ emptyText }}</p>

    <div v-for="row in rows" :key="row.id" class="bms-field-perm__row" :data-test="`field-row-${row.id}`">
      <span data-test="field-name">{{ row.name }}</span>
      <label>
        <input
          type="checkbox"
          :data-test="`field-visible-${row.id}`"
          :checked="row.visible"
          :disabled="disabled || row.readonly"
          @change="change(row.id, { visible: ($event.target as HTMLInputElement).checked })"
        />
        可见
      </label>
      <label>
        <input
          type="checkbox"
          :data-test="`field-editable-${row.id}`"
          :checked="row.editable"
          :disabled="disabled || row.readonly || !row.visible"
          @change="change(row.id, { editable: ($event.target as HTMLInputElement).checked })"
        />
        可编辑
      </label>
      <em v-if="row.readonly" data-test="field-readonly">来自其它来源</em>
    </div>
  </div>
</template>
