/**
 * 启用语言清单插件基类与提供者注册表：语言清单为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseI18nLocaleSource`，经 `I18nLocaleSourceRegistry` 登记接入；
 * 未登记 / 未注入时语言清单即占位（不发请求，字段仅必填语言可编辑并提示）。
 *
 * 契约对应后端「启用语言清单只读出口」（登录即可）与当前登录用户语言：
 * `GET /api/v1/i18n/locales/enabled`（code / name / 默认标记 / rtl）+ 会话语言。
 * 语言清单驱动多语言文案字段的语言行——新增语言只需在语言清单启用，界面与接口契约都不变。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 启用语言清单插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export class BaseI18nLocaleSource extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'i18n-locale-source';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 取启用语言清单。
     *
     * @returns 原始结果（缺省 `undefined`）。
     */
    loadEnabledLocales() {
        return Promise.resolve(undefined);
    }
    /**
     * 取当前登录用户语言。
     *
     * @returns 语言标识（缺省 `undefined`）。
     */
    currentUserLocale() {
        return undefined;
    }
}
/** 语言清单数据源注册项（工厂创建插件实例）。 */
export class I18nLocaleSourceProvider extends BaseProvider {
    /** 数据源键（如 `http`）。 */
    key;
    /** 数据源工厂。 */
    create;
    /**
     * 构造语言清单数据源注册项。
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
/** 语言清单数据源注册表（统一注册表基座；同键唯一性拒重）。 */
export class I18nLocaleSourceRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'i18n-locale-source-registry';
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
