/** 审批动作元数据（件层共用）：文案 / 按钮类型 / 是否危险 / 意见与目标是否必填 / 二次确认文案。 */
/** 审批动作元数据表。 */
export const APPROVAL_ACTION_METAS = [
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
];
/**
 * 取动作元数据。
 *
 * @param action 动作键。
 * @returns 动作元数据。
 */
export function approvalActionMeta(action) {
    return APPROVAL_ACTION_METAS.find((item) => item.key === action);
}
