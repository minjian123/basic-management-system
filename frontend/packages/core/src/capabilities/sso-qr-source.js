/**
 * 扫码登录状态源插件基类与提供者注册表：状态源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseSsoQrSource`，经 `SsoQrSourceRegistry` 登记接入；
 * 未登记 / 未注入时扫码登录能力即占位（不发请求）。
 *
 * 方法对应后端扫码链路出口（域二 `02_04`）：
 * `GET /api/v1/auth/sso/{idp_key}/authorize-url`（取授权 URL）。
 * **本期无扫码状态端点**（后端不做轮询状态机），`poll` 为可注入的扩展面：
 * 真实平台适配（内嵌登录组件 / 状态端点）归阶段十七，届时换实现即可。
 */
import { BasePluggable } from '../mechanisms/pluggable';
import { BaseProvider } from '../mechanisms/provider';
import { BaseProviderRegistry } from '../mechanisms/registry';
/** 状态源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseSsoQrSource extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'sso-qr-source';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 取授权 URL。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    init(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 轮询扫码状态。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    poll(query) {
        void query;
        return Promise.resolve(undefined);
    }
}
/** 状态源注册项（工厂创建插件实例）。 */
export class SsoQrSourceProvider extends BaseProvider {
    /** 状态源键（如 `http`）。 */
    key;
    /** 状态源工厂。 */
    create;
    /**
     * 构造状态源注册项。
     *
     * @param key 状态源键。
     * @param create 状态源工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 状态源注册表（统一注册表基座；同键唯一性拒重）。 */
export class SsoQrSourceRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'sso-qr-source-registry';
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
