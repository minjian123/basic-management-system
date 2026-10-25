<script setup lang="ts">
// 导入对话框主体（08_05）：由 ImportDialog 异步懒加载的独立分包入口；三步内容（选文件 → 上传解析进度 → 结果与错误行报告）。
import { resolveImportSummary, type ImportPhase, type ImportResult, type ImportStep } from '@bms/core'
import { ElProgress } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import ImportErrorReport from './ImportErrorReport.vue'

interface Props {
  /** 当前步骤。 */
  step?: ImportStep
  /** 当前阶段（上传中 / 解析中）。 */
  phase?: ImportPhase
  /** 上传进度（0 ~ 100）。 */
  progress?: number
  /** 导入结果。 */
  result?: ImportResult | undefined
  /** 文件级错误文案。 */
  errorMessage?: string
  /** 错误行页码。 */
  errorPage?: number
  /** 错误行每页行数。 */
  errorPageSize?: number
  /** 业务中文名。 */
  bizName?: string
  /** 是否进行中（禁止关闭）。 */
  busy?: boolean
  /** 是否下载中。 */
  downloading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  step: 'select',
  phase: 'idle',
  progress: 0,
  result: undefined,
  errorMessage: '',
  errorPage: 1,
  errorPageSize: 20,
  bizName: '',
  busy: false,
  downloading: false,
})

const emit = defineEmits<{
  'update:error-page': [page: number]
  'download-errors': []
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.step,
  (step) => {
    setState(step === 'uploading' ? 'loading' : step === 'result' ? 'ready' : 'empty')
  },
  { immediate: true },
)

/** 结果汇总态（空数据 / 全部成功 / 部分失败）。 */
const summary = computed(() =>
  resolveImportSummary(props.result ?? { total: 0, successCount: 0, failCount: 0, errors: [] }),
)
/** 是否文件级错误（整体拒绝、不展示错误行表）。 */
const fileLevelError = computed(() => props.phase === 'failed' && (props.result?.errors.length ?? 0) === 0)
/** 解析阶段文案。 */
const phaseText = computed(() => (props.phase === 'parsing' ? '解析校验中…' : '上传中…'))
</script>

<template>
  <div
    class="bms-import-dialog-body"
    data-test="import-body"
    data-subpackage="import"
    :data-step="step"
    :data-state="state"
    :data-phase="phase"
  >
    <p v-if="step === 'select'" class="bms-import-dialog-body__note" data-test="body-note">
      选择文件后提交（仅做类型 / 大小 / 空文件快速校验，模板列核对与行级校验由后端完成）
    </p>

    <div v-else-if="step === 'uploading'" class="bms-import-dialog-body__progress" data-test="upload-progress">
      <p class="bms-import-dialog-body__phase" data-test="progress-text">{{ phaseText }} {{ progress }}%</p>
      <el-progress :percentage="progress" :indeterminate="phase === 'parsing'" :stroke-width="8" />
      <p class="bms-import-dialog-body__tip">解析校验中请勿关闭对话框</p>
    </div>

    <div v-else class="bms-import-dialog-body__result" data-test="result">
      <ImportErrorReport
        v-if="!fileLevelError"
        :result="result"
        :page="errorPage"
        :page-size="errorPageSize"
        :biz-name="bizName"
        :downloading="downloading"
        @update:page="emit('update:error-page', $event)"
        @download="emit('download-errors')"
      >
        <template #empty>全部导入成功</template>
      </ImportErrorReport>

      <p v-if="summary === 'warning' && !fileLevelError" class="bms-import-dialog-body__hint" data-test="body-hint">
        请按行号修正后重新导入
      </p>

      <slot name="error-report" />

      <p v-if="errorMessage" class="bms-import-dialog-body__error" data-test="body-error">{{ errorMessage }}</p>

      <slot name="empty" />
    </div>
  </div>
</template>

<style scoped>
.bms-import-dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-import-dialog-body__note {
  margin: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-sm);
}

.bms-import-dialog-body__progress {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-import-dialog-body__phase {
  margin: 0;
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.bms-import-dialog-body__tip {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-import-dialog-body__result {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-import-dialog-body__hint {
  margin: 0;
  padding: var(--bms-space-2);
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}

/* 文件级错误文案与字段错误位同口径（全局共享类）。 */
.bms-import-dialog-body__error {
  margin: 0;
  color: var(--bms-field-error-color);
  font-size: var(--bms-font-size-xs);
}
</style>
