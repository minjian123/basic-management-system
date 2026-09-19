<script setup lang="ts">
// 数据集详情面板（08_09_01）：当前数据集字段清单 / 参数 / 样例数据预览（停用提示）。
import { computed, watch } from 'vue'

import type { ReportDataset } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 当前数据集（缺省取清单首项）。 */
  dataset?: ReportDataset
  /** 数据集清单（用于回退查找）。 */
  datasets?: ReportDataset[]
  /** 当前数据集标识。 */
  datasetId?: string
  /** 只读。 */
  readOnly?: boolean
  /** 预览列。 */
  previewColumns?: { name: string; type: string }[]
  /** 预览行。 */
  previewRows?: Record<string, unknown>[]
  /** 预览加载中。 */
  previewLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  dataset: undefined,
  datasets: () => [],
  datasetId: '',
  readOnly: false,
  previewColumns: () => [],
  previewRows: () => [],
  previewLoading: false,
})

const emit = defineEmits<{
  preview: [payload: { datasetId: string; params?: Record<string, unknown> }]
  'select-field': [payload: { datasetId: string; field: { name: string; type: string } }]
}>()

/** 当前数据集。 */
const current = computed(() => props.dataset ?? props.datasets.find((entry) => entry.id === props.datasetId))

/** 当前字段清单。 */
const fields = computed(() => current.value?.fields ?? [])

/** 数据状态（空 / 就绪）。 */
const { state, setState } = useBaseDataState()
watch(
  () => fields.value.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/** 触发预览取数。 */
function requestPreview(): void {
  if (props.datasetId !== '') {
    emit('preview', { datasetId: props.datasetId })
  }
}
</script>

<template>
  <div class="bms-report-dataset" data-test="dataset-detail" :data-state="state" :data-readonly="readOnly">
    <p class="bms-report-dataset__title">{{ current?.name ?? '未选择数据集' }}</p>
    <p v-if="current?.status === 'disabled'" data-test="dataset-disabled-hint">该数据集已停用，不可选</p>

    <div v-if="fields.length > 0" class="bms-report-dataset__fields">
      <p>字段清单</p>
      <button
        v-for="field in fields"
        :key="field.name"
        type="button"
        :data-test="`field-${field.name}`"
        @click="emit('select-field', { datasetId, field })"
      >
        {{ field.name }} · {{ field.type }}
      </button>
    </div>

    <div v-if="(current?.params ?? []).length > 0" class="bms-report-dataset__params" data-test="dataset-params">
      <p>参数</p>
      <span v-for="param in current?.params ?? []" :key="param.name">{{ param.label ?? param.name }}</span>
    </div>

    <div class="bms-report-dataset__preview">
      <button type="button" data-test="preview-trigger" :disabled="readOnly || datasetId === ''" @click="requestPreview">
        数据预览
      </button>
      <p v-if="previewLoading" data-test="preview-loading">加载中…</p>
      <table v-else-if="previewColumns.length > 0" data-test="preview-table">
        <thead>
          <tr>
            <th v-for="column in previewColumns" :key="column.name">{{ column.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in previewRows" :key="index">
            <td v-for="column in previewColumns" :key="column.name">{{ row[column.name] }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else data-test="preview-empty">暂无预览数据</p>
    </div>
  </div>
</template>

<style scoped>
.bms-report-dataset {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  font-size: 13px;
}
.bms-report-dataset__fields {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.bms-report-dataset table {
  width: 100%;
  border-collapse: collapse;
}
.bms-report-dataset th,
.bms-report-dataset td {
  border: 1px solid var(--bms-color-border, #dcdfe6);
  padding: 2px 4px;
  text-align: left;
}
</style>
