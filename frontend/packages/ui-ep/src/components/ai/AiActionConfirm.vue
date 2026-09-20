<script setup lang="ts">
// AI 自动执行二次确认（08_10）：展示待确认内容 → 强制二次确认 → 执行；已执行且可撤销时提供撤销。
import { canRevokeAction, requiresConfirm, type AiPendingAction } from '@bms/core'
import { ElDialog } from 'element-plus'
import { computed } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 显隐（v-model）。 */
  modelValue: boolean
  /** 待确认动作。 */
  action?: AiPendingAction | null
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 提交中。 */
  loading?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  action: null,
  ready: true,
  loading: false,
  degradeText: '自动执行未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [{ actionId: string }]
  revoke: [{ actionId: string }]
  close: []
}>()

const { state, setState } = useBaseDataState()

/** 是否可确认。 */
const confirmable = computed(() => (props.action ? requiresConfirm(props.action) : false))

/** 是否可撤销。 */
const revocable = computed(() => (props.action ? canRevokeAction(props.action) : false))

/** 状态文案。 */
const stateLabel = computed(() => {
  const value = props.action?.state
  if (value === 'pending') {
    return '待确认'
  }
  if (value === 'confirmed') {
    return '已确认'
  }
  if (value === 'executed') {
    return '已执行'
  }
  if (value === 'revoked') {
    return '已撤销'
  }
  if (value === 'failed') {
    return '执行失败'
  }
  return ''
})

setState(props.ready ? 'ready' : 'empty')
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="自动执行确认"
    width="480px"
    data-test="ai-action-confirm"
    :data-state="state"
    :data-ready="ready || undefined"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <div v-if="!ready" class="bms-ai-action__placeholder" data-test="action-placeholder">{{ degradeText }}</div>
    <div v-else-if="action" class="bms-ai-action">
      <h4 class="bms-ai-action__title" data-test="action-title">{{ action.title }}</h4>
      <p v-if="action.summary" class="bms-ai-action__summary" data-test="action-summary">{{ action.summary }}</p>
      <pre v-if="action.content" class="bms-ai-action__content" data-test="action-content">{{ action.content }}</pre>
      <span class="bms-ai-action__state" data-test="action-state">{{ stateLabel }}</span>
    </div>
    <template #footer>
      <slot name="footer" :action="action">
        <button
          v-if="confirmable"
          type="button"
          class="bms-ai-action__confirm"
          data-test="action-confirm"
          :disabled="loading"
          @click="action && emit('confirm', { actionId: action.id })"
        >
          确认执行
        </button>
        <button
          v-if="revocable"
          type="button"
          class="bms-ai-action__revoke"
          data-test="action-revoke"
          :disabled="loading"
          @click="action && emit('revoke', { actionId: action.id })"
        >
          撤销
        </button>
        <button type="button" data-test="action-close" @click="emit('update:modelValue', false)">关闭</button>
      </slot>
    </template>
  </el-dialog>
</template>

<style scoped>
.bms-ai-action__title {
  margin: 0 0 8px;
}
.bms-ai-action__summary {
  margin: 0 0 8px;
  color: var(--bms-color-text-secondary, #909399);
}
.bms-ai-action__content {
  padding: 8px 12px;
  overflow: auto;
  white-space: pre-wrap;
  background: var(--bms-ai-bubble-assistant-bg, #f5f7fa);
  border-radius: 4px;
}
.bms-ai-action__state {
  display: inline-block;
  margin-top: 8px;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
  color: var(--bms-color-warning, #e6a23c);
  background: var(--bms-ai-risk-bg, #fdf6ec);
  border-radius: 10px;
}
.bms-ai-action__confirm {
  margin-right: 8px;
  padding: 4px 16px;
  color: #fff;
  cursor: pointer;
  background: var(--bms-color-primary, #409eff);
  border: none;
  border-radius: 4px;
}
.bms-ai-action__revoke {
  margin-right: 8px;
  padding: 4px 16px;
  color: var(--bms-color-danger, #f56c6c);
  cursor: pointer;
  background: none;
  border: 1px solid var(--bms-color-danger, #f56c6c);
  border-radius: 4px;
}
.bms-ai-action__placeholder {
  padding: 16px;
  color: var(--bms-color-text-secondary, #909399);
  text-align: center;
}
</style>
