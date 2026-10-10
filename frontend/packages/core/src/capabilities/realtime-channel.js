/**
 * 实时通道插件基类与提供者注册表：实时通道为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseRealtimeChannel`，经 `RealtimeChannelRegistry` 登记接入；
 * 未登记 / 未注入时通知能力即轮询占位（不发请求）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 实时通道插件基类（抽象；方法与 `NotificationRealtimeAdapter` 契约一致）。 */
export class BaseRealtimeChannel extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'realtime-channel';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
}
/** 实时通道注册项（工厂创建插件实例）。 */
export class RealtimeChannelProvider extends BaseProvider {
    /** 通道键（如 `socket.io`）。 */
    key;
    /** 通道工厂。 */
    create;
    /**
     * 构造实时通道注册项。
     *
     * @param key 通道键。
     * @param create 通道工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 实时通道注册表（统一注册表基座；同键唯一性拒重）。 */
export class RealtimeChannelRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'realtime-channel-registry';
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
