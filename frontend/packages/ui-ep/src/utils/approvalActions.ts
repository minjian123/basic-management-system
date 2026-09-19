/** 审批动作元数据（件层共用）：文案 / 按钮类型 / 是否危险 / 意见与目标是否必填 / 二次确认文案。 */

import type { ApprovalAction } from '@bms/core'

/** 动作元数据。 */
export interface ApprovalActionMeta {
  /** 动作键。 */
  key: ApprovalAction
  /** 按钮文案。 */
  label: string
  /** 按钮类型（主操作 / 危险 / 默认）。 */
  variant: 'primary' | 'danger' | 'default'
  /** 是否危险（危险确认）。 */
  danger: boolean
  /** 意见是否必填。 */
  commentRequired: boolean
  /** 意见是否展示。 */
  commentVisible: boolean
  /** 目标是否必填（驳回退回节点 / 转办对象）。 */
  targetRequired: boolean
  /** 目标选择形态（退回节点 / 转办对象）。 */
  targetKind: 'return-node' | 'transfer-user' | 'none'
  /** 二次确认形态（弹窗表单 / 危险确认 / 不需确认）。 */
  confirm: 'form' | 'confirm' | 'none'
  /** 二次确认标题。 */
  confirmTitle: string
  /** 二次确认正文。 */
  confirmContent: string
}

/** 审批动作元数据表。 */
export const APPROVAL_ACTION_METAS: readonly ApprovalActionMeta[] = [
  {
    key: 'approve',
    label: '同意',
    variant: 'primary',
    danger: false,
    commentRequired: false,
    commentVisible: true,
    targetRequired: false,
    targetKind: 'none',
    confirm: 'none',
    confirmTitle: '确认同意',
    confirmContent: '确认同意该审批？',
  },
  {
    key: 'reject',
    label: '驳回',
    variant: 'danger',
    danger: true,
    commentRequired: true,
    commentVisible: true,
    targetRequired: false,
    targetKind: 'return-node',
    confirm: 'form',
    confirmTitle: '确认驳回',
    confirmContent: '驳回后流程将退回至所选节点（缺省退回上一节点）',
  },
  {
    key: 'transfer',
    label: '转办',
    variant: 'default',
    danger: false,
    commentRequired: false,
    commentVisible: true,
    targetRequired: true,
    targetKind: 'transfer-user',
    confirm: 'form',
    confirmTitle: '转办审批',
    confirmContent: '转办后本人不再持有该待办',
  },
  {
    key: 'withdraw',
    label: '撤回',
    variant: 'danger',
    danger: true,
    commentRequired: false,
    commentVisible: true,
    targetRequired: false,
    targetKind: 'none',
    confirm: 'confirm',
    confirmTitle: '确认撤回',
    confirmContent: '撤回后流程实例将终止',
  },
  {
    key: 'comment',
    label: '评论',
    variant: 'default',
    danger: false,
    commentRequired: true,
    commentVisible: true,
    targetRequired: false,
    targetKind: 'none',
    confirm: 'none',
    confirmTitle: '添加评论',
    confirmContent: '评论仅留痕，不推进流程',
  },
]

/**
 * 取动作元数据。
 *
 * @param action 动作键。
 * @returns 动作元数据。
 */
export function approvalActionMeta(action: ApprovalAction): ApprovalActionMeta {
  return APPROVAL_ACTION_METAS.find((item) => item.key === action) as ApprovalActionMeta
}
