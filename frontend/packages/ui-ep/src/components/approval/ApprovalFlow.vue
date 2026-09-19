<script setup lang="ts">
// 审批流展示容器件（08_8_1）：优先级进度 + 时间线 + 操作面板 + 可选只读 BPMN 图；事件与注入双轨（注入 jobs 时由内核驱动编排）。
// 对外契约沿用 08_01_01 冻结形状并向后兼容扩展（动作事件合并为 `action`，见详细设计第 3.4.2 节）。
import {
  APPROVAL_DIAGRAM_FALLBACK_TEXT,
  APPROVAL_PLACEHOLDER_TEXT,
  normalizeInstance,
  type ApprovalAction,
  type ApprovalAssignee,
  type ApprovalInstance,
  type ApprovalInstanceInput,
  type ApprovalJobs,
  type ApprovalRecordInput,
  type ApprovalSubmitResult,
  type ApprovalTaskInput,
  type ApprovalTimelineOrder,
  type BaseAccess,
  type BaseNotice,
  type BasePresignedUrl,
} from '@bms/core'
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'

import { useBaseApprovalFlow } from '../../composables/useBaseApprovalFlow'
import { useConfirm } from '../../composables/useConfirm'
import FormDialog from '../modal/FormDialog.vue'
import ApprovalActionPanel, { type ApprovalPanelPayload } from './ApprovalActionPanel.vue'
import ApprovalProgress from './ApprovalProgress.vue'
import ApprovalTimeline from './ApprovalTimeline.vue'

// 只读 BPMN 图独立分包（bpmn-js 不进首屏）。
const Diagram = defineAsyncComponent(() => import('./ApprovalFlowDiagram.vue'))

interface Props {
  /** 数据通路是否就绪（占位语义开关，缺省 `false`）。 */
  ready?: boolean
  /** 流程实例（受控覆盖：提供则装载；按装载输入口径，可省略字段）。 */
  instance?: ApprovalInstanceInput
  /** 审批记录（受控覆盖：提供则装载；按装载输入口径）。 */
  records?: readonly ApprovalRecordInput[]
  /** 当前待办任务（受控覆盖：提供则装载；按装载输入口径）。 */
  currentTask?: ApprovalTaskInput
  /** 加载态（受控覆盖）。 */
  loading?: boolean
  /** 紧凑模式。 */
  compact?: boolean
  /** 可审批（`wf:approve` + 持有待办）。 */
  canApprove?: boolean
  /** 可撤回（发起人且实例未结束）。 */
  canWithdraw?: boolean
  /** 是否展示只读 BPMN 图。 */
  showDiagram?: boolean
  /** BPMN 定义快照（只读图数据源）。 */
  bpmnXml?: string
  /** 只读图图片地址（预签名通路）。 */
  diagramUrl?: string
  /** 降级文案。 */
  degradeText?: string
  /** 实例标识（注入取数用）。 */
  instanceId?: string
  /** 取数 / 提交 / 取图址处理函数（注入时才由内核驱动编排）。 */
  jobs?: ApprovalJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
  /** 只读图图片通路（预签名）。 */
  presigned?: BasePresignedUrl
  /** 是否展示操作区。 */
  showActions?: boolean
  /** 是否展示时间线。 */
  showTimeline?: boolean
  /** 时间线排序。 */
  timelineOrder?: ApprovalTimelineOrder
  /** 高亮动作。 */
  highlightAction?: ApprovalAction
  /** 可退回节点（驳回选择）。 */
  returnableNodes?: readonly { nodeId: string; name: string }[]
  /** 转办候选。 */
  transferCandidates?: readonly { id: string; name: string }[]
  /** 就绪后是否自动取数（缺省 `true`）。 */
  autoLoad?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  instance: undefined,
  records: undefined,
  currentTask: undefined,
  loading: undefined,
  compact: false,
  canApprove: undefined,
  canWithdraw: undefined,
  showDiagram: false,
  bpmnXml: '',
  diagramUrl: '',
  degradeText: APPROVAL_PLACEHOLDER_TEXT,
  instanceId: '',
  jobs: undefined,
  access: undefined,
  notice: undefined,
  presigned: undefined,
  showActions: true,
  showTimeline: true,
  timelineOrder: 'asc',
  highlightAction: undefined,
  returnableNodes: () => [],
  transferCandidates: () => [],
  autoLoad: true,
})

const emit = defineEmits<{
  action: [payload: ApprovalPanelPayload]
  'node-click': [nodeId: string]
  'node-select': [payload: { nodeId: string; assignees: ApprovalAssignee[] }]
  retry: []
  saved: [result: ApprovalSubmitResult]
  failed: [payload: { message: string; code?: number }]
  reloaded: [payload: { instance: boolean; records: boolean }]
  'diagram-fallback': []
}>()

const api = useBaseApprovalFlow({
  ready: props.ready,
  instanceId: props.instanceId,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
  presigned: props.presigned,
})

const { confirm } = useConfirm()

/**
 * 归一受控实例输入为运行态（受控面可省略字段）。
 *
 * @param input 实例装载输入。
 * @returns 运行态实例。
 */
function normalizeInstanceInput(input: ApprovalInstanceInput): ApprovalInstance {
  return normalizeInstance(input)
}

/** 驳回弹窗显隐。 */
const rejectVisible = ref(false)
/** 转办弹窗显隐。 */
const transferVisible = ref(false)
/** 驳回 / 转办意见草稿。 */
const dialogComment = ref('')
/** 驳回退回目标。 */
const dialogTarget = ref('')
/** 面板内联错误。 */
const actionError = ref('')

/** 生效加载态（受控覆盖优先）。 */
const loading = computed(() => (props.loading === true ? true : api.busy.value))
/** 生效可审批（受控覆盖优先）。 */
const canApprove = computed(() => (props.canApprove !== undefined ? props.canApprove : api.canApprove.value))
/** 生效可撤回。 */
const canWithdraw = computed(() => (props.canWithdraw !== undefined ? props.canWithdraw : api.canWithdraw.value))

/** 生效实例（受控覆盖优先；受控面按装载输入口径归一为运行态）。 */
const instance = computed<ApprovalInstance | undefined>(() =>
  props.instance === undefined ? api.instance.value : normalizeInstanceInput(props.instance),
)
/** 生效记录（受控覆盖优先）。 */
const records = computed(() => props.records ?? api.records.value)
/** 生效当前待办。 */
const currentTask = computed(() => props.currentTask ?? api.currentTask.value)

/** 可用动作矩阵（并入受控覆盖）。 */
const actions = computed(() => {
  if (props.canApprove === undefined && props.canWithdraw === undefined) {
    return api.actions.value
  }
  const base = api.actions.value
  const task = base.approve || base.reject || base.transfer || base.comment
  return {
    approve: task && canApprove.value,
    reject: task && canApprove.value,
    transfer: task && canApprove.value,
    withdraw: api.readonly.value === false && canWithdraw.value,
    comment: task && canApprove.value,
  }
})

/** 只读图形态（受控 `diagramUrl` 优先）。 */
const diagramMode = computed(() => (props.diagramUrl !== '' ? 'image' : api.diagramMode.value))
/** 只读图 XML。 */
const diagramXml = computed(() => props.bpmnXml || api.diagramXml.value)
/** 只读图地址。 */
const diagramUrl = computed(() => props.diagramUrl || api.diagramUrl.value)

watch(
  () => props.ready,
  (value) => api.setReady(value),
)
watch(
  () => props.instanceId,
  (value) => api.setInstanceId(value),
)
watch(
  () => props.jobs,
  (value) => api.setJobs(value ?? {}),
)
watch(
  () => props.access,
  (value) => api.setAccess(value),
)
watch(
  () => props.notice,
  (value) => api.setNotice(value),
)
watch(
  () => props.presigned,
  (value) => api.setPresigned(value),
)
watch(
  () => props.instance,
  (value) => {
    if (value !== undefined) {
      api.applyInstance(value)
    }
  },
  { immediate: true },
)
watch(
  () => props.records,
  (value) => {
    if (value !== undefined) {
      api.applyRecords(value)
    }
  },
  { immediate: true },
)
watch(
  () => props.currentTask,
  (value) => {
    if (value !== undefined) {
      api.applyTask(value)
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (props.ready && props.autoLoad && props.instance === undefined) {
    void api.load().then((ok) => emit('reloaded', { instance: ok, records: ok }))
  }
})

/**
 * 动作点击：先上抛 `action`（保留事件轨）；注入 `jobs` 时由内核驱动真实编排。
 *
 * @param payload 面板载荷。
 */
async function onAction(payload: ApprovalPanelPayload): Promise<void> {
  emit('action', payload)
  if (props.jobs?.submit === undefined) {
    return
  }
  if (payload.action === 'reject') {
    dialogComment.value = payload.comment ?? ''
    dialogTarget.value = payload.target ?? ''
    rejectVisible.value = true
    return
  }
  if (payload.action === 'transfer') {
    dialogComment.value = payload.comment ?? ''
    dialogTarget.value = payload.target ?? ''
    transferVisible.value = true
    return
  }
  if (payload.action === 'withdraw') {
    const ok = await confirm({ title: '确认撤回', content: '撤回后流程实例将终止', danger: true })
    if (!ok) {
      return
    }
  }
  await submit(payload.action, payload.comment, payload.target)
}

/**
 * 执行提交并上抛结果。
 *
 * @param action 动作。
 * @param comment 意见。
 * @param target 目标。
 */
async function submit(action: ApprovalAction, comment?: string, target?: string): Promise<void> {
  const result = await api.submit(action, { comment, target })
  if (result !== undefined) {
    emit('saved', result)
    emit('reloaded', { instance: true, records: true })
    return
  }
  if (api.phase.value === 'failed') {
    emit('failed', { message: api.errorMessage.value })
  }
}

/** 确认驳回。 */
async function confirmReject(): Promise<void> {
  rejectVisible.value = false
  await submit('reject', dialogComment.value, dialogTarget.value)
}

/** 确认转办。 */
async function confirmTransfer(): Promise<void> {
  transferVisible.value = false
  await submit('transfer', dialogComment.value, dialogTarget.value)
}

/** 只读图失败降级。 */
function onDiagramError(): void {
  api.markDiagramFailed()
  emit('diagram-fallback')
}

/**
 * 节点点击（联动时间线）。
 *
 * @param nodeId 节点标识。
 */
function onNodeClick(nodeId: string): void {
  emit('node-click', nodeId)
}

/**
 * 会签展开联动。
 *
 * @param payload 节点与审批人。
 */
function onNodeSelect(payload: { nodeId: string; assignees: ApprovalAssignee[] }): void {
  emit('node-select', payload)
}

/** 重试失败提交。 */
async function retry(): Promise<void> {
  emit('retry')
  const result = await api.retry()
  if (result !== undefined) {
    emit('saved', result)
  } else {
    await api.load()
  }
}

defineExpose({
  /** 编排基类实例（核对页与宿主读取普通字段用）。 */
  approval: api.approval,
  /** 编排投影（响应式面）。 */
  projection: api,
  submit,
  load: api.load,
  retry,
})
</script>

<template>
  <div
    class="bms-approval-flow"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-phase="api.phase.value"
    :data-compact="compact || undefined"
    :data-readonly="api.readonly.value || undefined"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <slot name="live">
        <div v-if="loading" class="bms-approval-flow__loading" data-test="loading">加载中…</div>

        <div class="bms-approval-flow__progress" data-test="progress">
          <p v-if="!instance || instance.nodes.length === 0" data-test="empty">暂无流程节点</p>
          <slot v-else name="progress" :nodes="instance.nodes">
            <ApprovalProgress
              :nodes="instance.nodes"
              :instance-status="instance.status"
              :current-node-id="instance.currentNodeId"
              :compact="compact"
              :direction="compact ? 'vertical' : 'horizontal'"
              @node-click="onNodeClick"
              @node-select="onNodeSelect"
            />
          </slot>
          <span class="bms-approval-flow__status" data-test="instance-status">{{ instance?.status ?? '' }}</span>
        </div>

        <div v-if="showTimeline" class="bms-approval-flow__timeline" data-test="timeline">
          <p v-if="records.length === 0" data-test="empty-records">暂无审批记录</p>
          <slot v-else name="timeline" :records="records">
            <ApprovalTimeline
              :records="records"
              :order="timelineOrder"
              :active-node-id="instance?.currentNodeId"
              :highlight-action="highlightAction"
            />
          </slot>
        </div>

        <div v-if="showDiagram" class="bms-approval-flow__diagram" data-test="diagram">
          <component
            :is="Diagram"
            v-if="diagramMode === 'xml' || diagramMode === 'image'"
            :xml="diagramXml"
            :url="diagramUrl"
            :current-node-id="instance?.currentNodeId ?? ''"
            @error="onDiagramError"
          />
          <div v-else data-test="diagram-degrade">{{ APPROVAL_DIAGRAM_FALLBACK_TEXT }}</div>
        </div>

        <div v-if="showActions" class="bms-approval-flow__actions" data-test="actions">
          <slot name="actions" :disabled="api.disabled.value">
            <slot name="panel">
              <ApprovalActionPanel
                :actions="actions"
                :current-task="currentTask"
                :readonly="api.readonly.value"
                :submitting="api.busy.value"
                :returnable-nodes="returnableNodes"
                :transfer-candidates="transferCandidates"
                @action="onAction"
              />
            </slot>
          </slot>
          <span v-if="api.errorMessage.value !== ''" class="bms-approval-flow__error" data-test="error">
            {{ api.errorMessage.value }}
          </span>
          <span v-if="actionError !== ''" class="bms-approval-flow__error">{{ actionError }}</span>
          <button
            v-if="api.phase.value === 'failed'"
            type="button"
            class="bms-approval-flow__retry"
            data-test="retry"
            @click="retry"
          >
            重试
          </button>
        </div>
      </slot>
    </template>

    <FormDialog
      v-model="rejectVisible"
      mode="create"
      title="确认驳回"
      :dirty="dialogComment !== ''"
      @submit="confirmReject"
    >
      <div class="bms-approval-flow__dialog" data-test="reject-dialog">
        <p>驳回后流程将退回至所选节点（缺省退回上一节点）。</p>
        <textarea v-model="dialogComment" data-test="reject-comment" rows="3" placeholder="请填写驳回意见（必填）" />
        <select v-if="returnableNodes.length > 0" v-model="dialogTarget" data-test="reject-node">
          <option value="">退回上一节点</option>
          <option v-for="node in returnableNodes" :key="node.nodeId" :value="node.nodeId">{{ node.name }}</option>
        </select>
      </div>
    </FormDialog>

    <FormDialog
      v-model="transferVisible"
      mode="create"
      title="转办审批"
      :dirty="dialogTarget !== ''"
      @submit="confirmTransfer"
    >
      <div class="bms-approval-flow__dialog" data-test="transfer-dialog">
        <p>转办后本人不再持有该待办。</p>
        <select v-model="dialogTarget" data-test="transfer-user">
          <option value="">请选择转办对象</option>
          <option v-for="candidate in transferCandidates" :key="candidate.id" :value="candidate.id">
            {{ candidate.name }}
          </option>
        </select>
      </div>
    </FormDialog>
  </div>
</template>

<style scoped>
.bms-approval-flow {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md, 12px);
}

.bms-approval-flow__status {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}

.bms-approval-flow__dialog {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-approval-flow__dialog textarea,
.bms-approval-flow__dialog select {
  padding: 4px 6px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  font: inherit;
}

.bms-approval-flow__loading,
.bms-approval-flow__error {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}

.bms-approval-flow__error {
  color: var(--bms-color-danger, #f56c6c);
}
</style>
