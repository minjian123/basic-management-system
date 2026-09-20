<script setup lang="ts">
// AI 输入区（08_10）：多行输入（回车发送、Shift+回车换行）/ 发送与停止 / 数据集选择 / 附件 / 字数与超长提示 / 快捷问题。
import { AI_PROMPT_MAX, countAiCodePoints, modeLabel, type AiMode } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 模式。 */
  mode?: AiMode
  /** 输入内容（v-model）。 */
  modelValue?: string
  /** 是否流式输出中。 */
  streaming?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 数据集（智能问数）。 */
  datasets?: { id: string; name: string }[]
  /** 当前数据集标识。 */
  datasetId?: string
  /** 附件（文档问答）。 */
  files?: { id: string; name: string }[]
  /** 展示附件按钮（缺省 true）。 */
  showAttach?: boolean
  /** 输入占位。 */
  placeholder?: string
  /** 字数上限（缺省 `AI_PROMPT_MAX`）。 */
  maxLength?: number
  /** 快捷问题。 */
  shortcuts?: string[]
  /** 错误提示。 */
  errorText?: string
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'ask',
  modelValue: '',
  streaming: false,
  disabled: false,
  ready: true,
  datasets: () => [],
  datasetId: '',
  files: () => [],
  showAttach: true,
  placeholder: '输入问题，回车发送，Shift+回车换行',
  maxLength: AI_PROMPT_MAX,
  shortcuts: () => [],
  errorText: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:datasetId': [datasetId: string]
  send: []
  stop: []
  attach: [fileIds: string[]]
  shortcut: [text: string]
  retry: []
}>()

const { state, setState } = useBaseDataState()

/** 已输入码点数。 */
const count = computed(() => countAiCodePoints(props.modelValue))

/** 是否超长。 */
const tooLong = computed(() => count.value > props.maxLength)

/** 是否可发送。 */
const canSend = computed(
  () => props.ready && !props.disabled && !props.streaming && props.modelValue.trim() !== '' && !tooLong.value,
)

watch(
  () => [tooLong.value, props.disabled, props.ready, props.errorText] as const,
  ([over, disabled, ready, errorText]) => {
    if (!ready) {
      setState('empty')
    } else if (disabled || over || errorText !== '') {
      setState('error')
    } else {
      setState('ready')
    }
  },
  { immediate: true },
)

/** 回车发送（Shift+回车换行）。 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }
  event.preventDefault()
  if (canSend.value) {
    emit('send')
  }
}
</script>

<template>
  <div class="bms-ai-composer" data-test="ai-composer" :data-state="state" :data-streaming="streaming || undefined">
    <div v-if="shortcuts.length > 0" class="bms-ai-composer__shortcuts" data-test="composer-shortcuts">
      <button v-for="(item, index) in shortcuts" :key="index" type="button" @click="emit('shortcut', item)">
        {{ item }}
      </button>
    </div>
    <textarea
      class="bms-ai-composer__input"
      data-test="input"
      :value="modelValue"
      :disabled="disabled"
      :placeholder="placeholder"
      rows="3"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      @keydown="handleKeydown"
    />
    <div class="bms-ai-composer__toolbar">
      <slot name="toolbar">
        <select
          v-if="mode === 'report'"
          class="bms-ai-composer__dataset"
          data-test="dataset-select"
          :disabled="disabled"
          :value="datasetId"
          @change="emit('update:datasetId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">选择数据集</option>
          <option v-for="item in datasets" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <button
          v-if="showAttach"
          type="button"
          data-test="attach"
          :disabled="disabled"
          @click="emit('attach', [])"
        >
          附件
        </button>
        <span class="bms-ai-composer__mode" data-test="composer-mode">{{ modeLabel(mode) }}</span>
        <span class="bms-ai-composer__count" data-test="composer-count" :data-over="tooLong || undefined">
          {{ count }}/{{ maxLength }}
        </span>
        <button
          type="button"
          class="bms-ai-composer__send"
          data-test="send"
          :disabled="!canSend"
          @click="emit('send')"
        >
          发送
        </button>
        <button
          type="button"
          class="bms-ai-composer__stop"
          data-test="stop"
          :disabled="!streaming"
          @click="emit('stop')"
        >
          停止
        </button>
      </slot>
    </div>
    <div v-if="tooLong || errorText !== ''" class="bms-ai-composer__error" data-test="composer-error">
      <span>{{ tooLong ? `问题超过 ${maxLength} 字` : errorText }}</span>
      <button type="button" data-test="composer-retry" @click="emit('retry')">重试</button>
    </div>
    <slot name="hint" />
  </div>
</template>

<style scoped>
.bms-ai-composer {
  padding: 8px 12px;
  border-top: 1px solid var(--bms-color-border, #ebeef5);
}
.bms-ai-composer__shortcuts {
  display: flex;
  gap: 6px;
  padding-bottom: 6px;
  overflow: auto;
}
.bms-ai-composer__shortcuts button {
  padding: 2px 8px;
  color: var(--bms-color-primary, #409eff);
  white-space: nowrap;
  cursor: pointer;
  background: var(--bms-ai-citation-bg, #ecf5ff);
  border: none;
  border-radius: 10px;
}
.bms-ai-composer__input {
  box-sizing: border-box;
  width: 100%;
  padding: 8px;
  font-family: inherit;
  color: var(--bms-color-text, #303133);
  resize: vertical;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: 4px;
}
.bms-ai-composer__toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
  font-size: 12px;
}
.bms-ai-composer__mode {
  color: var(--bms-color-text-secondary, #909399);
}
.bms-ai-composer__count {
  margin-left: auto;
  color: var(--bms-color-text-secondary, #909399);
}
.bms-ai-composer__count[data-over] {
  color: var(--bms-color-danger, #f56c6c);
}
.bms-ai-composer__send,
.bms-ai-composer__stop {
  padding: 4px 16px;
  color: #fff;
  cursor: pointer;
  background: var(--bms-color-primary, #409eff);
  border: none;
  border-radius: 4px;
}
.bms-ai-composer__send:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.bms-ai-composer__stop {
  background: var(--bms-color-danger, #f56c6c);
}
.bms-ai-composer__error {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
  font-size: 12px;
  color: var(--bms-color-danger, #f56c6c);
}
.bms-ai-composer__error button {
  color: var(--bms-color-primary, #409eff);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
