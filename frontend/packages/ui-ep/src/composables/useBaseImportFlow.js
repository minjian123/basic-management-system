/** 导入流投影：把核心能力基类 `BaseImportFlow` 投影为组合式（文件校验 / 幂等键 / 阶段与进度 / 错误行报告 / 下载）。 */
import { BaseImportFlow, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体导入流件（可实例化）。 */
class ImportFlow extends BaseImportFlow {
}
/**
 * 使用导入流投影。
 *
 * @param options 选项。
 * @returns 导入流基类实例与响应式面。
 */
export function useBaseImportFlow(options = {}) {
    const flow = new ImportFlow();
    if (options.accept !== undefined) {
        flow.accept = options.accept;
    }
    if (options.maxSize !== undefined) {
        flow.maxSize = options.maxSize;
    }
    flow.templateParams = options.templateParams;
    flow.successAutoClose = options.successAutoClose ?? false;
    if (options.biz !== undefined) {
        flow.setBiz(options.biz, options.bizName);
    }
    if (options.jobs !== undefined) {
        flow.jobs = options.jobs;
    }
    if (options.engine !== undefined) {
        flow.engine = markRaw(toRaw(options.engine));
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
    flow.setReady(options.ready ?? false);
    const ready = ref(flow.ready);
    const degraded = ref(flow.degraded);
    const busy = ref(flow.busy);
    const phase = ref(flow.phase);
    const step = ref(flow.step);
    const progress = ref(flow.progress);
    const idempotencyKey = ref(flow.idempotencyKey);
    const fileMeta = ref(flow.fileMeta);
    const hasFile = ref(flow.file !== undefined);
    const fileError = ref(flow.fileError);
    const errorMessage = ref(flow.errorMessage);
    const result = ref(flow.result);
    const errorRows = ref(flow.errorRows);
    const errorPage = ref(flow.errorPage);
    const errorPageCount = ref(flow.errorPageCount);
    const errorTruncated = ref(flow.errorTruncated);
    const summary = ref(flow.summary);
    const canImport = ref(flow.canImport);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = flow.ready;
        degraded.value = flow.degraded;
        busy.value = flow.busy;
        phase.value = flow.phase;
        step.value = flow.step;
        progress.value = flow.progress;
        idempotencyKey.value = flow.idempotencyKey;
        fileMeta.value = flow.fileMeta;
        hasFile.value = flow.file !== undefined;
        fileError.value = flow.fileError;
        errorMessage.value = flow.errorMessage;
        result.value = flow.result;
        errorRows.value = flow.errorRows;
        errorPage.value = flow.errorPage;
        errorPageCount.value = flow.errorPageCount;
        errorTruncated.value = flow.errorTruncated;
        summary.value = flow.summary;
        canImport.value = flow.canImport;
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
        step,
        progress,
        idempotencyKey,
        fileMeta,
        hasFile,
        fileError,
        errorMessage,
        result,
        errorRows,
        errorPage,
        errorPageCount,
        errorTruncated,
        summary,
        canImport,
        setReady: (value) => {
            flow.setReady(value);
            sync();
        },
        setBiz: (biz, bizName) => {
            flow.setBiz(biz, bizName);
            sync();
        },
        setJobs: (jobs) => {
            flow.jobs = jobs;
            sync();
        },
        selectFile: (file, meta) => {
            const applied = flow.selectFile(file, meta);
            sync();
            return applied;
        },
        clearFile: () => {
            flow.clearFile();
            sync();
        },
        setErrorPage: (page) => {
            flow.setErrorPage(page);
            sync();
        },
        submit: async () => {
            const value = await flow.submit();
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
        downloadTemplate: async () => {
            const value = await flow.downloadTemplate();
            sync();
            return value;
        },
        downloadErrors: async () => {
            const value = await flow.downloadErrors();
            sync();
            return value;
        },
    };
}
