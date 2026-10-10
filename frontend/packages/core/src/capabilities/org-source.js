/**
 * 组织数据源插件基类与提供者注册表：组织数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseOrgSource`，经 `OrgSourceRegistry` 登记接入；
 * 未登记 / 未注入时组织选择能力即占位（不发请求）。
 *
 * 四方法对应**组织主数据出口**（查询与批量回显分列两个出口）——组织主数据归 **mdm 产品**，
 * 出口经**产品命名空间**暴露：`/api/mdm/v1/org/data-source/{users,posts,dept-tree}` 与
 * `/api/mdm/v1/org/resolve-names`（前端默认端点由寻址契约组装，见 `@bms/ui-ep` 的 `orgSourceEndpoint`）；
 * 契约（数据契约与插件基类）原在 `bms_core/org`，已随阶段二 `11_02` 迁出基座。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 组织数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseOrgSource extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'org-source';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 用户查询。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    searchUsers(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 岗位查询。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    searchPosts(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 部门树查询。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    loadDeptTree(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 批量回显。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    resolveNames(query) {
        void query;
        return Promise.resolve(undefined);
    }
}
/** 组织数据源注册项（工厂创建插件实例）。 */
export class OrgSourceProvider extends BaseProvider {
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
/** 组织数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class OrgSourceRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'org-source-registry';
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
