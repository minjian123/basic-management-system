/**
 * AI 流式插件基类与提供者注册表：AI 流式通道为**可替换实现（纵向）**——
 * 内建 SSE 实现继承 `BaseAiStream`，经 `AiStreamRegistry` 登记接入；
 * 未登记 / 未注入时 AI 能力即占位（不发请求）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** AI 流式插件基类（抽象；方法与 `AiStreamAdapter` 契约一致）。 */
export class BaseAiStream extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'ai-stream';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
}
/** AI 流式注册项（工厂创建插件实例）。 */
export class AiStreamProvider extends BaseProvider {
    /** 流式键（如 `sse`）。 */
    key;
    /** 流式工厂。 */
    create;
    /**
     * 构造 AI 流式注册项。
     *
     * @param key 流式键。
     * @param create 流式工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** AI 流式注册表（统一注册表基座；同键唯一性拒重）。 */
export class AiStreamRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'ai-stream-registry';
    /** 实现名。 */
    pluginName = 'core';
    /**
     * 注册项键。
     *
     * @param provider 注册项。
     */
    providerKey(provider) {
        return provider.key;
    }
}
