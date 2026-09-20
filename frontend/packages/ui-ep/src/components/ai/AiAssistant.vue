<script setup lang="ts">
// AI 助手容器（08_10）：自 interaction/ 迁入 + 真实实现。四模式页签、会话列表、对话面板（独立分包）、
// 输入区与自动执行二次确认装配；对外契约保持 08_01_03 冻结形状，仅向后兼容新增可选 Props / 事件 / 插槽。
import { defineAsyncComponent, ref, watch } from 'vue'

import AiActionConfirm from './AiActionConfirm.vue'
import AiComposer from './AiComposer.vue'
import AiSessionList from './AiSessionList.vue'
import { useBaseAiAssistant } from '../../composables/useBaseAiAssistant'
import { useBaseSubscription } from '../../composables/useBaseSubscription'
import type {
  AiJobs,
  AiMessage,
  AiMode,
  AiPendingAction,
  AiSession,
  AiStreamAdapter,
  ChartEngineAdapter,
  ReportDataset,
} from '@bms/core'

// 对话面板独立分包（流式输出 / 消息渲染）。
const AiChatPanel = defineAsyncComponent(() => import('./AiChatPanel.vue'))

/** 助手模式集合。 */
const MODES: AiMode[] = ['ask', 'report', 'approval', 'doc_qa']

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
  /** 取数处理函数（注入后驱动真实编排）。 */
  jobs?: AiJobs
  /** 流式适配器（注入后驱动真实编排）。 */
  stream?: AiStreamAdapter
  /** 权限码集合（驱动 ai:chat / ai:manage 门控）。 */
  accessCodes?: string[]
  /** 待确认动作。 */
  pendingAction?: AiPendingAction
  /** 错误码。 */
  errorCode?: number
  /** 错误文案。 */
  errorText?: string
  /** 快捷问题。 */
  shortcuts?: string[]
  /** 图表引擎工厂（测试注入）。 */
  engineFactory?: () => Promise<ChartEngineAdapter>
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
  jobs: undefined,
  stream: undefined,
  accessCodes: undefined,
  pendingAction: undefined,
  errorCode: undefined,
  errorText: '',
  shortcuts: () => [],
  engineFactory: undefined,
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
  'confirm-action': [sessionId: string]
  'revoke-action': [sessionId: string]
  retry: []
  loaded: []
  failed: [payload: { message: string; code?: number }]
  'session-created': [sessionId: string]
  'messages-loaded': [sessionId: string]
  'action-confirmed': [payload: { actionId: string }]
  'action-revoked': [payload: { actionId: string }]
}>()

const base = useBaseAiAssistant({
  ready: props.ready,
  mode: props.mode,
  sessions: props.sessions,
  messages: props.messages,
  autoExecute: props.autoExecute,
  autoApprove: props.autoApprove,
  jobs: props.jobs,
  stream: props.stream,
  accessCodes: props.accessCodes,
})

/** 是否注入真实通路（注入后才驱动能力基类编排）。 */
const injected = ref(props.jobs !== undefined || props.stream !== undefined)

const content = ref('')
const datasetId = ref('')
const streamBuffer = ref('')
const confirmVisible = ref(false)

const { topics, subscribe } = useBaseSubscription()

watch(
  () => props.ready,
  (next) => {
    base.setReady(next)
    if (next && !injected.value) {
      subscribe('ai.stream', (payload) => {
        streamBuffer.value += String(payload)
      })
    }
  },
  { immediate: true },
)
watch(
  () => props.mode,
  (next) => base.setMode(next),
)
watch(
  () => props.sessions,
  (next) => base.setSessions(next ?? []),
  { immediate: true },
)
watch(
  () => props.messages,
  (next) => base.setMessages(next ?? []),
  { immediate: true },
)
watch(
  () => props.autoExecute,
  (next) => base.setAutoExecute(next),
)
watch(
  () => props.autoApprove,
  (next) => base.setAutoApprove(next),
)
watch(
  () => props.accessCodes,
  (next) => {
    if (next !== undefined) {
      base.setAccessCodes(next)
    }
  },
  { immediate: true },
)
watch(
  () => props.jobs,
  (next) => {
    if (next !== undefined) {
      base.setJobs(next)
    }
    injected.value = next !== undefined || props.stream !== undefined
  },
)
watch(
  () => props.pendingAction,
  (next) => {
    base.setPendingAction(next)
    if (next !== undefined) {
      confirmVisible.value = true
    }
  },
  { immediate: true },
)
watch(
  () => base.errorMessage.value,
  (next) => {
    if (next !== '' && base.errorCode.value !== undefined) {
      emit('failed', { message: next, code: base.errorCode.value })
    }
  },
)

/** 切换模式。 */
function switchMode(mode: AiMode): void {
  if (injected.value) {
    base.setMode(mode)
  }
  emit('update:mode', mode)
}

/** 新建会话。 */
function newSession(): void {
  emit('new-session')
  if (!injected.value) {
    return
  }
  const session = base.newSession(props.mode)
  emit('session-created', session.id)
}

/** 切换会话。 */
function selectSession(id: string): void {
  emit('select-session', id)
  if (injected.value) {
    base.selectSession(id)
    void base.loadMessages(id).then((messages) => {
      if (messages !== undefined) {
        emit('messages-loaded', id)
      }
    })
  }
}

/** 删除会话。 */
function removeSession(id: string): void {
  emit('remove-session', id)
  if (injected.value) {
    void base.removeSession(id)
  }
}

/** 发送消息。 */
function send(): void {
  if (base.degraded.value || content.value.trim() === '') {
    return
  }
  emit('send', {
    mode: props.mode,
    content: content.value,
    datasetId: datasetId.value || undefined,
    sessionId: props.activeSessionId || undefined,
  })
  if (injected.value) {
    void base.send({ content: content.value, datasetId: datasetId.value || undefined })
  }
  content.value = ''
}

/** 停止流式。 */
function stop(): void {
  emit('stop')
  if (injected.value) {
    void base.stop()
  }
}

/** 重新生成。 */
function regenerate(messageId: string): void {
  emit('regenerate', messageId)
  if (injected.value) {
    void base.regenerate(messageId)
  }
}

/** 附件按钮（附件选择由宿主提供）。 */
function attach(): void {
  emit('attach', [])
}

/** 确认执行（保留既有语义；注入时驱动能力基类）。 */
function confirmAction(): void {
  emit('confirm-action', props.activeSessionId)
  if (injected.value) {
    const actionId = props.pendingAction?.id
    void base.confirmAction(actionId).then((ok) => {
      if (ok && actionId !== undefined) {
        emit('action-confirmed', { actionId })
      }
    })
  }
}

/** 撤销动作。 */
function revokeAction(): void {
  emit('revoke-action', props.activeSessionId)
  if (injected.value) {
    const actionId = props.pendingAction?.id
    void base.revokeAction(actionId).then((ok) => {
      if (ok && actionId !== undefined) {
        emit('action-revoked', { actionId })
      }
    })
  }
}

/** 确认件回调。 */
function onActionConfirm(payload: { actionId: string }): void {
  if (injected.value) {
    void base.confirmAction(payload.actionId).then((ok) => {
      if (ok) {
        emit('action-confirmed', payload)
      }
    })
  }
}

/** 确认件撤销回调。 */
function onActionRevoke(payload: { actionId: string }): void {
  if (injected.value) {
    void base.revokeAction(payload.actionId).then((ok) => {
      if (ok) {
        emit('action-revoked', payload)
      }
    })
  }
}
</script>

<template>
  <div
    class="bms-ai-assistant"
    data-test="ai-assistant"
    data-subpackage-host="ai"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-ai-assistant__modes" data-test="modes">
          <button
            v-for="item in MODES"
            :key="item"
            type="button"
            :data-test="`mode-${item}`"
            :data-active="mode === item || undefined"
            @click="switchMode(item)"
          >
            {{ item }}
          </button>
          <span data-test="topics">{{ topics.join(',') }}</span>
          <span v-if="!base.canChat.value" class="bms-ai-assistant__hint" data-test="readonly-hint">无 AI 对话权限</span>
          <span
            v-if="base.errorMessage.value !== '' || errorText !== ''"
            class="bms-ai-assistant__hint is-error"
            data-test="error-hint"
          >
            {{ base.errorMessage.value || errorText }}
          </span>
        </div>

        <div class="bms-ai-assistant__body">
          <div class="bms-ai-assistant__sessions" data-test="sessions">
            <slot name="sessions">
              <slot name="session-list" :sessions="sessions">
                <AiSessionList
                  :sessions="sessions"
                  :active-session-id="activeSessionId"
                  :disabled="base.degraded.value"
                  @select="selectSession"
                  @create="newSession"
                  @remove="removeSession"
                />
              </slot>
            </slot>
          </div>

          <div class="bms-ai-assistant__chat" data-test="chat">
            <component
              :is="AiChatPanel"
              :messages="messages"
              :streaming="streaming"
              :ready="ready"
              :mode="mode"
              :datasets="datasets"
              :engine-factory="engineFactory"
              @regenerate="regenerate"
              @retry="emit('retry')"
            />
          </div>
        </div>

        <div class="bms-ai-assistant__input" data-test="input-area">
          <slot name="input" :send="send" :stop="stop">
            <slot name="composer">
              <AiComposer
                v-model="content"
                v-model:dataset-id="datasetId"
                :mode="mode"
                :streaming="streaming"
                :disabled="base.degraded.value"
                :ready="ready"
                :datasets="datasets"
                :files="files"
                :shortcuts="shortcuts"
                :error-text="errorText"
                @send="send"
                @stop="stop"
                @attach="attach"
                @retry="emit('retry')"
              />
            </slot>
          </slot>
          <button
            v-if="autoExecute"
            type="button"
            data-test="confirm-action"
            @click="confirmAction"
          >
            确认执行
          </button>
          <button v-if="autoExecute" type="button" data-test="revoke-action" @click="revokeAction">撤销</button>
          <span v-if="streamBuffer" data-test="stream-buffer">{{ streamBuffer }}</span>
        </div>

        <slot name="action-confirm">
          <AiActionConfirm
            v-model="confirmVisible"
            :action="pendingAction"
            :ready="base.canAutoExecute.value"
            :loading="base.phase.value === 'loading'"
            @confirm="onActionConfirm"
            @revoke="onActionRevoke"
          />
        </slot>
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-ai-assistant {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--bms-color-border, #ebeef5);
  border-radius: 6px;
}
.bms-ai-assistant__modes {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--bms-color-border, #ebeef5);
}
.bms-ai-assistant__modes button {
  padding: 2px 10px;
  cursor: pointer;
  background: none;
  border: 1px solid transparent;
  border-radius: 12px;
}
.bms-ai-assistant__modes button[data-active] {
  color: var(--bms-color-primary, #409eff);
  background: var(--bms-ai-citation-bg, #ecf5ff);
  border-color: var(--bms-color-primary, #409eff);
}
.bms-ai-assistant__hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--bms-color-text-secondary, #909399);
}
.bms-ai-assistant__hint.is-error {
  color: var(--bms-color-danger, #f56c6c);
}
.bms-ai-assistant__body {  display: flex;
  flex: 1 1 auto;
  min-height: 320px;
}
.bms-ai-assistant__chat {
  flex: 1 1 auto;
  min-width: 0;
  overflow: auto;
}
.bms-ai-assistant__input {
  border-top: 1px solid var(--bms-color-border, #ebeef5);
}
</style>
