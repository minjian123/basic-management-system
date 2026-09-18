<script setup lang="ts">
// 通用表格（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { computed, ref, watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 表格列定义。 */
export interface DataTableColumn {
  /** 字段名。 */
  key: string
  /** 列头文案。 */
  title: string
  /** 固定列宽（px）。 */
  width?: number
  /** 是否参与排序。 */
  sortable?: boolean
}

/** 排序状态。 */
export interface DataTableSort {
  /** 字段名。 */
  prop: string
  /** 方向。 */
  order: 'asc' | 'desc'
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 列定义。 */
  columns?: DataTableColumn[]
  /** 行数据。 */
  data?: Record<string, unknown>[]
  /** 加载中。 */
  loading?: boolean
  /** 总条数。 */
  total?: number
  /** 当前页（从 1 起）。 */
  page?: number
  /** 每页条数。 */
  pageSize?: number
  /** 行主键字段。 */
  rowKey?: string
  /** 是否可多选。 */
  selectable?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  columns: () => [],
  data: () => [],
  loading: false,
  total: 0,
  page: 1,
  pageSize: 20,
  rowKey: 'id',
  selectable: false,
  degradeText: '表格数据未就绪（占位）',
})

const emit = defineEmits<{
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  'sort-change': [sort: DataTableSort]
  'selection-change': [keys: string[]]
  'row-click': [row: Record<string, unknown>]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })
const selected = ref<string[]>([])
const sort = ref<DataTableSort | undefined>()

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

const allSelected = computed(
  () => props.data.length > 0 && selected.value.length === props.data.length,
)

function rowId(row: Record<string, unknown>): string {
  return String(row[props.rowKey])
}

function toggleAll(): void {
  selected.value = allSelected.value ? [] : props.data.map((row) => rowId(row))
  emit('selection-change', [...selected.value])
}

function toggleRow(row: Record<string, unknown>): void {
  const id = rowId(row)
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id]
  emit('selection-change', [...selected.value])
}

function emitSort(column: DataTableColumn): void {
  const order: DataTableSort['order'] =
    sort.value?.prop === column.key && sort.value.order === 'asc' ? 'desc' : 'asc'
  sort.value = { prop: column.key, order }
  emit('sort-change', sort.value)
}
</script>

<template>
  <div class="bms-data-table" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-data-table__toolbar" data-test="toolbar">
        <slot name="toolbar" />
      </div>
      <table v-if="data.length > 0" class="bms-data-table__table" data-test="data-table">
        <thead>
          <tr>
            <th v-if="selectable" class="bms-data-table__cell--check">
              <input type="checkbox" data-test="select-all" :checked="allSelected" @change="toggleAll" />
            </th>
            <th
              v-for="column in columns"
              :key="column.key"
              :style="column.width ? { width: `${column.width}px` } : undefined"
              :data-sortable="column.sortable || undefined"
              @click="column.sortable && emitSort(column)"
            >
              {{ column.title }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in data"
            :key="rowId(row)"
            :data-test="`row-${rowId(row)}`"
            @click="emit('row-click', row)"
          >
            <td v-if="selectable" class="bms-data-table__cell--check">
              <input
                type="checkbox"
                :checked="selected.includes(rowId(row))"
                @click.stop
                @change="toggleRow(row)"
              />
            </td>
            <td v-for="column in columns" :key="column.key">
              <slot :name="`cell-${column.key}`" :row="row" :column="column">
                {{ row[column.key] }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="bms-data-table__empty" data-test="empty">
        <slot name="empty">暂无数据</slot>
      </div>
      <div class="bms-data-table__footer" data-test="footer">
        <span data-test="total">共 {{ total }} 条</span>
        <button type="button" data-test="prev" :disabled="page <= 1" @click="emit('update:page', page - 1)">
          上一页
        </button>
        <span data-test="page">{{ page }}</span>
        <button
          type="button"
          data-test="next"
          :disabled="total > 0 && page * pageSize >= total"
          @click="emit('update:page', page + 1)"
        >
          下一页
        </button>
      </div>
    </template>
  </div>
</template>
