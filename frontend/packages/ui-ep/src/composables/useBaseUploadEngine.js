/** 上传引擎投影：把核心上传引擎能力基类 `BaseUploadEngine` 投影为组合式（进度 / 任务 / 通路 / 分片）。 */
import { BasePresignedUrl, BaseUploadEngine, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体上传引擎（可实例化）。 */
class UploadEngine extends BaseUploadEngine {
}
/**
 * 使用上传引擎投影。
 *
 * @param options 选项。
 * @returns 上传引擎基类实例与响应式面。
 */
export function useBaseUploadEngine(options = {}) {
    const engine = new UploadEngine();
    if (options.chunkSize !== undefined) {
        engine.chunkSize = options.chunkSize;
    }
    if (options.maxSize !== undefined) {
        engine.maxSize = options.maxSize;
    }
    if (options.config !== undefined) {
        engine.setConfig(options.config);
    }
    if (options.ready !== undefined) {
        engine.setReady(options.ready);
    }
    if (options.transport !== undefined) {
        engine.setTransport(options.transport);
    }
    if (options.presigned !== undefined) {
        engine.setPresigned(options.presigned);
    }
    const progress = ref(engine.progress);
    const ready = ref(engine.ready);
    const degraded = ref(engine.degraded);
    const requestCount = ref(engine.requestCount);
    const tasks = ref([...engine.tasks]);
    const totalPercent = ref(engine.totalPercent);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        progress.value = engine.progress;
        ready.value = engine.ready;
        degraded.value = engine.degraded;
        requestCount.value = engine.requestCount;
        tasks.value = [...engine.tasks];
        totalPercent.value = engine.totalPercent;
    }
    const off = engine.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        engine.dispose();
    });
    const busy = computed(() => tasks.value.some((task) => task.phase === 'pending' || task.phase === 'hashing' || task.phase === 'uploading' || task.phase === 'merging'));
    const canUpload = computed(() => ready.value && engine.transport !== undefined);
    return {
        engine,
        progress,
        ready,
        degraded,
        requestCount,
        tasks,
        busy,
        totalPercent,
        canUpload,
        setReady: (value) => engine.setReady(value),
        setTransport: (transport) => engine.setTransport(transport),
        setPresigned: (presigned) => engine.setPresigned(presigned),
        setConfig: (input) => engine.setConfig(input),
        enqueue: (input) => engine.enqueue(input),
        start: (taskId) => engine.start(taskId),
        retry: (taskId) => engine.retry(taskId),
        cancelTask: (taskId) => engine.cancel(taskId),
        remove: (taskId) => engine.remove(taskId),
        taskOf: (taskId) => engine.taskOf(taskId),
        upload: async (file) => {
            const key = await engine.upload(file);
            sync();
            return key;
        },
        cancel: () => {
            engine.cancel();
            sync();
        },
    };
}
