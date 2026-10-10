/** 预签名投影：把核心预签名能力基类 `BasePresignedUrl` 投影为组合式（获取 / 失效重取 / 降级）。 */
import { BasePresignedUrl } from '@bms/core';
import { ref } from 'vue';
/** 具体预签名（可实例化）。 */
class PresignedUrlState extends BasePresignedUrl {
}
/**
 * 使用预签名投影。
 *
 * @returns 预签名基类实例与响应式面。
 */
export function useBasePresignedUrl() {
    const presigned = new PresignedUrlState();
    const url = ref(presigned.url);
    const expiresAt = ref(presigned.expiresAt);
    function sync() {
        url.value = presigned.url;
        expiresAt.value = presigned.expiresAt;
    }
    return {
        presigned,
        url,
        expiresAt,
        setFetcher: (fetcher) => {
            presigned.fetcher = fetcher;
        },
        get: async () => {
            const next = await presigned.get();
            sync();
            return next;
        },
        refresh: () => {
            presigned.refresh();
            sync();
        },
        isExpired: (now) => presigned.isExpired(now),
    };
}
