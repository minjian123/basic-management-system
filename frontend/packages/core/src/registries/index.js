/**
 * 扩展点注册表（微前端模块契约）：五个具体注册表与工厂。
 *
 * 均基于统一提供者注册表基座 `BaseProviderRegistry`（同键唯一性拒重、保序、只读快照），
 * 供模块注册与平台自身注册共用——**不得另起映射**。
 */
import { schemaError } from './validate';
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseError } from '../mechanisms/error';
import { ErrorCodes } from '../mechanisms/error-codes';
import { evaluatePermission } from '../domain/permission';
import { ComponentProvider, FieldRendererProvider, I18nPackProvider, IconProvider, LOCALE_TAG_PATTERN, PAGE_AREA_ID_PATTERN, PageAreaProvider, REGISTRY_KEY_PATTERN, RouteMenuProvider, ThemeTokenProvider, WorkbenchCardProvider, } from './providers';
export * from './providers';
export { schemaError };
/** 校验命名空间键（模块注册项）。 */
export function assertNamespacedKey(key, scope) {
    if (!REGISTRY_KEY_PATTERN.test(key)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `${scope} 注册键非法：${key}`);
    }
}
/** icon key 模式（`el:User` / `biz:purchase-order` / `custom:1024` / `van:todo-o`）。 */
export const ICON_KEY_PATTERN = /^[a-z][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*$/;
/**
 * 校验 icon key（前缀 + 大小写/数字/连字符段）。
 *
 * @param key icon key。
 * @throws BaseError 键非法（`CAPABILITY_VIOLATION`）。
 */
export function assertIconKey(key) {
    if (!ICON_KEY_PATTERN.test(key)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `图标键非法：${key}`);
    }
}
/**
 * 校验页面区域标识（点分 `<域>.<区域>`）。
 *
 * @param area 区域标识。
 * @throws BaseError 标识非法（`CAPABILITY_VIOLATION`）。
 */
export function assertPageAreaId(area) {
    if (!PAGE_AREA_ID_PATTERN.test(area)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `区域标识非法：${area}`);
    }
}
/**
 * 校验语言标识段（小写 BCP-47 形态）。
 *
 * @param tag 语言标识段。
 * @param scope 校验范围。
 * @throws BaseError 标识非法（`CAPABILITY_VIOLATION`）。
 */
export function assertLocaleTag(tag, scope) {
    if (!LOCALE_TAG_PATTERN.test(tag)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `${scope} 语言标识非法：${tag}`);
    }
}
/** 归一化图标检索文本（小写、去分隔符，保留中英文；kebab/Pascal 归一后可匹配）。 */
function normalizeIconSearch(value) {
    return value.toLowerCase().replace(/[\s:._-]+/g, '');
}
/** 路由·菜单注册表。 */
export class RouteMenuRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'route-menu-registry';
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
    /**
     * 登记路由·菜单（路径须以 `/` 开头）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        if (!provider.path.startsWith('/')) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `路由路径须以 / 开头：${provider.path}`);
        }
        super.register(provider);
    }
}
/** 通用组件注册表。 */
export class ComponentRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'component-registry';
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
    /**
     * 登记通用组件（键须为命名空间键）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, '通用组件');
        super.register(provider);
    }
}
/** 字段渲染器注册表。 */
export class FieldRendererRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'field-renderer-registry';
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
    /**
     * 登记字段渲染器（键须为命名空间键）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, '字段渲染器');
        super.register(provider);
    }
    /**
     * 按字段类型解析渲染器（首个命中）。
     *
     * @param fieldType 字段类型。
     */
    resolveByType(fieldType) {
        return this.values().find((provider) => provider.fieldType === fieldType);
    }
}
/** 图标注册表。 */
export class IconRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'icon-registry';
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
    /**
     * 登记图标（键须为 icon key：`前缀:段`，段允许大小写 / 数字 / `._-`）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertIconKey(provider.key);
        super.register(provider);
    }
    /**
     * 按来源前缀取图标（`el` / `biz` / `custom` / `van`，冒号可省）。
     *
     * @param prefix 来源前缀。
     */
    byPrefix(prefix) {
        const normalized = prefix.endsWith(':') ? prefix : `${prefix}:`;
        return this.values().filter((provider) => provider.key.startsWith(normalized));
    }
    /**
     * 按关键词检索（归一匹配 key / name / tags；空串返回全部）。
     *
     * @param keyword 关键词。
     */
    search(keyword) {
        const text = normalizeIconSearch(keyword);
        if (text === '') {
            return this.values();
        }
        return this.values().filter((provider) => {
            const key = normalizeIconSearch(provider.key);
            const name = normalizeIconSearch(provider.name ?? '');
            const tags = provider.tags.map((tag) => normalizeIconSearch(tag));
            return key.includes(text) || name.includes(text) || tags.some((tag) => tag.includes(text));
        });
    }
    /**
     * 解析图标资源（未登记返回 `undefined`）。
     *
     * @param key icon key。
     */
    resolve(key) {
        return this.get(key)?.source;
    }
}
/** 工作台卡片注册表。 */
export class WorkbenchCardRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'workbench-card-registry';
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
    /**
     * 登记工作台卡片（键须为命名空间键）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, '工作台卡片');
        super.register(provider);
    }
}
/** 页面区域注册表。 */
export class PageAreaRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'page-area-registry';
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
    /**
     * 登记页面区域项（键须为命名空间键，区域标识须为点分标识）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, '页面区域');
        assertPageAreaId(provider.area);
        super.register(provider);
    }
    /**
     * 按区域标识解析（保序；按显示条件与权限过滤；未命中返回空数组，不替调用方兜底）。
     *
     * @param area 区域 / 具名插槽标识。
     * @param options 解析选项（已持有权限码）。
     */
    resolveByArea(area, options = {}) {
        const codes = options.permissionCodes ?? [];
        return this.values().filter((provider) => provider.area === area && this.visible(provider, codes));
    }
    /**
     * 区域项本轮是否可见（显示条件 → 权限码；任一不满足即不渲染）。
     *
     * 显示条件谓词抛错按「不渲染」处置并上报，**不影响同区其余项**。
     *
     * @param provider 注册项。
     * @param codes 已持有权限码。
     */
    visible(provider, codes) {
        if (provider.when !== undefined) {
            try {
                if (!provider.when()) {
                    return false;
                }
            }
            catch (error) {
                this.reportError(error, { key: provider.key, area: provider.area, stage: 'region-when' });
                return false;
            }
        }
        const perm = provider.perm;
        if (perm === undefined) {
            return true;
        }
        const required = typeof perm === 'string' ? [perm] : [...perm];
        if (required.length === 0) {
            return true;
        }
        return evaluatePermission(codes, required, provider.permMode);
    }
    /** 已登记区域标识（登记序、去重）。 */
    areas() {
        return [...new Set(this.values().map((provider) => provider.area))];
    }
}
/** 主题令牌注册表。 */
export class ThemeTokenRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'theme-token-registry';
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
    /**
     * 登记主题令牌（键须为命名空间键）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, '主题令牌');
        super.register(provider);
    }
    /**
     * 解析令牌映射（未命中返回 `undefined`）。
     *
     * @param key 主题键。
     */
    resolve(key) {
        return this.get(key)?.tokens;
    }
    /**
     * 按模式筛选（保序；空串返回全部）。
     *
     * @param mode 模式标注。
     */
    byMode(mode) {
        if (mode === '') {
            return this.values();
        }
        return this.values().filter((provider) => provider.mode === mode);
    }
}
/** i18n 文案包注册表。 */
export class I18nPackRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'i18n-pack-registry';
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
    /**
     * 登记 i18n 文案包（键须为命名空间键，语言标识段须小写归一且合法）。
     *
     * @param provider 注册项。
     */
    register(provider) {
        assertNamespacedKey(provider.key, 'i18n 文案包');
        assertLocaleTag(provider.locale, 'i18n 文案包');
        super.register(provider);
    }
    /**
     * 解析单个文案包（未命中返回 `undefined`；**不跨来源合并**）。
     *
     * @param key 语言包键。
     */
    resolve(key) {
        return this.get(key)?.messages;
    }
    /**
     * 按语言解析文案包（入参小写归一后比对；未命中返回空数组）。
     *
     * @param locale 语言标识。
     */
    byLocale(locale) {
        const normalized = locale.toLowerCase();
        return this.values().filter((provider) => provider.locale === normalized);
    }
}
/**
 * 创建前端注册表集合（平台自身注册与模块注册共用同一实例）。
 *
 * @returns 注册表集合。
 */
export function createRegistries() {
    return {
        routeMenu: new RouteMenuRegistry(),
        pageArea: new PageAreaRegistry(),
        component: new ComponentRegistry(),
        fieldRenderer: new FieldRendererRegistry(),
        icon: new IconRegistry(),
        workbenchCard: new WorkbenchCardRegistry(),
        themeToken: new ThemeTokenRegistry(),
        i18nPack: new I18nPackRegistry(),
    };
}
