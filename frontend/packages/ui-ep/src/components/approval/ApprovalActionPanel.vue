<script setup lang="ts">
// 审批操作面板件（08_8_1）：按可用动作矩阵渲染同意 / 驳回 / 转办 / 撤回 / 评论；意见与目标必填校验 + 码点长度提示 + 只读态禁用。
import {
  APPROVAL_COMMENT_REQUIRED_TEXT,
  APPROVAL_COMMENT_TOO_LONG_TEXT,
  APPROVAL_NO_TASK_TEXT,
  APPROVAL_READONLY_TEXT,
  APPROVAL_TARGET_REQUIRED_TEXT,
  countCodePoints,
  validateAction,
  type ApprovalAction,
  type ApprovalTaskInput,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseApprovalFlow } from '../../composables/useBaseApprovalFlow'
import { approvalActionMeta } from '../../utils/approvalActions'

/** 操作载荷。 */
export interface ApprovalPanelPayload {
  /** 动作。 */
  action: ApprovalAction
  /** 任务标识。 */
  taskId?: string
  /** 意见。 */
  comment?: string
  /** 目标（驳回退回节点 / 转办对象）。 */
  target?: string
}

interface Props {
  /** 可用动作矩阵。 */
  actions: { approve: boolean; reject: boolean; transfer: boolean; withdraw: boolean; comment: boolean }
  /** 当前待办任务（按装载输入口径，可省略字段）。 */
  currentTask?: ApprovalTaskInput
  /** 只读（实例结束 / 异常）。 */
  readonly?: boolean
  /** 提交中。 */
  submitting?: boolean
  /** 意见长度上限（Unicode 码点；缺省 4000）。 */
  commentMax?: number
  /** 可退回节点（驳回选择）。 */
  returnableNodes?: readonly { nodeId: string; name: string }[]
  /** 转办候选审批人。 */
  transferCandidates?: readonly { id: string; name: string }[]
}

const props = withDefaults(defineProps<Props>(), {
  currentTask: undefined,
  readonly: false,
  submitting: false,
  commentMax: 4000,
  returnableNodes: () => [],
  transferCandidates: () => [],
})

const emit = defineEmits<{
  action: [payload: ApprovalPanelPayload]
  cancel: []
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { approval } = useBaseApprovalFlow()

/** 意见草稿（受控件未接 `v-model` 时按本地草稿即时渲染）。 */
const comment = ref('')
/** 目标选择（驳回退回节点 / 转办对象）。 */
const target = ref('')
/** 当前动作（决定意见是否必填）。 */
const currentAction = ref<ApprovalAction>('approve')
/** 内联错误文案。 */
const errorText = ref('')

/** 意见码点数。 */
const commentLength = computed(() => countCodePoints(comment.value))

/** 是否超过长度上限。 */
const tooLong = computed(() => commentLength.value > props.commentMax)

/** 是否有可用动作。 */
const hasAction = computed(() => Object.values(props.actions).some((value) => value))

/**
 * 任务是否缺失（无待办时审批类动作不可用）。
 *
 * @returns 是否无待办。
 */
const noTask = computed(() => props.currentTask === undefined && props.actions.approve === false)

/**
 * 取动作元数据。
 *
 * @param action 动作。
 * @returns 元数据。
 */
function metaOf(action: ApprovalAction): ReturnType<typeof approvalActionMeta> {
  return approvalActionMeta(action)
}

/**
 * 点击动作：先记录当前动作与校验，再上抛（保留事件轨）。
 *
 * @param action 动作。
 */
function onClick(action: ApprovalAction): void {
  currentAction.value = action
  errorText.value = ''
  const meta = metaOf(action)
  if (meta.commentRequired && comment.value.trim() === '') {
    errorText.value = APPROVAL_COMMENT_REQUIRED_TEXT
    return
  }
  if (meta.targetRequired && target.value.trim() === '') {
    errorText.value = APPROVAL_TARGET_REQUIRED_TEXT
    return
  }
  if (tooLong.value) {
    errorText.value = APPROVAL_COMMENT_TOO_LONG_TEXT
    return
  }
  const check = validateAction(action, {
    comment: comment.value,
    target: target.value,
    canApprove: props.actions.approve,
    canWithdraw: props.actions.withdraw,
    hasTask: props.currentTask !== undefined,
  })
  if (!check.valid) {
    errorText.value = check.message
    return
  }
  emit('action', {
    action,
    taskId: props.currentTask?.taskId,
    comment: comment.value === '' ? undefined : comment.value,
    target: target.value === '' ? undefined : target.value,
  })
}

watch(
  () => props.readonly,
  () => {
    errorText.value = ''
  },
)

// 说明：`approval` 仅为挂链（件层以投影组合式接入继承链）。
void approval

defineExpose({ comment, target, errorText, onClick })
</script>

<template>
  <div
    class="bms-approval-actions"
    data-test="approval-action-panel"
    :data-readonly="readonly || undefined"
    :data-submitting="submitting || undefined"
  >
    <slot name="extra" :disabled="readonly || submitting" />

    <div v-if="readonly" class="bms-approval-actions__readonly" data-test="readonly-tip">
      {{ APPROVAL_READONLY_TEXT }}
    </div>
    <div v-else-if="noTask" class="bms-approval-actions__hint" data-test="no-task">
      {{ APPROVAL_NO_TASK_TEXT }}
    </div>

    <label v-if="!readonly && hasAction" class="bms-approval-actions__comment">
      <textarea
        v-model="comment"
        class="bms-approval-actions__input"
        data-test="comment-input"
        :disabled="submitting"
        :placeholder="`审批意见（最多 ${commentMax} 字）`"
        rows="3"
      />
      <span class="bms-approval-actions__count" :data-over="tooLong || undefined">
        {{ commentLength }} / {{ commentMax }}
      </span>
    </label>

    <label v-if="!readonly && currentAction === 'reject' && returnableNodes.length > 0" class="bms-approval-actions__target">
      <select v-model="target" data-test="reject-target" :disabled="submitting">
        <option value="">退回上一节点</option>
        <option v-for="node in returnableNodes" :key="node.nodeId" :value="node.nodeId">{{ node.name }}</option>
      </select>
    </label>

    <label v-if="!readonly && currentAction === 'transfer'" class="bms-approval-actions__target">
      <select v-model="target" data-test="transfer-target" :disabled="submitting">
        <option value="">请选择转办对象</option>
        <option v-for="candidate in transferCandidates" :key="candidate.id" :value="candidate.id">
          {{ candidate.name }}
        </option>
      </select>
    </label>

    <div v-if="!readonly && hasAction" class="bms-approval-actions__buttons">
      <slot name="buttons" :submitting="submitting">
        <button
          v-if="actions.approve"
          type="button"
          class="bms-approval-actions__button bms-approval-actions__button--primary"
          data-test="approve"
          :disabled="submitting"
          @click="onClick('approve')"
        >
          同意
        </button>
        <button
          v-if="actions.reject"
          type="button"
          class="bms-approval-actions__button bms-approval-actions__button--danger"
          data-test="reject"
          :disabled="submitting"
          @click="onClick('reject')"
        >
          驳回
        </button>
        <button
          v-if="actions.transfer"
          type="button"
          class="bms-approval-actions__button"
          data-test="transfer"
          :disabled="submitting"
          @click="onClick('transfer')"
        >
          转办
        </button>
        <button
          v-if="actions.withdraw"
          type="button"
          class="bms-approval-actions__button bms-approval-actions__button--danger"
          data-test="withdraw"
          :disabled="submitting"
          @click="onClick('withdraw')"
        >
          撤回
        </button>
        <button
          v-if="actions.comment"
          type="button"
          class="bms-approval-actions__button"
          data-test="comment"
          :disabled="submitting"
          @click="onClick('comment')"
        >
          评论
        </button>
      </slot>
    </div>

    <p v-if="errorText !== ''" class="bms-approval-actions__error" data-test="comment-error">{{ errorText }}</p>
    <p v-if="submitting" class="bms-approval-actions__loading" data-test="submit-loading">提交中…</p>
  </div>
</template>

<style scoped>
.bms-approval-actions {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-approval-actions__comment {
  display: flex;
  flex-direction: column;
}

.bms-approval-actions__input {
  padding: 4px 6px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  font: inherit;
  resize: vertical;
}

.bms-approval-actions__count {
  align-self: flex-end;
  color: var(--bms-color-text-secondary);
  font-size: 0.8em;
}

.bms-approval-actions__count[data-over='true'] {
  color: var(--bms-color-danger);
}

.bms-approval-actions__target select {
  padding: 4px 6px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  font: inherit;
}

.bms-approval-actions__buttons {
  display: flex;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-approval-actions__button {
  padding: 4px 12px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-approval-actions__button--primary {
  border-color: var(--bms-color-primary);
  background: var(--bms-color-primary);
  color: var(--bms-color-white);
}

.bms-approval-actions__button--danger {
  border-color: var(--bms-color-danger);
  color: var(--bms-color-danger);
}

.bms-approval-actions__button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-approval-actions__error {
  margin: 0;
  color: var(--bms-color-danger);
  font-size: 0.85em;
}

.bms-approval-actions__hint,
.bms-approval-actions__readonly,
.bms-approval-actions__loading {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}
</style>
