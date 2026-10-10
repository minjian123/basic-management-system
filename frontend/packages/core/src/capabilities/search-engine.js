/**
 * 检索引擎插件基类与提供者注册表：检索引擎为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseSearchEngine`，经 `SearchEngineRegistry` 登记接入；
 * 未登记 / 未注入时搜索能力即占位（不发请求）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 检索引擎插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseSearchEngine extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'search-engine';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 即时建议。
     *
     * @param input 关键词与限定域。
     * @returns 原始结果（缺省 `undefined`）。
     */
    suggest(input) {
        void input;
        return Promise.resolve(undefined);
    }
    /**
     * 全局检索。
     *
     * @param input 检索请求。
     * @returns 原始结果（缺省 `undefined`）。
     */
    searchGlobal(input) {
        void input;
        return Promise.resolve(undefined);
    }
    /**
     * 审计日志检索。
     *
     * @param input 检索请求。
     * @returns 原始结果（缺省 `undefined`）。
     */
    searchLogs(input) {
        void input;
        return Promise.resolve(undefined);
    }
    /**
     * 文件内容检索。
     *
     * @param input 检索请求。
     * @returns 原始结果（缺省 `undefined`）。
     */
    searchFiles(input) {
        void input;
        return Promise.resolve(undefined);
    }
}
/** 检索引擎注册项（工厂创建插件实例）。 */
export class SearchEngineProvider extends BaseProvider {
    /** 引擎键（如 `http`）。 */
    key;
    /** 引擎工厂。 */
    create;
    /**
     * 构造检索引擎注册项。
     *
     * @param key 引擎键。
     * @param create 引擎工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 检索引擎注册表（统一注册表基座；同键唯一性拒重）。 */
export class SearchEngineRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'search-engine-registry';
    /** 实现名。 */
    pluginName = 'core';
    /**
     * 注册项键。
     *
     * @param provider 注册项。
     * @returns 注册项键。
     */
    providerKey(provider) {
        return provider.key;
    }
}
