<script setup lang="ts">
// 字段权限矩阵件（08_04_02）：表单 × 字段的可见 / 可编辑矩阵（默认全开、收窄、批量与分页）；单元格子件挂字段权限族基类。
import type { FieldPermRow } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import FieldPermCell from './FieldPermCell.vue'

interface Props {
  /** 字段权限矩阵（表单 × 字段）。 */
  rows?: FieldPermRow[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 搜索词（字段名 / 键）。 */
  keyword?: string
  /** 是否仅显示已收窄字段。 */
  onlyNarrowed?: boolean
  /** 每页行数（表单数，缺省 20）。 */
  pageSize?: number
  /** 当前页码（`v-model:page`，自 1 起）。 */
  page?: number
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  rows: () => [],
  disabled: false,
  keyword: '',
  onlyNarrowed: false,
  pageSize: 20,
  page: 1,
  emptyText: '暂无字段权限数据',
})

const emit = defineEmits<{
  change: [payload: { formKey: string; fieldKey: string; key: 'visible' | 'editable'; value: boolean }]
  batch: [payload: { key: 'visible' | 'editable'; value: boolean; formKey?: string }]
  'update:page': [page: number]
}>()

const { state, setState } = useBaseDataState()

/** 是否为已收窄字段。 */
function narrowed(row: FieldPermRow, index: number): boolean {
  const field = row.fields[index]
  return field !== undefined && (field.visible === false || field.editable === false)
}

/** 过滤后的矩阵（搜索 + 仅已收窄）。 */
const filtered = computed<FieldPermRow[]>(() => {
  const keyword = props.keyword.trim()
  return props.rows
    .map((row) => ({
      ...row,
      fields: row.fields.filter((field, index) => {
        if (props.onlyNarrowed && !narrowed(row, index)) {
          return false
        }
        return keyword === '' || field.label.includes(keyword) || field.key.includes(keyword)
      }),
    }))
    .filter((row) => row.fields.length > 0)
})

/** 总页数。 */
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / Math.max(props.pageSize, 1))))

/** 当前页行。 */
const pagedRows = computed<FieldPermRow[]>(() => {
  const size = Math.max(props.pageSize, 1)
  const start = (Math.min(Math.max(props.page, 1), totalPages.value) - 1) * size
  return filtered.value.slice(start, start + size)
})

watch(filtered, (list) => setState(list.length === 0 ? 'empty' : 'ready'), { immediate: true })

/** 字段权限变更上抛（补全表单键与字段键）。 */
function onCell(formKey: string, fieldKey: string, payload: { key: 'visible' | 'editable'; value: boolean }): void {
  emit('change', { formKey, fieldKey, key: payload.key, value: payload.value })
}

/** 批量设置（缺省对全部行，指定表单则仅该表单）。 */
function batch(key: 'visible' | 'editable', value: boolean, formKey?: string): void {
  emit('batch', { key, value, formKey })
}

/** 切换页码。 */
function goPage(next: number): void {
  emit('update:page', Math.min(Math.max(next, 1), totalPages.value))
}
</script>

<template>
  <div class="bms-field-perm-matrix" data-test="field-perm-matrix" :data-state="state">
    <div class="bms-field-perm-matrix__toolbar" data-test="matrix-toolbar">
      <button type="button" data-test="batch-visible" :disabled="disabled" @click="batch('visible', true)">
        全选可见
      </button>
      <button type="button" data-test="batch-invisible" :disabled="disabled" @click="batch('visible', false)">
        全选不可见
      </button>
      <button type="button" data-test="batch-editable" :disabled="disabled" @click="batch('editable', true)">
        全选可编辑
      </button>
      <span data-test="matrix-total">{{ filtered.length }} 个字段</span>
    </div>

    <p v-if="filtered.length === 0" data-test="empty">{{ emptyText }}</p>

    <div v-for="row in pagedRows" :key="row.formKey" :data-test="`form-${row.formKey}`">
      <strong data-test="matrix-form-label">{{ row.formLabel }}</strong>
      <div
        v-for="field in row.fields"
        :key="field.key"
        class="bms-field-perm-matrix__field"
        :data-test="`field-${row.formKey}-${field.key}`"
      >
        <span class="bms-field-perm-matrix__label">{{ field.label }}</span>
        <FieldPermCell
          :form-key="row.formKey"
          :field="field"
          :disabled="disabled"
          @change="onCell(row.formKey, field.key, $event)"
        />
      </div>
    </div>

    <div v-if="totalPages > 1" class="bms-field-perm-matrix__pager" data-test="matrix-pager">
      <button type="button" data-test="page-prev" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
      <span data-test="page-current">{{ page }} / {{ totalPages }}</span>
      <button type="button" data-test="page-next" :disabled="page >= totalPages" @click="goPage(page + 1)">
        下一页
      </button>
    </div>
  </div>
</template>
