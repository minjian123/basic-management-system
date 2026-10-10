/**
 * 上传通路插件基类与提供者注册表：上传通路为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseUploadTransport`，经 `UploadTransportRegistry` 登记接入；
 * 未登记 / 未注入时上传引擎即占位（不发请求）。
 *
 * 方法与后端对象存储扩展基座（`02-4-18`）及冻结的契约缺口一一对应：
 * 分片 `initiate` / `upload_part` / `complete` / `abort` / `check`（`/api/v1/files/*`）、
 * 已传分片查询、批量元数据、整包上传与下载 / 预览预签名（只增不改，登记后端需求）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 上传通路插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseUploadTransport extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'upload-transport';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 整文件（含每片）哈希。
     *
     * @param query 哈希入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    hash(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 秒传判定。
     *
     * @param query 判定入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    check(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 整包上传。
     *
     * @param query 上传入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    uploadWhole(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 分片初始化。
     *
     * @param query 初始化入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    initiate(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 分片上传。
     *
     * @param query 分片入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    uploadPart(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 分片合并。
     *
     * @param query 会话入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    complete(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 取消会话。
     *
     * @param query 会话入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    abort(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 已传分片查询（断点续传）。
     *
     * @param query 会话入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    listParts(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 批量元数据。
     *
     * @param query 批量入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    resolveFiles(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 下载 / 预览预签名。
     *
     * @param query 预签名入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    presign(query) {
        void query;
        return Promise.resolve(undefined);
    }
}
/** 通路注册项（工厂创建插件实例）。 */
export class UploadTransportProvider extends BaseProvider {
    /** 注册键。 */
    key;
    /** 工厂（按选项创建通路实例）。 */
    create;
    /**
     * 构造注册项。
     *
     * @param key 通路键（如 `http`）。
     * @param create 通路工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 通路注册表（统一注册表基座；同键唯一性拒重）。 */
export class UploadTransportRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'upload-transport-registry';
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
