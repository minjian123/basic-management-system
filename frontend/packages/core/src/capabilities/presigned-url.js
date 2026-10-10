/**
 * 预签名能力基类：获取 / 按文件标识缓存 / 提前刷新 / 失效重取一次 / 并发合并 / 降级策略
 * （获取器由宿主注入，未注入即占位不请求）。
 *
 * **兼容**：无 key 的 `get()` / `refresh()` / `isExpired()` 保持既有单 URL 语义（文件预览 `07_03`、
 * 审批只读图 `08_08`、下载触发 `BaseFileDownload` 调用逐字不变）；带 key 的调用走 keyed 缓存。
 * 核心不触 DOM、不发请求。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 预签名能力基类（抽象）。 */
export class BasePresignedUrl extends BaseComponent {
    /** 能力键。 */
    identifier = 'presigned-url';
    /** 当前 URL（无 key 单 URL 语义）。 */
    url;
    /** 过期时间戳（毫秒）。 */
    expiresAt = 0;
    /** URL 获取器（未注入则按占位返回已有值）。 */
    fetcher;
    /** 缺省提前刷新阈值（秒）。 */
    defaultRefreshAhead = 300;
    /** 缺省降级策略（声明，供消费方回退）。 */
    fallback = 'download';
    /** keyed 缓存（文件标识 → 签名结果）。 */
    entries = new Map();
    /** keyed 在途取址（同 key 并发合并）。 */
    pending = new Map();
    /** keyed 缓存条数。 */
    get cacheSize() {
        return this.entries.size;
    }
    /**
     * 获取可用 URL。
     *
     * 无 key：既有单 URL 语义（有效则复用；未注入获取器则降级返回已有值）。
     * 带 key：keyed 缓存命中直接返回；否则取址（同 key 并发合并、失败重试一次）。
     *
     * @param key 文件标识（可选）。
     * @param options 取址选项（可选）。
     * @returns URL；不可用返回 `undefined`。
     */
    async get(key, options) {
        if (key === undefined || key === '') {
            if (this.url !== undefined && !this.isExpired()) {
                return this.url;
            }
            if (this.fetcher === undefined) {
                return this.url;
            }
            const result = await this.fetchOnce();
            if (result === undefined) {
                return undefined;
            }
            this.url = result.url;
            this.expiresAt = result.expiresAt;
            return this.url;
        }
        const resolved = await this.resolve(key, options);
        return resolved?.url;
    }
    /**
     * 取址（keyed；含提前刷新判定、并发合并与失败重试一次）。
     *
     * @param key 文件标识。
     * @param options 取址选项（可选）。
     * @returns 取址结果；不可用返回 `undefined`。
     */
    async resolve(key, options) {
        const refreshAhead = options?.refreshAhead ?? this.defaultRefreshAhead;
        const cached = this.entries.get(key);
        if (cached !== undefined && !this.isEntryStale(cached, refreshAhead)) {
            return { ...cached };
        }
        const inflight = this.pending.get(key);
        if (inflight !== undefined) {
            return inflight;
        }
        const task = this.fetchKeyed(key, options).finally(() => {
            this.pending.delete(key);
        });
        this.pending.set(key, task);
        return task;
    }
    /**
     * 清除缓存（无 key 清单 URL 缓存；带 key 清该键）。
     *
     * @param key 文件标识（可选）。
     */
    refresh(key) {
        if (key === undefined || key === '') {
            this.url = undefined;
            this.expiresAt = 0;
            return;
        }
        this.entries.delete(key);
    }
    /**
     * 清空全部缓存（单 URL + keyed）。
     */
    clear() {
        this.url = undefined;
        this.expiresAt = 0;
        this.entries.clear();
        this.pending.clear();
    }
    /**
     * 是否已过期（无 key 判单 URL；带 key 判该键）。
     *
     * @param now 当前时间戳（缺省 `Date.now()`）。
     * @param key 文件标识（可选）。
     * @returns 是否过期。
     */
    isExpired(now = Date.now(), key) {
        if (key === undefined || key === '') {
            return this.expiresAt > 0 && now >= this.expiresAt;
        }
        const entry = this.entries.get(key);
        return entry !== undefined && entry.expiresAt > 0 && now >= entry.expiresAt;
    }
    /**
     * 取址（无 key；失败重试一次）。
     *
     * @returns 取址结果；不可用返回 `undefined`。
     */
    async fetchOnce() {
        const fetcher = this.fetcher;
        if (fetcher === undefined) {
            return undefined;
        }
        try {
            return await fetcher();
        }
        catch {
            try {
                return await fetcher();
            }
            catch {
                return undefined;
            }
        }
    }
    /**
     * 取址（带 key；失败重试一次并写缓存）。
     *
     * @param key 文件标识。
     * @param options 取址选项。
     * @returns 取址结果；不可用返回 `undefined`。
     */
    async fetchKeyed(key, options) {
        const fetcher = this.fetcher;
        if (fetcher === undefined) {
            return undefined;
        }
        const input = { key, purpose: options?.purpose ?? 'get' };
        let result;
        try {
            result = await fetcher(input);
        }
        catch {
            try {
                result = await fetcher(input);
            }
            catch {
                result = undefined;
            }
        }
        if (result === undefined || result.url === '') {
            return undefined;
        }
        this.entries.set(key, { url: result.url, expiresAt: result.expiresAt });
        this.notifyLifecycle('update');
        return { ...result };
    }
    /**
     * 缓存条目是否陈旧（提前刷新阈值内视为将过期）。
     *
     * @param entry 缓存条目。
     * @param refreshAhead 提前刷新阈值（秒）。
     * @returns 是否陈旧。
     */
    isEntryStale(entry, refreshAhead) {
        if (entry.expiresAt <= 0) {
            return false;
        }
        return Date.now() >= entry.expiresAt - refreshAhead * 1000;
    }
}
