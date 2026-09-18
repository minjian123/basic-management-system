<script setup lang="ts">
// 审批流展示（占位版，08_01_01）：契约先行冻结；数据通路未就绪时不请求、操作禁用 + 降级提示。可选只读 BPMN 图独立分包懒加载。
import { defineAsyncComponent, watch } from 'vue'

import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 只读 BPMN 图独立分包（bpmn-js 不进首屏；真实实现 08_08 接入）。
const ApprovalDiagram = defineAsyncComponent(() => import('./ApprovalFlowDiagram.vue'))

/** 节点状态。 */
export type ApprovalNodeStatus = 'done' | 'active' | 'pending' | 'rejected' | 'skipped'

/** 流程节点。 */
export interface ApprovalNode {
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  name: string
  /** 节点状态。 */
  status: ApprovalNodeStatus
  /** 审批人。 */
  assignees?: { id: string; name: string }[]
  /** 是否会签节点。 */
  signed?: boolean
  /** 处理时间。 */
  time?: string
}

/** 流程实例状态。 */
export type ApprovalInstanceStatus = 'running' | 'finished' | 'rejected' | 'abnormal'

/** 流程实例。 */
export interface ApprovalInstance {
  /** 实例标识。 */
  id: string
  /** 实例状态。 */
  status: ApprovalInstanceStatus
  /** 当前节点标识。 */
  currentNodeId?: string
  /** 节点序列。 */
  nodes: ApprovalNode[]
}

/** 审批动作。 */
export type ApprovalAction = 'approve' | 'reject' | 'withdraw' | 'transfer' | 'comment'

/** 审批记录。 */
export interface ApprovalRecord {
  /** 记录标识。 */
  id: string
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  nodeName: string
  /** 审批人标识。 */
  assigneeId: string
  /** 审批人姓名。 */
  assigneeName: string
  /** 动作。 */
  action: ApprovalAction
  /** 意见。 */
  comment?: string
  /** 时间。 */
  createdAt: string
}

/** 当前待办任务。 */
export interface ApprovalTask {
  /** 任务标识。 */
  taskId: string
  /** 节点标识。 */
  nodeId: string
  /** 节点名称。 */
  nodeName: string
  /** 是否会签。 */
  signed?: boolean
  /** 截止时间。 */
  deadline?: string
}

/** 审批操作载荷。 */
export interface ApprovalActionPayload {
  /** 动作。 */
  action: ApprovalAction
  /** 任务标识。 */
  taskId?: string
  /** 意见。 */
  comment?: string
  /** 驳回目标 / 转办对象。 */
  target?: string
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 流程实例（节点序列 / 当前节点 / 状态）。 */
  instance?: ApprovalInstance
  /** 审批记录（全链路轨迹）。 */
  records?: ApprovalRecord[]
  /** 当前待办任务。 */
  currentTask?: ApprovalTask
  /** 加载中。 */
  loading?: boolean
  /** 紧凑模式（卡片摘要）。 */
  compact?: boolean
  /** 可审批（`wf:approve` + 持有待办）。 */
  canApprove?: boolean
  /** 可撤回（发起人且实例未结束）。 */
  canWithdraw?: boolean
  /** 是否展示只读 BPMN 图。 */
  showDiagram?: boolean
  /** BPMN 定义快照（只读图数据源）。 */
  bpmnXml?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  instance: undefined,
  records: () => [],
  currentTask: undefined,
  loading: false,
  compact: false,
  canApprove: false,
  canWithdraw: false,
  showDiagram: false,
  bpmnXml: '',
  degradeText: '审批数据未就绪（占位）',
})

const emit = defineEmits<{
  approve: [payload: ApprovalActionPayload]
  reject: [payload: ApprovalActionPayload]
  transfer: [payload: ApprovalActionPayload]
  withdraw: [payload: ApprovalActionPayload]
  comment: [payload: ApprovalActionPayload]
  'node-click': [nodeId: string]
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 构造审批操作载荷（任务标识取当前待办）。 */
function payload(action: ApprovalAction): ApprovalActionPayload {
  return { action, taskId: props.currentTask?.taskId }
}
</script>

<template>
  <div
    class="bms-approval-flow"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-approval-flow__progress" data-test="progress">
        <p v-if="!instance || instance.nodes.length === 0" data-test="empty">暂无流程节点</p>
        <span
          v-for="node in instance?.nodes ?? []"
          :key="node.nodeId"
          class="bms-approval-flow__node"
          :data-test="`node-${node.nodeId}`"
          :data-status="node.status"
          @click="emit('node-click', node.nodeId)"
        >
          {{ node.name }}
          <em v-if="node.signed" data-test="signed">会签</em>
        </span>
      </div>

      <div class="bms-approval-flow__timeline" data-test="timeline">
        <p v-if="records.length === 0" data-test="empty-records">暂无审批记录</p>
        <div
          v-for="record in records"
          :key="record.id"
          class="bms-approval-flow__record"
          :data-test="`record-${record.id}`"
          :data-action="record.action"
        >
          <span>{{ record.nodeName }}</span>
          <span>{{ record.assigneeName }}</span>
          <span>{{ record.action }}</span>
          <span v-if="record.comment">{{ record.comment }}</span>
        </div>
      </div>

      <div v-if="showDiagram" class="bms-approval-flow__diagram" data-test="diagram">
        <component
          :is="ApprovalDiagram"
          v-if="bpmnXml && instance"
          :xml="bpmnXml"
          :current-node-id="instance.currentNodeId"
        />
        <div v-else data-test="diagram-degrade">流程图加载失败，已切换为进度视图</div>
      </div>

      <div class="bms-approval-flow__actions" data-test="actions">
        <slot name="actions" :disabled="placeholder.disabled.value">
          <button
            type="button"
            data-test="approve"
            :disabled="placeholder.disabled.value || !canApprove"
            @click="emit('approve', payload('approve'))"
          >
            同意
          </button>
          <button
            type="button"
            data-test="reject"
            :disabled="placeholder.disabled.value || !canApprove"
            @click="emit('reject', payload('reject'))"
          >
            驳回
          </button>
          <button
            type="button"
            data-test="transfer"
            :disabled="placeholder.disabled.value || !canApprove"
            @click="emit('transfer', payload('transfer'))"
          >
            转办
          </button>
          <button
            type="button"
            data-test="withdraw"
            :disabled="placeholder.disabled.value || !canWithdraw"
            @click="emit('withdraw', payload('withdraw'))"
          >
            撤回
          </button>
          <button
            type="button"
            data-test="comment"
            :disabled="placeholder.disabled.value || !canApprove"
            @click="emit('comment', payload('comment'))"
          >
            评论
          </button>
        </slot>
      </div>
      </slot>
    </template>
  </div>
</template>
