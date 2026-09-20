<script setup lang="ts">
// 审批时间线件（08_8_1）：正序缺省可切倒序 + 节点分组 + 动作语义色 + 长意见折叠 + 附件名称与数量 + 空态。
import {
  APPROVAL_ACTION_LABELS,
  APPROVAL_EMPTY_TEXT,
  foldComment,
  groupRecordsByNode,
  normalizeRecords,
  resolveTimelineOrderRecords,
  type ApprovalAction,
  type ApprovalAttachment,
  type ApprovalRecord,
  type ApprovalRecordInput,
  type ApprovalTimelineOrder,
} from '@bms/core'
import { computed, ref } from 'vue'

import { useBaseApprovalFlow } from '../../composables/useBaseApprovalFlow'
import UserAvatar from '../display/UserAvatar.vue'

interface Props {
  /** 审批记录。 */
  records?: readonly ApprovalRecordInput[]
  /** 排序（缺省正序）。 */
  order?: ApprovalTimelineOrder
  /** 是否按节点分组。 */
  grouped?: boolean
  /** 高亮动作。 */
  highlightAction?: ApprovalAction
  /** 定位节点（容器联动）。 */
  activeNodeId?: string
  /** 折叠阈值（Unicode 码点；缺省 200）。 */
  foldLimit?: number
  /** 是否展示附件。 */
  showAttachments?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  records: () => [],
  order: 'asc',
  grouped: false,
  highlightAction: undefined,
  activeNodeId: undefined,
  foldLimit: 200,
  showAttachments: true,
})

const emit = defineEmits<{
  'record-click': [recordId: string]
  'attachment-click': [payload: { recordId: string; attachment: ApprovalAttachment }]
  'fold-toggle': [payload: { recordId: string; folded: boolean }]
  'order-change': [order: ApprovalTimelineOrder]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { approval } = useBaseApprovalFlow()

/** 排序方向（受控缺省，内部可切）。 */
const innerOrder = ref<ApprovalTimelineOrder>(props.order)
/** 已展开的记录标识集合。 */
const expanded = ref<Set<string>>(new Set())

/** 运行态记录。 */
const items = computed(() => normalizeRecords(props.records))

/** 排序后记录。 */
const ordered = computed(() => resolveTimelineOrderRecords(items.value, innerOrder.value))

/** 分组结果。 */
const groups = computed(() => groupRecordsByNode(ordered.value))

/**
 * 切换排序（受控只上抛，内部同步以即时生效）。
 *
 * @param order 目标方向。
 */
function switchOrder(order: ApprovalTimelineOrder): void {
  innerOrder.value = order
  emit('order-change', order)
}

/**
 * 意见展示文本（超阈值折叠）。
 *
 * @param record 记录。
 * @returns 展示文本与是否已折叠。
 */
function commentOf(record: ApprovalRecord): { text: string; folded: boolean } {
  const result = foldComment(record.comment, props.foldLimit)
  if (expanded.value.has(record.id)) {
    return { text: record.comment, folded: false }
  }
  return result
}

/**
 * 展开 / 收起长意见。
 *
 * @param record 记录。
 */
function toggleFold(record: ApprovalRecord): void {
  const next = new Set(expanded.value)
  if (next.has(record.id)) {
    next.delete(record.id)
  } else {
    next.add(record.id)
  }
  expanded.value = next
  emit('fold-toggle', { recordId: record.id, folded: next.has(record.id) })
}

/**
 * 记录是否为高亮动作。
 *
 * @param record 记录。
 * @returns 是否高亮。
 */
function isHighlight(record: ApprovalRecord): boolean {
  return props.highlightAction !== undefined && record.action === props.highlightAction
}

// 说明：`approval` 仅为挂链（件层以投影组合式接入继承链）。
void approval
</script>

<template>
  <div class="bms-approval-timeline" data-test="approval-timeline" :data-order="innerOrder">
    <div class="bms-approval-timeline__toolbar">
      <button
        type="button"
        class="bms-approval-timeline__order"
        data-test="timeline-order"
        @click="switchOrder(innerOrder === 'asc' ? 'desc' : 'asc')"
      >
        {{ innerOrder === 'asc' ? '正序' : '倒序' }}
      </button>
    </div>

    <p v-if="ordered.length === 0" class="bms-approval-timeline__empty" data-test="empty-records">
      {{ APPROVAL_EMPTY_TEXT }}
    </p>

    <slot v-else name="record" :records="ordered">
      <div v-for="group in groups" :key="group.nodeId" class="bms-approval-timeline__group" :data-test="`record-group-${group.nodeId}`">
        <h4 v-if="grouped" class="bms-approval-timeline__group-title">{{ group.nodeName }}</h4>
        <ol class="bms-approval-timeline__list">
          <li
            v-for="record in group.records"
            :key="record.id"
            class="bms-approval-timeline__item"
            :data-test="`record-${record.id}`"
            :data-action="record.action"
            :data-highlight="isHighlight(record) || undefined"
            :data-node-active="record.nodeId === activeNodeId || undefined"
            @click="emit('record-click', record.id)"
          >
            <span class="bms-approval-timeline__head">
              <UserAvatar :name="record.assigneeName" size="xs" />
              <span class="bms-approval-timeline__who">{{ record.assigneeName }}</span>
              <span class="bms-approval-timeline__action">{{ APPROVAL_ACTION_LABELS[record.action] }}</span>
              <span v-if="record.target" class="bms-approval-timeline__target">→ {{ record.target }}</span>
              <span class="bms-approval-timeline__time">{{ record.createdAt }}</span>
            </span>
            <span class="bms-approval-timeline__node">{{ record.nodeName }}</span>
            <span v-if="record.comment !== ''" class="bms-approval-timeline__comment">
              {{ commentOf(record).text }}
              <button
                v-if="commentOf(record).folded || expanded.has(record.id)"
                type="button"
                class="bms-approval-timeline__fold"
                :data-test="`fold-${record.id}`"
                @click.stop="toggleFold(record)"
              >
                {{ expanded.has(record.id) ? '收起' : '展开' }}
              </button>
            </span>
            <span
              v-if="showAttachments && record.attachments.length > 0"
              class="bms-approval-timeline__attachments"
              :data-attachment-count="record.attachments.length"
            >
              <button
                v-for="attachment in record.attachments"
                :key="attachment.id"
                type="button"
                class="bms-approval-timeline__attachment"
                :data-test="`attachment-${attachment.id}`"
                @click.stop="emit('attachment-click', { recordId: record.id, attachment })"
              >
                {{ attachment.name }}
              </button>
            </span>
          </li>
        </ol>
      </div>
    </slot>
  </div>
</template>

<style scoped>
.bms-approval-timeline__toolbar {
  display: flex;
  justify-content: flex-end;
}

.bms-approval-timeline__order {
  padding: 2px 8px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg);
  color: inherit;
  font: inherit;
  font-size: 0.85em;
  cursor: pointer;
}

.bms-approval-timeline__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.bms-approval-timeline__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--bms-spacing-sm, 4px) 0;
  border-bottom: 1px solid var(--bms-color-border);
  cursor: pointer;
}

.bms-approval-timeline__item[data-node-active='true'] {
  background: var(--bms-color-primary-light);
}

.bms-approval-timeline__head {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-approval-timeline__action {
  font-weight: 500;
}

.bms-approval-timeline__item[data-action='approve'] .bms-approval-timeline__action {
  color: var(--bms-color-success);
}

.bms-approval-timeline__item[data-action='reject'] .bms-approval-timeline__action {
  color: var(--bms-color-danger);
}

.bms-approval-timeline__item[data-action='withdraw'] .bms-approval-timeline__action {
  color: var(--bms-color-warning);
}

.bms-approval-timeline__item[data-action='transfer'] .bms-approval-timeline__action,
.bms-approval-timeline__item[data-action='comment'] .bms-approval-timeline__action {
  color: var(--bms-color-text-secondary);
}

.bms-approval-timeline__time {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}

.bms-approval-timeline__node,
.bms-approval-timeline__comment {
  color: var(--bms-color-text-secondary);
  font-size: 0.9em;
}

.bms-approval-timeline__fold {
  margin-left: var(--bms-spacing-sm, 4px);
  border: 0;
  background: transparent;
  color: var(--bms-color-primary);
  font: inherit;
  font-size: 0.9em;
  cursor: pointer;
}

.bms-approval-timeline__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-approval-timeline__attachment {
  border: 0;
  background: transparent;
  color: var(--bms-color-primary);
  font: inherit;
  font-size: 0.85em;
  cursor: pointer;
}

.bms-approval-timeline__empty,
.bms-approval-timeline__group-title {
  color: var(--bms-color-text-secondary);
}
</style>
