/** 下载触发投影：把核心能力基类 `BaseFileDownload` 投影为组合式（取址 / 触发 / 失败重试）。 */
import { BaseFileDownload, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体下载触发件（可实例化）。 */
class FileDownload extends BaseFileDownload {
}
/**
 * 使用下载触发投影。
 *
 * @param options 选项。
 * @returns 下载基类实例与响应式面。
 */
export function useBaseFileDownload(options = {}) {
    const download = new FileDownload();
    if (options.trigger !== undefined) {
        download.trigger = options.trigger;
    }
    if (options.fetcher !== undefined) {
        download.fetcher = options.fetcher;
    }
    if (options.presigned !== undefined) {
        download.presigned = markRaw(toRaw(options.presigned));
    }
    const phase = ref(download.phase);
    const url = ref(download.url);
    const filename = ref(download.filename);
    const errorMessage = ref(download.errorMessage);
    const ready = ref(download.ready);
    const busy = ref(download.busy);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        phase.value = download.phase;
        url.value = download.url;
        filename.value = download.filename;
        errorMessage.value = download.errorMessage;
        ready.value = download.ready;
        busy.value = download.busy;
    };
    const off = download.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        download,
        phase,
        url,
        filename,
        errorMessage,
        ready,
        busy,
        setTrigger: (trigger) => {
            download.trigger = trigger;
            sync();
        },
        setFetcher: (fetcher) => {
            download.fetcher = fetcher;
            sync();
        },
        run: async (input) => {
            const result = await download.download(input);
            sync();
            return result;
        },
        retry: async () => {
            const result = await download.retry();
            sync();
            return result;
        },
        reset: () => {
            download.reset();
            sync();
        },
    };
}
