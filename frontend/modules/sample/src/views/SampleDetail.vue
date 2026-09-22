<script setup lang="ts">
// 示例数据详情页：只读字段 + 编辑入口 + 删除（不存在时呈现错误态）。
import { DescriptionList, PageContainer, SectionContainer, StatusContainer } from '@bms/ui-ep'
import type { DescItem, StatusContainerState } from '@bms/ui-ep'
import { ElButton, ElPopconfirm } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SamplePriorityTag from '../components/SamplePriorityTag.vue'
import SampleStatusTag from '../components/SampleStatusTag.vue'
import { useSampleI18n } from '../composables/useSampleI18n'
import { SAMPLE_CATEGORIES, type SampleRecord } from '../domain'
import { sampleRuntime } from '../runtime'
import { sampleService } from '../services/sample-service'

defineOptions({ name: 'SampleDetail' })

const route = useRoute()
const router = useRouter()
const { t } = useSampleI18n()
const runtime = sampleRuntime()

const record = ref<SampleRecord | null>(null)
const state = ref<StatusContainerState>('loading')

const id = computed(() => String(route.params.id ?? ''))

const items = computed<DescItem[]>(() => [
  { key: 'code', label: t('sample.column.code') },
  { key: 'name', label: t('sample.column.name') },
  {
    key: 'category',
    label: t('sample.column.category'),
    type: 'enum',
    options: SAMPLE_CATEGORIES.map((item) => ({ label: t(item.labelKey), value: item.value })),
  },
  { key: 'priority', label: t('sample.column.priority') },
  { key: 'amount', label: t('sample.column.amount'), type: 'amount' },
  { key: 'status', label: t('sample.column.status') },
  { key: 'owner', label: t('sample.column.owner') },
  { key: 'createdAt', label: t('sample.column.createdAt'), type: 'datetime' },
  { key: 'updatedAt', label: t('sample.detail.updatedAt'), type: 'datetime' },
  { key: 'remark', label: t('sample.detail.remark'), type: 'longtext', crossColumn: true, collapse: true },
])

const data = computed<Record<string, unknown>>(() => (record.value === null ? {} : { ...record.value }))

/** 加载详情。 */
async function load(): Promise<void> {
  state.value = 'loading'
  try {
    record.value = await sampleService.get(id.value)
    state.value = 'ready'
  } catch {
    record.value = null
    state.value = 'error'
  }
}

/** 返回列表。 */
function back(): void {
  void router.push({ name: 'SampleList' })
}

/** 打开编辑表单。 */
function edit(): void {
  void router.push({ name: 'SampleForm', params: { id: id.value } })
}

/** 删除并返回列表。 */
async function remove(): Promise<void> {
  await sampleService.remove(id.value)
  back()
}

onMounted(load)
</script>

<template>
  <page-container :title="t('sample.detail.title')" show-back @back="back">
    <template #extra>
      <el-button v-if="runtime.canEdit && state === 'ready'" type="primary" data-test="sample-detail-edit" @click="edit">
        {{ t('sample.detail.edit') }}
      </el-button>
      <el-popconfirm v-if="runtime.canEdit && state === 'ready'" :title="t('sample.list.removeConfirm')" @confirm="remove">
        <template #reference>
          <el-button type="danger" data-test="sample-detail-remove">{{ t('sample.list.remove') }}</el-button>
        </template>
      </el-popconfirm>
    </template>
    <section-container>
      <status-container
        :status="state"
        :delay="0"
        :retryable="true"
        :error-text="t('sample.detail.notFound')"
        @retry="load"
      >
        <description-list :items="items" :data="data" :columns="2" plain-enabled>
          <template #item-priority="{ value }">
            <sample-priority-tag :value="value as SampleRecord['priority']" />
          </template>
          <template #item-status="{ value }">
            <sample-status-tag :value="value as SampleRecord['status']" />
          </template>
        </description-list>
      </status-container>
    </section-container>
  </page-container>
</template>
