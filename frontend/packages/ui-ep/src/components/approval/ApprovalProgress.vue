<script setup lang="ts">
// 流程进度件（08_8_1）：简化节点进度三形态（横向 / 纵向 / 紧凑）+ 当前节点高亮滚动居中 + 会签 n/m 聚合 + 分支降级。
import {
  normalizeNode,
  normalizeNodes,
  resolveActiveNodeIndex,
  resolveVisibleNodes,
  signProgress,
  type ApprovalInstanceStatus,
  type ApprovalNode,
  type ApprovalNodeInput,
  type ApprovalNodeStatus,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseApprovalFlow } from '../../composables/useBaseApprovalFlow'

/** 进度方向。 */
export type ApprovalProgressDirection = 'horizontal' | 'vertical'

interface Props {
  /** 节点序列。 */
  nodes?: readonly ApprovalNodeInput[]
  /** 实例状态（决定整体语义色）。 */
  instanceStatus?: ApprovalInstanceStatus
  /** 当前节点标识（高亮与滚动居中）。 */
  currentNodeId?: string
  /** 方向（缺省横向）。 */
  direction?: ApprovalProgressDirection
  /** 紧凑模式（仅圆点 + 名称；未走分支省略）。 */
  compact?: boolean
  /** 是否展示节点审批人与时间。 */
  showAssignees?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  nodes: () => [],
  instanceStatus: 'running',
  currentNodeId: undefined,
  direction: 'horizontal',
  compact: false,
  showAssignees: true,
})

const emit = defineEmits<{
  'node-click': [nodeId: string]
  'node-select': [payload: { nodeId: string; assignees: ApprovalNode['assignees'] }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { approval } = useBaseApprovalFlow()

/** 运行态节点序列。 */
const items = computed<ApprovalNode[]>(() => normalizeNodes(props.nodes))

/** 可见节点（分支降级：紧凑省略未走分支；非紧凑置灰保留）。 */
const visible = computed(() => resolveVisibleNodes(items.value, { compact: props.compact }))

/** 当前节点索引（用于高亮与滚动定位）。 */
const activeIndex = computed(() => resolveActiveNodeIndex(items.value, props.currentNodeId))

/** 当前节点标识。 */
const activeId = computed(() => (activeIndex.value < 0 ? '' : items.value[activeIndex.value].nodeId))

/** 容器引用（滚动居中用）。 */
const container = ref<HTMLElement | undefined>()

/** 会签展开的节点标识（空串表示未展开）。 */
const expandedId = ref('')

watch([activeId, visible], async () => {
  if (activeId.value === '' || props.direction !== 'horizontal') {
    return
  }
  await Promise.resolve()
  const target = container.value?.querySelector<HTMLElement>(`[data-node-id="${activeId.value}"]`)
  target?.scrollIntoView?.({ inline: 'center', block: 'nearest' })
})

/**
 * 取节点会签进度文案。
 *
 * @param node 节点。
 * @returns 文案；非会签返回空串。
 */
function signText(node: ApprovalNode): string {
  const progress = signProgress(node)
  return progress === undefined ? '' : `已完成 ${progress.done} / 共 ${progress.total}`
}

/**
 * 节点点击（联动时间线定位）。
 *
 * @param node 节点。
 */
function onClick(node: ApprovalNode): void {
  emit('node-click', node.nodeId)
}

/**
 * 展开 / 收起会签审批人处理状态。
 *
 * @param node 节点。
 */
function toggleSigned(node: ApprovalNode): void {
  if (!node.signed) {
    return
  }
  expandedId.value = expandedId.value === node.nodeId ? '' : node.nodeId
  emit('node-select', { nodeId: node.nodeId, assignees: node.assignees })
}

/** 实例状态文案。 */
const statusText = computed(
  () => ({ running: '进行中', finished: '已完成', rejected: '已驳回', abnormal: '异常' })[props.instanceStatus],
)

/** 已展开节点的审批人处理状态（序号 + 姓名 + 是否已处理）。 */
const signedDetail = computed<{ id: string; name: string; handled: boolean }[]>(() => {
  if (expandedId.value === '') {
    return []
  }
  const node = items.value.find((item) => item.nodeId === expandedId.value)
  if (node === undefined) {
    return []
  }
  const done = signProgress(node)?.done ?? 0
  return node.assignees.map((assignee, index) => ({ id: assignee.id, name: assignee.name, handled: index < done }))
})

/** 节点状态语义（供 `data-status` 与样式类）。 */
function statusOf(node: ApprovalNode): ApprovalNodeStatus {
  return node.status
}
// 说明：`approval` 仅为挂链（件层以投影组合式接入继承链）。
void approval
void normalizeNode
</script>

<template>
  <div
    ref="container"
    class="bms-approval-progress"
    data-test="approval-progress"
    :data-direction="direction"
    :data-compact="compact || undefined"
    :data-status="instanceStatus"
  >
    <p v-if="visible.length === 0" class="bms-approval-progress__empty" data-test="progress-empty">
      暂无流程节点
    </p>

    <slot v-else name="node" :nodes="visible">
      <ol class="bms-approval-progress__list">
        <li
          v-for="node in visible"
          :key="node.nodeId"
          class="bms-approval-progress__item"
          :data-test="`node-${node.nodeId}`"
          :data-status="statusOf(node)"
          :data-node-id="node.nodeId"
          :data-active="node.nodeId === activeId || undefined"
          @click="onClick(node)"
        >
          <span class="bms-approval-progress__dot" aria-hidden="true" />
          <span class="bms-approval-progress__body">
            <span class="bms-approval-progress__name" :data-test="node.nodeId === activeId ? 'active-node' : undefined">
              {{ node.name }}
            </span>
            <span
              v-if="node.signed"
              class="bms-approval-progress__sign"
              data-test="signed"
              @click.stop="toggleSigned(node)"
            >
              <em data-test="sign-progress">{{ signText(node) }}</em>
            </span>
            <span
              v-if="showAssignees && node.assignees.length > 0"
              class="bms-approval-progress__assignees"
              :data-test="`node-assignees-${node.nodeId}`"
            >
              <span v-for="assignee in node.assignees" :key="assignee.id" class="bms-approval-progress__assignee">
                {{ assignee.name }}
              </span>
            </span>
            <span v-if="showAssignees && node.time" class="bms-approval-progress__time">{{ node.time }}</span>
          </span>
        </li>
      </ol>

      <div v-if="signedDetail.length > 0" class="bms-approval-progress__signed-panel" data-test="signed-panel">
        <span
          v-for="assignee in signedDetail"
          :key="assignee.id"
          class="bms-approval-progress__signed-item"
          :data-handled="assignee.handled"
        >
          {{ assignee.name }}（{{ assignee.handled ? '已处理' : '待处理' }}）
        </span>
      </div>
    </slot>

    <p class="bms-approval-progress__summary" data-test="progress-summary">
      {{ statusText }} · 已完成 {{ items.filter((item) => item.status === 'done').length }} / {{ items.length }} 节点
    </p>
  </div>
</template>

<style scoped>
.bms-approval-progress {
  overflow-x: auto;
}

.bms-approval-progress__list {
  display: flex;
  gap: var(--bms-spacing-md, 12px);
  margin: 0;
  padding: 0;
  list-style: none;
}

.bms-approval-progress[data-direction='vertical'] .bms-approval-progress__list {
  flex-direction: column;
}

.bms-approval-progress__item {
  display: flex;
  align-items: flex-start;
  gap: var(--bms-spacing-sm, 4px);
  min-width: 96px;
  cursor: pointer;
}

.bms-approval-progress__dot {
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border: 2px solid var(--bms-color-border);
  border-radius: 50%;
  background: var(--bms-color-bg);
}

.bms-approval-progress__item[data-status='done'] .bms-approval-progress__dot {
  border-color: var(--bms-color-success);
  background: var(--bms-color-success);
}

.bms-approval-progress__item[data-status='active'] .bms-approval-progress__dot {
  border-color: var(--bms-color-primary);
  background: var(--bms-color-primary);
  box-shadow: 0 0 0 3px var(--bms-color-focus-ring);
}

.bms-approval-progress__item[data-status='rejected'] .bms-approval-progress__dot {
  border-color: var(--bms-color-danger);
  background: var(--bms-color-danger);
}

.bms-approval-progress__item[data-status='skipped'] {
  opacity: 0.6;
}

.bms-approval-progress__item[data-status='skipped'] .bms-approval-progress__dot {
  border-style: dashed;
}

.bms-approval-progress__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bms-approval-progress__name {
  font-weight: 500;
}

.bms-approval-progress[data-compact='true'] .bms-approval-progress__name {
  font-weight: 400;
}

.bms-approval-progress__assignees {
  display: flex;
  gap: var(--bms-spacing-sm, 4px);
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}

.bms-approval-progress__time {
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}

.bms-approval-progress__sign {
  color: var(--bms-color-primary);
  font-size: 0.85em;
}

.bms-approval-progress__sign em {
  font-style: normal;
}

.bms-approval-progress__signed-panel {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm, 4px);
  margin-top: var(--bms-spacing-sm, 4px);
  padding: var(--bms-spacing-sm, 4px);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  font-size: 0.85em;
}

.bms-approval-progress__signed-item[data-handled='true'] {
  color: var(--bms-color-success);
}

.bms-approval-progress__summary {
  margin: var(--bms-spacing-sm, 4px) 0 0;
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}
</style>
