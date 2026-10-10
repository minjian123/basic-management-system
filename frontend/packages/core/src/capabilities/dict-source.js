/**
 * 字典数据源插件基类与提供者注册表：字典数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseDictSource`，经 `DictSourceRegistry` 登记接入；
 * 未登记 / 未注入时字典能力即占位（不发请求）。
 *
 * 方法对应后端字典出口（普通取数与高级查询同一数据源）：
 * `GET /api/v1/dicts/{type}`、`POST /api/v1/dicts/batch`、`GET /api/v1/dicts/{type}/attrs`、
 * `GET /api/v1/dicts/query-providers`、`POST /api/v1/dicts/{type}/advanced-query`、
 * `/api/v1/query-schemes`（清单 / 默认 / 保存 / 删除）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 字典数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseDictSource extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'dict-source';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 单类型取数。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    getType(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 批量取数。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    batch(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 属性 schema。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    loadAttrs(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 查询提供者清单。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    loadProviders(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 高级查询。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    advancedQuery(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 查询方案清单。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    listSchemes(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 默认方案解析。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    resolveDefaultScheme(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 保存方案。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    saveScheme(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 删除方案。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    deleteScheme(query) {
        void query;
        return Promise.resolve(undefined);
    }
}
/** 数据源注册项（工厂创建插件实例）。 */
export class DictSourceProvider extends BaseProvider {
    /** 数据源键（如 `http`）。 */
    key;
    /** 数据源工厂。 */
    create;
    /**
     * 构造数据源注册项。
     *
     * @param key 数据源键。
     * @param create 数据源工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class DictSourceRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'dict-source-registry';
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
