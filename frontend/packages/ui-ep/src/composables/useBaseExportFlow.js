/** 导出流投影：把核心能力基类 `BaseExportFlow` 投影为组合式（取数参数 / 范围 / 脱敏 / 同步与异步通路 / 进度与取消）。 */
import { BaseExportFlow, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体导出流件（可实例化）。 */
class ExportFlow extends BaseExportFlow {
}
/**
 * 使用导出流投影。
 *
 * @param options 选项。
 * @returns 导出流基类实例与响应式面。
 */
export function useBaseExportFlow(options = {}) {
    const flow = new ExportFlow();
    if (options.biz !== undefined) {
        flow.setBiz(options.biz, options.bizName);
    }
    if (options.params !== undefined) {
        flow.setParams(options.params);
    }
    if (options.scope !== undefined || options.selectedIds !== undefined) {
        flow.setScope(options.scope ?? 'filtered', options.selectedIds);
    }
    if (options.asyncThreshold !== undefined) {
        flow.setThreshold(options.asyncThreshold);
    }
    if (options.total !== undefined) {
        flow.setTotal(options.total);
    }
    if (options.plain !== undefined) {
        flow.setPlain(options.plain);
    }
    if (options.filenamePrefix !== undefined) {
        flow.filenamePrefix = options.filenamePrefix;
    }
    if (options.jobs !== undefined) {
        flow.jobs = options.jobs;
    }
    if (options.task !== undefined) {
        flow.task = markRaw(toRaw(options.task));
    }
    if (options.download !== undefined) {
        flow.download = markRaw(toRaw(options.download));
    }
    if (options.access !== undefined) {
        flow.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        flow.notice = markRaw(toRaw(options.notice));
    }
    flow.setDisabled(options.disabled ?? false);
    flow.setReady(options.ready ?? false);
    const ready = ref(flow.ready);
    const degraded = ref(flow.degraded);
    const busy = ref(flow.busy);
    const phase = ref(flow.phase);
    const progress = ref({ ...flow.progress });
    const canExport = ref(flow.canExport);
    const asyncMode = ref(flow.asyncMode);
    const empty = ref(flow.empty);
    const exportReady = ref(flow.exportReady);
    const plainAllowed = ref(flow.plainAllowed);
    const lastResult = ref(flow.lastResult);
    const plan = ref(flow.plan);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = flow.ready;
        degraded.value = flow.degraded;
        busy.value = flow.busy;
        phase.value = flow.phase;
        progress.value = { ...flow.progress };
        canExport.value = flow.canExport;
        asyncMode.value = flow.asyncMode;
        empty.value = flow.empty;
        exportReady.value = flow.exportReady;
        plainAllowed.value = flow.plainAllowed;
        lastResult.value = flow.lastResult;
        plan.value = flow.plan;
    };
    const off = flow.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        flow,
        ready,
        degraded,
        busy,
        phase,
        progress,
        canExport,
        asyncMode,
        empty,
        exportReady,
        plainAllowed,
        lastResult,
        plan,
        setReady: (value) => {
            flow.setReady(value);
            sync();
        },
        setBiz: (biz, bizName) => {
            flow.setBiz(biz, bizName);
            sync();
        },
        setParams: (params) => {
            flow.setParams(params);
            sync();
        },
        setScope: (scope, selectedIds) => {
            flow.setScope(scope, selectedIds);
            sync();
        },
        setSelected: (ids) => {
            flow.setSelected(ids);
            sync();
        },
        setTotal: (total) => {
            flow.setTotal(total);
            sync();
        },
        setPlain: (plain) => {
            flow.setPlain(plain);
            sync();
        },
        setThreshold: (threshold) => {
            flow.setThreshold(threshold);
            sync();
        },
        setDisabled: (disabled) => {
            flow.setDisabled(disabled);
            sync();
        },
        setJobs: (jobs) => {
            flow.jobs = jobs;
            sync();
        },
        run: async () => {
            const value = await flow.export();
            sync();
            return value;
        },
        cancel: () => {
            flow.cancel();
            sync();
        },
        retry: async () => {
            const value = await flow.retry();
            sync();
            return value;
        },
        reset: () => {
            flow.reset();
            sync();
        },
    };
}
