<script setup lang="ts">
// AI 对话面板（占位，08_01_03）：由 AiAssistant 异步懒加载的独立分包入口，真实实现（08_10）承载流式输出与消息渲染。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { AiMessage } from './AiAssistant.vue'

interface Props {
  /** 消息流。 */
  messages?: AiMessage[]
  /** 当前是否流式输出中。 */
  streaming?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
  streaming: false,
})

const emit = defineEmits<{
  regenerate: [messageId: string]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => [props.messages.length, props.streaming] as const,
  ([count, streaming]) => setState(streaming ? 'loading' : count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-ai-chat-panel"
    data-test="chat-panel"
    data-subpackage="ai"
    :data-state="state"
    :data-streaming="streaming"
  >
    <p v-if="messages.length === 0" data-test="chat-empty">暂无消息（占位，真实实现接入流式对话）</p>
    <div
      v-for="message in messages"
      :key="message.id"
      class="bms-ai-chat-panel__message"
      :data-test="`message-${message.id}`"
      :data-role="message.role"
      :data-status="message.status"
    >
      <p data-test="message-content">{{ message.content }}</p>
      <span v-if="message.result" data-test="message-result">结果：{{ message.result.kind }}</span>
      <span v-if="message.auditId" data-test="message-audit">审计 {{ message.auditId }}</span>
      <div v-for="(cite, index) in message.citations ?? []" :key="index" data-test="message-citation">
        引用：{{ cite.title }}
      </div>
      <div v-for="(risk, index) in message.risks ?? []" :key="index" data-test="message-risk">风险：{{ risk }}</div>
      <button
        v-if="message.role === 'assistant' && (message.status === 'error' || message.status === 'stopped')"
        type="button"
        data-test="regenerate"
        @click="emit('regenerate', message.id)"
      >
        重新生成
      </button>
    </div>
  </div>
</template>
