<script setup lang="ts">
// 导入对话框主体（占位，08_01_02）：由 ImportDialog 异步懒加载的独立分包入口，真实实现（08_05）承载上传与错误行报告。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { ImportResult, ImportStep } from './ImportDialog.vue'

interface Props {
  /** 当前步骤。 */
  step?: ImportStep
  /** 导入结果。 */
  result?: ImportResult | null
  /** 上传进度（0 ~ 100）。 */
  progress?: number
  /** 文件级错误文案。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  step: 'select',
  result: null,
  progress: 0,
  errorMessage: '',
})

const { state, setState } = useBaseDataState()
watch(
  () => props.step,
  (step) => {
    setState(step === 'uploading' ? 'loading' : step === 'result' ? 'ready' : 'empty')
  },
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-import-dialog-body"
    data-test="import-body"
    data-subpackage="import"
    :data-step="step"
    :data-state="state"
  >
    <p v-if="step === 'select'" data-test="body-note">选择文件后提交（占位，真实实现接入上传与解析）</p>
    <div v-else-if="step === 'uploading'" class="bms-import-dialog-body__progress" data-test="upload-progress">
      <progress :value="progress" max="100" />
      <span data-test="progress-text">解析校验中… {{ progress }}%</span>
    </div>
    <div v-else data-test="result">
      <p data-test="import-summary">
        总 {{ result?.total ?? 0 }} / 成功 {{ result?.successCount ?? 0 }} / 失败 {{ result?.failCount ?? 0 }}
      </p>
      <p v-if="errorMessage" data-test="body-error">{{ errorMessage }}</p>
      <div
        v-for="item in result?.errors ?? []"
        :key="item.row"
        :data-test="`error-row-${item.row}`"
        :data-column="item.column || undefined"
      >
        第 {{ item.row }} 行：{{ item.message }}
      </div>
    </div>
  </div>
</template>
