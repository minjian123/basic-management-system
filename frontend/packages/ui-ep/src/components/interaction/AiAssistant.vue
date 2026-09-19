<script setup lang="ts">
// AI 助手（占位版，08_01_03）：契约先行冻结；数据通路未就绪时不请求、操作禁用 + 降级提示。对话面板独立分包懒加载。
import { defineAsyncComponent, ref, watch } from 'vue'

import { useBaseSubscription } from '../../composables/useBaseSubscription'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'
import type { ReportDataset } from '@bms/core'

// 对话面板独立分包（流式输出 / 消息渲染，真实实现 08_10 接入）。
const AiChatPanel = defineAsyncComponent(() => import('./AiChatPanel.vue'))

/** 助手模式。 */
export type AiMode = 'ask' | 'report' | 'approval' | 'doc_qa'

/** 消息角色。 */
export type AiRole = 'user' | 'assistant'

/** 消息状态。 */
export type AiMessageStatus = 'streaming' | 'done' | 'error' | 'stopped'

/** 引用来源。 */
export interface AiCitation {
  /** 来源类型。 */
  type: 'file' | 'article' | 'record'
  /** 标题。 */
  title: string
  /** 标识。 */
  id: string
}

/** 消息。 */
export interface AiMessage {
  /** 消息标识。 */
  id: string
  /** 角色。 */
  role: AiRole
  /** 状态。 */
  status: AiMessageStatus
  /** 文本（Markdown）。 */
  content: string
  /** 结构化结果（图表 / 表格）。 */
  result?: { kind: 'chart' | 'table'; chartType?: string; datasetId?: string; rows?: unknown[] }
  /** 引用来源。 */
  citations?: AiCitation[]
  /** 风险提示。 */
  risks?: string[]
  /** 审计记录标识。 */
  auditId?: string
}

/** 会话。 */
export interface AiSession {
  /** 会话标识。 */
  id: string
  /** 标题。 */
  title: string
  /** 模式。 */
  mode: AiMode
  /** 更新时间。 */
  updatedAt: string
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 模式。 */
  mode?: AiMode
  /** 会话列表。 */
  sessions?: AiSession[]
  /** 当前会话标识。 */
  activeSessionId?: string
  /** 消息流。 */
  messages?: AiMessage[]
  /** 是否流式输出中。 */
  streaming?: boolean
  /** 可选数据集（智能问数）。 */
  datasets?: ReportDataset[]
  /** 可选文件（文档问答）。 */
  files?: { id: string; name: string }[]
  /** 自动执行开关。 */
  autoExecute?: boolean
  /** 自动审批开关。 */
  autoApprove?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  mode: 'ask',
  sessions: () => [],
  activeSessionId: '',
  messages: () => [],
  streaming: false,
  datasets: () => [],
  files: () => [],
  autoExecute: false,
  autoApprove: false,
  degradeText: 'AI 助手未就绪（占位）',
})

const emit = defineEmits<{
  'update:mode': [mode: AiMode]
  send: [payload: { mode: AiMode; content: string; datasetId?: string; fileIds?: string[]; sessionId?: string }]
  stop: []
  regenerate: [messageId: string]
  'select-session': [sessionId: string]
  'new-session': []
  'remove-session': [sessionId: string]
  attach: [fileIds: string[]]
  'confirm-action': [actionId: string]
  'revoke-action': [actionId: string]
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { topics, subscribe } = useBaseSubscription()
const content = ref('')
const datasetId = ref('')
const streamBuffer = ref('')

watch(
  () => props.ready,
  (next) => {
    placeholder.setReady(next)
    if (next) {
      subscribe('ai.stream', (payload) => {
        streamBuffer.value += String(payload)
      })
    }
  },
  { immediate: true },
)

/** 发送消息（占位：仅透传事件，不发请求）。 */
function send(): void {
  if (placeholder.disabled.value || content.value.trim() === '') {
    return
  }
  emit('send', {
    mode: props.mode,
    content: content.value,
    datasetId: datasetId.value || undefined,
    sessionId: props.activeSessionId || undefined,
  })
  content.value = ''
}
</script>

<template>
  <div class="bms-ai-assistant" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-ai-assistant__modes" data-test="modes">
          <button
            v-for="item in (['ask', 'report', 'approval', 'doc_qa'] as AiMode[])"
            :key="item"
            type="button"
            :data-test="`mode-${item}`"
            :data-active="mode === item || undefined"
            @click="emit('update:mode', item)"
          >
            {{ item }}
          </button>
          <span data-test="topics">{{ topics.join(',') }}</span>
        </div>

        <div class="bms-ai-assistant__body">
          <div class="bms-ai-assistant__sessions" data-test="sessions">
            <slot name="sessions">
              <button type="button" data-test="new-session" @click="emit('new-session')">新建会话</button>
              <div
                v-for="session in sessions"
                :key="session.id"
                :data-test="`session-${session.id}`"
                :data-active="session.id === activeSessionId || undefined"
                @click="emit('select-session', session.id)"
              >
                {{ session.title }}
                <button type="button" :data-test="`remove-session-${session.id}`" @click.stop="emit('remove-session', session.id)">
                  删除
                </button>
              </div>
            </slot>
          </div>

          <div class="bms-ai-assistant__chat" data-test="chat">
            <component
              :is="AiChatPanel"
              :messages="messages"
              :streaming="streaming"
              @regenerate="emit('regenerate', $event)"
            />
          </div>
        </div>

        <div class="bms-ai-assistant__input" data-test="input-area">
          <textarea
            v-model="content"
            data-test="input"
            :disabled="placeholder.disabled.value"
            placeholder="输入问题（占位）"
          />
          <select v-if="mode === 'report'" v-model="datasetId" data-test="dataset-select" :disabled="placeholder.disabled.value">
            <option value="">选择数据集</option>
            <option v-for="item in datasets" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <button type="button" data-test="attach" :disabled="placeholder.disabled.value" @click="emit('attach', [])">
            附件
          </button>
          <button type="button" data-test="send" :disabled="placeholder.disabled.value" @click="send">发送</button>
          <button type="button" data-test="stop" :disabled="placeholder.disabled.value || !streaming" @click="emit('stop')">
            停止
          </button>
          <button
            v-if="autoExecute"
            type="button"
            data-test="confirm-action"
            @click="emit('confirm-action', activeSessionId)"
          >
            确认执行
          </button>
          <button
            v-if="autoExecute"
            type="button"
            data-test="revoke-action"
            @click="emit('revoke-action', activeSessionId)"
          >
            撤销
          </button>
          <span v-if="streamBuffer" data-test="stream-buffer">{{ streamBuffer }}</span>
        </div>
      </slot>
    </template>
  </div>
</template>
