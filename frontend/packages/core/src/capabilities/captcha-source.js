/**
 * 验证码数据源插件基类与提供者注册表：验证码数据源为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseCaptchaSource`，经 `CaptchaSourceRegistry` 登记接入；
 * 未登记 / 未注入时验证码能力即占位（不发请求）。
 *
 * 方法对应后端验证码出口（`app/api/captcha.py` 四端点）：
 * `POST /api/v1/captcha/challenges`、`POST /api/v1/captcha/sms`、
 * `POST /api/v1/captcha/verify`、`GET /api/v1/captcha/scenes/{scene}/policy`。
 */
import { BasePluggable } from '../mechanisms/pluggable';
import { BaseProvider } from '../mechanisms/provider';
import { BaseProviderRegistry } from '../mechanisms/registry';
/** 验证码数据源插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseCaptchaSource extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'captcha-source';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 出题（图形 / 滑块）。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    challenge(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 发送短信验证码。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    sendSms(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 校验凭证。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    verify(query) {
        void query;
        return Promise.resolve(undefined);
    }
    /**
     * 取场景策略。
     *
     * @param query 查询入参。
     * @returns 原始结果（缺省 `undefined`）。
     */
    policy(query) {
        void query;
        return Promise.resolve(undefined);
    }
}
/** 数据源注册项（工厂创建插件实例）。 */
export class CaptchaSourceProvider extends BaseProvider {
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
export class CaptchaSourceRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'captcha-source-registry';
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
