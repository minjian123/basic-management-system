/** 文件上传族投影：把核心组件基类 `BaseFileUpload` 与上传引擎 / 预签名投影为组合式（列表 / 校验 / 上传 / 回显 / 预览下载）。 */
import { BaseFileUpload, BasePresignedUrl, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
import { useBaseUploadEngine } from './useBaseUploadEngine';
/** 具体文件上传族（可实例化）。 */
class FileUploadState extends BaseFileUpload {
}
/** 具体预签名（可实例化）。 */
class PresignedState extends BasePresignedUrl {
}
/**
 * 使用文件上传族投影。
 *
 * @param options 选项。
 * @returns 文件族实例与响应式面。
 */
export function useBaseFileUpload(options = {}) {
    const upload = new FileUploadState();
    const presigned = options.presigned ?? new PresignedState();
    const localDisabled = ref(options.disabled ?? false);
    const engine = useBaseUploadEngine({
        ...(options.transport === undefined ? {} : { transport: options.transport }),
        presigned,
        ...(options.partSize === undefined ? {} : { chunkSize: options.partSize }),
        config: {
            ...(options.partSize === undefined ? {} : { partSize: options.partSize }),
            ...(options.wholeMaxSize === undefined ? {} : { wholeMaxSize: options.wholeMaxSize }),
            ...(options.maxSize === undefined ? {} : { maxFileSize: options.maxSize }),
            ...(options.concurrency === undefined ? {} : { concurrency: options.concurrency }),
            ...(options.autoDedup === undefined ? {} : { autoDedup: options.autoDedup }),
        },
    });
    // 预签名取址器：经通路预签名接口（未覆写时不请求，回落已有地址）
    if (options.presigned === undefined && options.transport?.presign !== undefined) {
        presigned.fetcher = async (input) => {
            const raw = (await options.transport?.presign?.({
                fileId: input?.key ?? '',
                purpose: 'preview',
            }));
            const url = typeof raw?.url === 'string' ? raw.url : '';
            const expiresIn = typeof raw?.expires_in === 'number' ? raw.expires_in : 3600;
            return { url, expiresAt: url === '' ? 0 : Date.now() + expiresIn * 1000 };
        };
    }
    upload.setEngine(engine.engine);
    upload.setPresigned(presigned);
    upload.setOptions({
        ready: options.ready ?? false,
        ...(options.kind === undefined ? {} : { kind: options.kind }),
        ...(options.multiple === undefined ? {} : { multiple: options.multiple }),
        ...(options.limit === undefined ? {} : { limit: options.limit }),
        ...(options.accept === undefined ? {} : { accept: options.accept }),
        ...(options.maxSize === undefined ? {} : { maxSize: options.maxSize }),
        ...(options.wholeMaxSize === undefined ? {} : { wholeMaxSize: options.wholeMaxSize }),
        ...(options.compress === undefined ? {} : { compress: options.compress }),
        ...(options.crop === undefined ? {} : { crop: options.crop }),
        ...(options.cropShape === undefined ? {} : { cropShape: options.cropShape }),
        ...(options.cropAspect === undefined ? {} : { cropAspect: options.cropAspect }),
        ...(options.imageOptions === undefined ? {} : { imageOptions: options.imageOptions }),
        ...(options.draggable === undefined ? {} : { draggable: options.draggable }),
        ...(options.readonlyView === undefined ? {} : { readonlyView: options.readonlyView }),
    });
    if (options.transport !== undefined) {
        upload.setTransport(options.transport);
    }
    if (options.value !== undefined) {
        upload.setValue(options.value);
    }
    const ready = ref(upload.ready);
    const degraded = ref(upload.degraded);
    const requestCount = ref(upload.requestCount);
    const value = ref(upload.value);
    const refs = ref([...upload.refs]);
    const limitExceeded = ref(upload.limitExceeded);
    const fileError = ref(upload.fileError);
    const errorCode = ref(upload.errorCode);
    const errorMessage = ref(upload.errorMessage);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = upload.ready;
        degraded.value = upload.degraded;
        requestCount.value = upload.requestCount;
        value.value = upload.value;
        refs.value = [...upload.refs];
        limitExceeded.value = upload.limitExceeded;
        fileError.value = upload.fileError;
        errorCode.value = upload.errorCode;
        errorMessage.value = upload.errorMessage;
    }
    const off = upload.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offValue = upload.onChange(() => sync());
    onScopeDispose(() => {
        off();
        offValue();
        upload.dispose();
    });
    const disabled = computed(() => localDisabled.value || !ready.value);
    const selectedIds = computed(() => upload.selectedIds);
    const empty = computed(() => refs.value.length === 0 && !engine.busy.value);
    const error = computed(() => errorCode.value !== undefined);
    const errorText = computed(() => errorMessage.value);
    return {
        upload,
        engine,
        ready,
        degraded,
        disabled,
        requestCount,
        value,
        refs,
        selectedIds,
        tasks: engine.tasks,
        busy: engine.busy,
        totalPercent: engine.totalPercent,
        empty,
        limitExceeded,
        fileError,
        error,
        errorCode,
        errorMessage,
        errorText,
        setReady: (next) => upload.setReady(next),
        setOptions: (next) => upload.setOptions(next),
        setTransport: (next) => upload.setTransport(next),
        setValue: (next) => upload.setValue(next),
        syncValue: (next) => {
            upload.setValue(next);
            sync();
            if (upload.selectedIds.length > 0) {
                void upload.resolveFiles();
            }
        },
        acceptFiles: (inputs) => upload.acceptFiles(inputs),
        retryTask: (taskId) => upload.retryTask(taskId),
        cancelTask: (taskId) => upload.cancelTask(taskId),
        remove: (id) => upload.remove(id),
        clearFiles: () => upload.clearFiles(),
        moveFile: (from, to) => upload.moveFile(from, to),
        resolveFiles: (ids) => upload.resolveFiles(ids),
        previewUrlOf: (id) => upload.previewUrlOf(id),
        downloadFile: (id) => upload.downloadFile(id),
        labelOf: (id) => upload.labelOf(id),
        mergeRefs: (next) => upload.mergeRefs(next),
        taskOfFile: (id) => upload.taskOfFile(id),
        summary: () => upload.summary(),
        onValueChange: (listener) => upload.onChange(listener),
    };
}
