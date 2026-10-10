/** 审批流编排投影：把核心能力基类 `BaseApprovalFlow` 投影为组合式（并行取数 / 会签与进度 / 提交与幂等 / 错误码处置 / 只读图形态）。 */
import { BaseApprovalFlow, resolveApprovalActions, resolveProgressSummary, } from '@bms/core';
import { computed, markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体审批流编排件（可实例化）。 */
class ApprovalFlowState extends BaseApprovalFlow {
}
/**
 * 使用审批流编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBaseApprovalFlow(options = {}) {
    const approval = new ApprovalFlowState();
    if (options.instanceId !== undefined) {
        approval.setInstanceId(options.instanceId);
    }
    if (options.jobs !== undefined) {
        approval.setJobs(options.jobs);
    }
    if (options.access !== undefined) {
        approval.setAccess(markRaw(toRaw(options.access)));
    }
    if (options.notice !== undefined) {
        approval.setNotice(markRaw(toRaw(options.notice)));
    }
    if (options.presigned !== undefined) {
        approval.setPresigned(markRaw(toRaw(options.presigned)));
    }
    approval.setReady(options.ready ?? false);
    const ready = ref(approval.ready);
    const degraded = ref(approval.degraded);
    const disabled = ref(approval.disabled);
    const busy = ref(approval.busy);
    const phase = ref(approval.phase);
    const instance = ref(approval.instance);
    const records = ref(approval.records);
    const currentTask = ref(approval.currentTask);
    const instanceState = ref(approval.instanceState);
    const recordsState = ref(approval.recordsState);
    const errorMessage = ref(approval.errorMessage);
    const errorHandling = ref(approval.errorHandling);
    const pendingRefresh = ref(approval.pendingRefresh);
    const requestCount = ref(approval.requestCount);
    const diagramMode = ref(approval.diagramMode);
    const diagramXml = ref(approval.diagramXml);
    const diagramUrl = ref(approval.diagramUrl);
    const readonlyState = ref(approval.readonly);
    const canApprove = ref(approval.canApprove);
    const canWithdraw = ref(approval.canWithdraw);
    /** 从编排基类实例同步响应式面（集合面重建）。 */
    const sync = () => {
        ready.value = approval.ready;
        degraded.value = approval.degraded;
        disabled.value = approval.disabled;
        busy.value = approval.busy;
        phase.value = approval.phase;
        instance.value = approval.instance;
        records.value = approval.records;
        currentTask.value = approval.currentTask;
        instanceState.value = approval.instanceState;
        recordsState.value = approval.recordsState;
        errorMessage.value = approval.errorMessage;
        errorHandling.value = approval.errorHandling;
        pendingRefresh.value = approval.pendingRefresh;
        requestCount.value = approval.requestCount;
        diagramMode.value = approval.diagramMode;
        diagramXml.value = approval.diagramXml;
        diagramUrl.value = approval.diagramUrl;
        readonlyState.value = approval.readonly;
        canApprove.value = approval.canApprove;
        canWithdraw.value = approval.canWithdraw;
    };
    const off = approval.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    // 派生面必须读**响应式面**（核心基类字段非响应式；直接读实例会让 computed 首次求值后永久缓存）。
    const progress = computed(() => {
        const current = instance.value;
        if (current === undefined) {
            return { done: 0, total: 0, activeName: '' };
        }
        return resolveProgressSummary(current);
    });
    const actions = computed(() => resolveApprovalActions({
        status: instance.value?.status,
        canApprove: canApprove.value,
        canWithdraw: canWithdraw.value,
        hasTask: currentTask.value !== undefined,
        taskId: currentTask.value?.taskId,
    }));
    return {
        approval,
        ready,
        degraded,
        disabled,
        busy,
        phase,
        instance,
        records,
        currentTask,
        instanceState,
        recordsState,
        errorMessage,
        errorHandling,
        pendingRefresh,
        requestCount,
        diagramMode,
        diagramXml,
        diagramUrl,
        readonly: readonlyState,
        progress,
        actions,
        canApprove,
        canWithdraw,
        setReady: (value) => {
            approval.setReady(value);
            sync();
        },
        setInstanceId: (instanceId) => {
            approval.setInstanceId(instanceId);
            sync();
        },
        setJobs: (jobs) => {
            approval.setJobs(jobs);
            sync();
        },
        setAccess: (access) => {
            approval.setAccess(access === undefined ? undefined : markRaw(toRaw(access)));
            sync();
        },
        setPresigned: (presigned) => {
            approval.setPresigned(presigned === undefined ? undefined : markRaw(toRaw(presigned)));
            sync();
        },
        setNotice: (notice) => {
            approval.setNotice(notice === undefined ? undefined : markRaw(toRaw(notice)));
            sync();
        },
        setApprovable: (value) => {
            approval.approvable = value;
            sync();
        },
        setWithdrawable: (value) => {
            approval.withdrawable = value;
            sync();
        },
        applyInstance: (input) => {
            approval.applyInstance(input);
            sync();
        },
        applyRecords: (input) => {
            approval.applyRecords(input);
            sync();
        },
        applyTask: (input) => {
            approval.applyTask(input);
            sync();
        },
        load: async () => {
            const result = await approval.load();
            sync();
            return result;
        },
        reload: async () => {
            const result = await approval.reload();
            sync();
            return result;
        },
        loadDiagramImage: async () => {
            const result = await approval.loadDiagramImage();
            sync();
            return result;
        },
        markDiagramFailed: () => {
            approval.markDiagramFailed();
            sync();
        },
        idempotencyKey: (action, comment, target) => approval.idempotencyKey(action, comment, target),
        validate: (action, input) => approval.validate(action, input),
        submit: async (action, input) => {
            const result = await approval.submit(action, input);
            sync();
            return result;
        },
        retry: async () => {
            const result = await approval.retry();
            sync();
            return result;
        },
        reset: () => {
            approval.reset();
            sync();
        },
    };
}
