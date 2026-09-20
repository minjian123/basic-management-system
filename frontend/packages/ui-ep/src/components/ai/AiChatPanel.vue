<script setup lang="ts">
// AI 对话面板（08_10）：由 AiAssistant 异步懒加载的独立分包入口（data-subpackage="ai"）；
// 消息流渲染（Markdown / 代码 / 图表 / 表格 / 引用 / 风险 / 审计）、流式态与空 / 错误态。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import AiMessageItem from './AiMessageItem.vue'
import type { AiMessage, ChartEngineAdapter } from '@bms/core'

interface Props {
  /** 消息流。 */
  messages?: AiMessage[]
  /** 当前是否流式输出中。 */
  streaming?: boolean
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 当前模式。 */
  mode?: string
  /** 数据集。 */
  datasets?: unknown[]
  /** 空态文案。 */
  emptyText?: string
  /** 降级文案。 */
  degradeText?: string
  /** 流式失败态。 */
  error?: boolean
  /** 错误文案。 */
  errorText?: string
  /** 图表引擎工厂（测试注入）。 */
  engineFactory?: () => Promise<ChartEngineAdapter>
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
  streaming: false,
  ready: true,
  mode: 'ask',
  datasets: () => [],
  emptyText: '暂无消息（真实实现接入流式对话）',
  degradeText: 'AI 助手未就绪（占位）',
  error: false,
  errorText: 'AI 请求失败',
  engineFactory: undefined,
})

const emit = defineEmits<{
  regenerate: [messageId: string]
  retry: []
  'citation-click': [{ citation: { type: string; title: string; id: string } }]
  copy: [{ messageId: string }]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => [props.messages.length, props.streaming, props.error, props.ready] as const,
  ([count, streaming, error, ready]) => {
    if (!ready) {
      setState('empty')
      return
    }
    setState(error ? 'error' : streaming ? 'loading' : count > 0 ? 'ready' : 'empty')
  },
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-ai-chat-panel"
    data-test="chat-panel"
    data-subpackage="ai"
    :data-state="state"
    :data-streaming="streaming || undefined"
    :data-degraded="ready ? undefined : true"
  >
    <div v-if="!ready" class="bms-ai-chat-panel__placeholder" data-test="chat-degrade">{{ degradeText }}</div>
    <template v-else>
      <div v-if="error" class="bms-ai-chat-panel__error" data-test="chat-error">
        <span>{{ errorText }}</span>
        <button type="button" data-test="chat-retry" @click="emit('retry')">重试</button>
      </div>
      <div class="bms-ai-chat-panel__list" data-test="message-list">
        <div v-for="message in messages" :key="message.id" :data-test="`message-${message.id}`">
          <slot name="message" :message="message">
            <AiMessageItem
              :message="message"
              :mode="mode"
              :datasets="datasets"
              :streaming="streaming"
              :engine-factory="engineFactory"
              @regenerate="emit('regenerate', $event)"
              @citation-click="emit('citation-click', $event)"
              @copy="emit('copy', $event)"
            />
          </slot>
        </div>
      </div>
      <div v-if="messages.length === 0 && !error" class="bms-ai-chat-panel__empty" data-test="chat-empty">
        <slot name="empty">{{ emptyText }}</slot>
      </div>
    </template>
    <slot name="footer" />
  </div>
</template>

<style scoped>
.bms-ai-chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  overflow: auto;
}
.bms-ai-chat-panel__list {
  display: flex;
  flex-direction: column;
}
.bms-ai-chat-panel__empty,
.bms-ai-chat-panel__placeholder {
  padding: 32px;
  color: var(--bms-color-text-secondary);
  text-align: center;
}
.bms-ai-chat-panel__error {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 8px;
  color: var(--bms-color-danger);
  background: var(--bms-ai-risk-bg);
  border-radius: 4px;
}
.bms-ai-chat-panel__error button {
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
