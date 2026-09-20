<script setup lang="ts">
// AI 消息渲染件（08_10）：角色气泡 / Markdown（代码只读高亮）/ 图表与表格结果 / 引用来源 / 风险提示 / 审计标识。
import { citationTypeLabel, normalizeChartKind, type AiCitation, type AiMessage, type ChartEngineAdapter } from '@bms/core'
import { computed, ref, watch } from 'vue'

import ChartRenderer from '../chart/ChartRenderer.vue'
import CodeViewer from '../interaction/CodeViewer.vue'
import DataTable from '../data/DataTable.vue'
import { useBaseAiAssistant } from '../../composables/useBaseAiAssistant'
import { renderAiMarkdown, splitAiContent } from '../../utils/aiMarkdown'

interface Props {
  /** 消息。 */
  message: AiMessage
  /** 当前模式。 */
  mode?: string
  /** 数据集（图表渲染可选）。 */
  datasets?: unknown[]
  /** 主题模式。 */
  themeMode?: 'light' | 'dark' | 'auto'
  /** 是否正在流式（末尾光标）。 */
  streaming?: boolean
  /** 紧凑形态。 */
  compact?: boolean
  /** 展示审计标识（缺省 true）。 */
  showAudit?: boolean
  /** 展示风险提示（缺省 true）。 */
  showRisks?: boolean
  /** 展示引用来源（缺省 true）。 */
  showCitations?: boolean
  /** 图表引擎工厂（测试注入；缺省动态装载 ECharts 内核）。 */
  engineFactory?: () => Promise<ChartEngineAdapter>
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'ask',
  datasets: () => [],
  themeMode: 'auto',
  streaming: false,
  compact: false,
  showAudit: true,
  showRisks: true,
  showCitations: true,
  engineFactory: undefined,
})

const emit = defineEmits<{
  regenerate: [messageId: string]
  'citation-click': [{ citation: AiCitation }]
  copy: [{ messageId: string }]
}>()

const base = useBaseAiAssistant({ ready: true })

/** 渲染分段（文本走 Markdown、代码走只读高亮）。 */
const parts = ref<{ type: 'text' | 'code'; text: string; lang?: string; html?: string }[]>([])

watch(
  () => props.message.content,
  async (content) => {
    const segments = splitAiContent(content)
    const out: { type: 'text' | 'code'; text: string; lang?: string; html?: string }[] = []
    for (const segment of segments) {
      if (segment.type === 'code') {
        out.push({ ...segment })
      } else {
        out.push({ ...segment, html: await renderAiMarkdown(segment.text) })
      }
    }
    parts.value = out
  },
  { immediate: true },
)

/** 是否失败 / 已停止（可重新生成）。 */
const regenerable = computed(
  () => props.message.role === 'assistant' && (props.message.status === 'error' || props.message.status === 'stopped'),
)

/** 图表数据（结果 → 图表数据集结果）。 */
const chartData = computed(() => {
  const result = props.message.result
  if (result?.kind !== 'chart') {
    return undefined
  }
  const columns = (result.columns ?? []).map((column) => ({ name: column.name, type: column.type ?? 'text' }))
  return { columns, rows: (result.rows ?? []) as Record<string, unknown>[] }
})

/** 图表类型。 */
const chartType = computed(() => normalizeChartKind(props.message.result?.chartType))

/** 表格列。 */
const tableColumns = computed(() => {
  const result = props.message.result
  if (result?.kind !== 'table') {
    return []
  }
  if ((result.columns ?? []).length > 0) {
    return (result.columns ?? []).map((column) => ({ key: column.name, title: column.label ?? column.name }))
  }
  const first = (result.rows?.[0] ?? {}) as Record<string, unknown>
  return Object.keys(first).map((key) => ({ key, title: key }))
})

/** 表格行。 */
const tableRows = computed(() => ((props.message.result?.rows ?? []) as Record<string, unknown>[]))

/**
 * 复制消息内容。
 */
function copyMessage(): void {
  emit('copy', { messageId: props.message.id })
}
</script>

<template>
  <div
    class="bms-ai-message"
    :data-test="`ai-message-${message.id}`"
    :data-role="message.role"
    :data-status="message.status"
    :data-compact="compact || undefined"
    :data-degraded="base.degraded.value || undefined"
  >
    <div class="bms-ai-message__bubble" :class="`is-${message.role}`">
      <slot name="content" :message="message">
        <template v-for="(part, index) in parts" :key="index">
          <CodeViewer
            v-if="part.type === 'code'"
            class="bms-ai-message__code"
            data-test="message-code"
            :content="part.text"
            :language="(part.lang as 'text') ?? 'text'"
          />
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-else class="bms-ai-message__markdown" data-test="message-content" v-html="part.html" />
        </template>
        <span v-if="streaming && message.status === 'streaming'" class="bms-ai-message__cursor" data-test="message-streaming" />
      </slot>

      <slot name="result" :message="message">
        <div v-if="message.result" class="bms-ai-message__result" data-test="message-result">
          <ChartRenderer
            v-if="message.result.kind === 'chart'"
            data-test="message-chart"
            :ready="true"
            :chart-type="chartType"
            :data="chartData"
            :theme-mode="themeMode"
            :height="240"
            :engine-factory="engineFactory"
          />
          <DataTable
            v-else
            data-test="message-table"
            :ready="true"
            :columns="tableColumns"
            :rows="tableRows"
          />
        </div>
      </slot>

      <slot name="citations" :message="message">
        <ul v-if="showCitations && (message.citations ?? []).length > 0" class="bms-ai-message__citations">
          <li
            v-for="(citation, index) in message.citations"
            :key="index"
            data-test="message-citation"
            @click="emit('citation-click', { citation })"
          >
            <span class="bms-ai-message__cite-type">{{ citationTypeLabel(citation.type) }}</span>
            {{ citation.title }}
          </li>
        </ul>
      </slot>

      <slot name="risks" :message="message">
        <ul v-if="showRisks && (message.risks ?? []).length > 0" class="bms-ai-message__risks" data-test="message-risks">
          <li v-for="(risk, index) in message.risks" :key="index" data-test="message-risk">风险：{{ risk }}</li>
        </ul>
      </slot>

      <slot name="actions" :message="message">
        <div class="bms-ai-message__actions">
          <span v-if="showAudit && message.auditId" class="bms-ai-message__audit" data-test="message-audit">
            审计 {{ message.auditId }}
          </span>
          <button type="button" data-test="message-copy" @click="copyMessage">复制</button>
          <button v-if="regenerable" type="button" data-test="message-regenerate" @click="emit('regenerate', message.id)">
            重新生成
          </button>
        </div>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-ai-message {
  display: flex;
  margin-bottom: 12px;
}
.bms-ai-message[data-role='user'] {
  justify-content: flex-end;
}
.bms-ai-message__bubble {
  max-width: 82%;
  padding: 8px 12px;
  border-radius: 8px;
  color: var(--bms-color-text, #303133);
  background: var(--bms-ai-bubble-assistant-bg, #f5f7fa);
}
.bms-ai-message__bubble.is-user {
  color: #fff;
  background: var(--bms-ai-bubble-user-bg, var(--bms-color-primary, #409eff));
}
.bms-ai-message__markdown {
  word-break: break-word;
}
.bms-ai-message__markdown :deep(p) {
  margin: 0 0 6px;
}
.bms-ai-message__code {
  margin: 6px 0;
}
.bms-ai-message__cursor {
  display: inline-block;
  width: 6px;
  height: 14px;
  vertical-align: text-bottom;
  background: var(--bms-ai-stream-cursor, var(--bms-color-primary, #409eff));
  animation: bms-ai-blink 1s steps(2, start) infinite;
}
@keyframes bms-ai-blink {
  to {
    visibility: hidden;
  }
}
.bms-ai-message__result {
  margin-top: 8px;
}
.bms-ai-message__citations {
  padding: 0;
  margin: 8px 0 0;
  list-style: none;
}
.bms-ai-message__citations li {
  padding: 4px 8px;
  margin-bottom: 4px;
  font-size: 12px;
  cursor: pointer;
  background: var(--bms-ai-citation-bg, #ecf5ff);
  border-radius: 4px;
}
.bms-ai-message__cite-type {
  margin-right: 6px;
  color: var(--bms-color-text-secondary, #909399);
}
.bms-ai-message__risks {
  padding: 6px 10px;
  margin: 8px 0 0;
  list-style: none;
  background: var(--bms-ai-risk-bg, #fdf6ec);
  border-left: 3px solid var(--bms-ai-risk-border, var(--bms-color-warning, #e6a23c));
  border-radius: 4px;
}
.bms-ai-message__risks li {
  font-size: 12px;
}
.bms-ai-message__actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
  font-size: 12px;
}
.bms-ai-message__audit {
  color: var(--bms-ai-audit-color, var(--bms-color-text-secondary, #909399));
}
.bms-ai-message__actions button {
  color: var(--bms-color-primary, #409eff);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
