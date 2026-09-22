<script setup lang="ts">
// 示例数据列表页：查询筛选 + 列表 + 工具区（新建 / 刷新）；双击行打开详情。
import type { FilterCondition, FilterField } from '@bms/core'
import { DataTable, PageContainer, QueryFilter, SectionContainer } from '@bms/ui-ep'
import type { DataTableColumn } from '@bms/ui-ep'
import { ElButton } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import SamplePriorityTag from '../components/SamplePriorityTag.vue'
import SampleStatusTag from '../components/SampleStatusTag.vue'
import { useSampleI18n } from '../composables/useSampleI18n'
import {
  SAMPLE_CATEGORIES,
  SAMPLE_STATUSES,
  type SampleCategory,
  type SampleQuery,
  type SampleRecord,
  type SampleStatus,
} from '../domain'
import { sampleRuntime } from '../runtime'
import { sampleService } from '../services/sample-service'

defineOptions({ name: 'SampleList' })

const router = useRouter()
const { t } = useSampleI18n()
const runtime = sampleRuntime()

const fields = computed<FilterField[]>(() => [
  {
    key: 'category',
    label: t('sample.list.category'),
    type: 'select',
    options: SAMPLE_CATEGORIES.map((item) => ({ label: t(item.labelKey), value: item.value })),
  },
  {
    key: 'status',
    label: t('sample.list.status'),
    type: 'select',
    options: SAMPLE_STATUSES.map((item) => ({ label: t(item.labelKey), value: item.value })),
  },
])

const columns = computed<DataTableColumn[]>(() => [
  { key: 'code', title: t('sample.column.code'), width: 120 },
  { key: 'name', title: t('sample.column.name'), minWidth: 160, sortable: true },
  { key: 'category', title: t('sample.column.category'), width: 100 },
  { key: 'priority', title: t('sample.column.priority'), width: 110 },
  { key: 'amount', title: t('sample.column.amount'), width: 130, align: 'right', format: 'amount', sortable: true },
  { key: 'status', title: t('sample.column.status'), width: 110 },
  { key: 'owner', title: t('sample.column.owner'), width: 110 },
  { key: 'createdAt', title: t('sample.column.createdAt'), width: 170, format: 'datetime', sortable: true },
])

const conditions = ref<FilterCondition[]>([])
const keyword = ref('')
const query = ref<SampleQuery>({ page: 1, size: 10 })
const list = ref<SampleRecord[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<unknown>()

/** 错误文案（组件 `error` 属性为字符串口径）。 */
const errorText = computed(() => (error.value === undefined || error.value === null ? '' : String(error.value)))

/** 当前筛选（自条件模型提取，与后端筛选契约同形）。 */
function currentFilter(): Pick<SampleQuery, 'keyword' | 'category' | 'status'> {
  const valueOf = (field: string): unknown => conditions.value.find((item) => item.field === field)?.value
  const trimmed = keyword.value.trim()
  return {
    keyword: trimmed === '' ? undefined : trimmed,
    category: valueOf('category') as SampleCategory | undefined,
    status: valueOf('status') as SampleStatus | undefined,
  }
}

/** 加载当前查询。 */
async function load(): Promise<void> {
  loading.value = true
  error.value = undefined
  try {
    const result = await sampleService.list(query.value)
    list.value = result.list
    total.value = result.total
  } catch (caught) {
    error.value = caught
  } finally {
    loading.value = false
  }
}

/** 查询（回第 1 页）。 */
async function onSearch(): Promise<void> {
  query.value = { ...query.value, ...currentFilter(), page: 1 }
  await load()
}

/** 重置筛选。 */
async function onReset(): Promise<void> {
  conditions.value = []
  keyword.value = ''
  query.value = { ...query.value, keyword: undefined, category: undefined, status: undefined, page: 1 }
  await load()
}

/** 翻页。 */
async function onPageChange(next: number): Promise<void> {
  query.value = { ...query.value, page: next }
  await load()
}

/** 改页长（回第 1 页）。 */
async function onPageSizeChange(next: number): Promise<void> {
  query.value = { ...query.value, page: 1, size: next }
  await load()
}

/** 打开详情。 */
function openDetail(row: Record<string, unknown>): void {
  void router.push({ name: 'SampleDetail', params: { id: String(row.id) } })
}

/** 打开新建表单。 */
function openCreate(): void {
  void router.push({ name: 'SampleForm' })
}

onMounted(load)
</script>

<template>
  <page-container :title="t('sample.list.title')" :description="t('sample.list.description')">
    <section-container>
      <query-filter
        :ready="true"
        :fields="fields"
        :conditions="conditions"
        :keyword="keyword"
        :loading="loading"
        @update:conditions="conditions = $event"
        @update:keyword="keyword = $event"
        @search="onSearch"
        @reset="onReset"
      />
    </section-container>
    <section-container>
      <data-table
        :ready="true"
        :columns="columns"
        :data="list"
        :total="total"
        :page="query.page"
        :page-size="query.size"
        :loading="loading"
        :error="errorText"
        row-key="id"
        selectable
        form-key="sample_list"
        :empty-text="t('sample.list.empty')"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
        @row-dblclick="openDetail"
        @refresh="load"
        @retry="load"
      >
        <template #toolbar>
          <el-button v-if="runtime.canEdit" type="primary" data-test="sample-create" @click="openCreate">
            {{ t('sample.list.create') }}
          </el-button>
          <el-button data-test="sample-refresh" @click="load">{{ t('sample.list.refresh') }}</el-button>
        </template>
        <template #cell-priority="{ row }">
          <sample-priority-tag :value="(row as unknown as SampleRecord).priority" />
        </template>
        <template #cell-status="{ row }">
          <sample-status-tag :value="(row as unknown as SampleRecord).status" />
        </template>
      </data-table>
    </section-container>
  </page-container>
</template>
