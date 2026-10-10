/** 主题与品牌投影：把核心主题能力基类 `BaseTheme` 投影为组合式（模式 / 解析 / 品牌令牌 / 系统监听 / 根元素注入）。 */
import { BaseTheme, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
import { matchesMedia, onMediaChange as subscribeMediaChange, supportsMediaQuery } from '../utils/media';
/** 具体主题件（可实例化）。 */
class Theme extends BaseTheme {
}
/**
 * 使用主题与品牌投影。
 *
 * @param options 选项。
 * @returns 主题基类实例与响应式面。
 */
export function useBaseTheme(options = {}) {
    const theme = new Theme();
    theme.followSystem = options.followSystem ?? true;
    if (options.persisted !== undefined) {
        // 跨实例基类对象不进入响应式（私有字段经代理读取会失效）。
        theme.persisted = markRaw(toRaw(options.persisted));
    }
    if (options.brand !== undefined) {
        theme.setBrand(options.brand);
    }
    if (options.mode !== undefined) {
        theme.setMode(options.mode);
    }
    else if (theme.persisted !== undefined) {
        theme.attachPersisted(theme.persisted);
    }
    const mediaQuery = options.mediaQuery ?? '(prefers-color-scheme: dark)';
    if (theme.followSystem && supportsMediaQuery()) {
        theme.setSystemPrefersDark(matchesMedia(mediaQuery));
    }
    const offMedia = theme.followSystem
        ? subscribeMediaChange(mediaQuery, (matches) => {
            theme.setSystemPrefersDark(matches);
        })
        : () => { };
    onScopeDispose(offMedia);
    const mode = ref(theme.mode);
    const resolved = ref(theme.resolved);
    const primary = ref(theme.primary);
    const brandTokens = ref({ ...theme.brandTokens });
    const canUseDark = ref(theme.canUseDark);
    const displayMode = ref(theme.displayMode);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        mode.value = theme.mode;
        resolved.value = theme.resolved;
        primary.value = theme.primary;
        brandTokens.value = { ...theme.brandTokens };
        canUseDark.value = theme.canUseDark;
        displayMode.value = theme.displayMode;
    };
    const off = theme.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    /**
     * 应用主题与品牌到目标元素。
     *
     * @param target 目标元素（缺省 `document.documentElement`）。
     */
    const applyToElement = (target) => {
        const element = target ?? globalThis.document?.documentElement;
        if (element === undefined) {
            return;
        }
        element.dataset.theme = theme.resolved;
        for (const [name, value] of Object.entries(theme.brandTokens)) {
            element.style.setProperty(name, value);
        }
        const doc = globalThis.document;
        if (doc === undefined) {
            return;
        }
        if (theme.brand?.name !== undefined && options.applyTitle !== false) {
            doc.title = theme.brand.name;
        }
        if (theme.brand?.favicon !== undefined && options.applyFavicon !== false) {
            try {
                let link = doc.querySelector('link[rel="icon"]');
                if (link === null) {
                    link = doc.createElement('link');
                    link.rel = 'icon';
                    doc.head.appendChild(link);
                }
                link.href = theme.brand.favicon;
            }
            catch {
                // 品牌资源不可用时降级为平台默认（不阻断应用）。
            }
        }
    };
    return {
        theme,
        mode,
        resolved,
        primary,
        brandTokens,
        canUseDark,
        displayMode,
        setMode: (next) => {
            const value = theme.setMode(next);
            sync();
            return value;
        },
        setBrand: (brand) => {
            const value = theme.setBrand(brand);
            sync();
            return value;
        },
        setAccent: (color) => {
            const value = theme.setAccent(color);
            sync();
            return value;
        },
        toggle: () => {
            const value = theme.toggle();
            sync();
            return value;
        },
        applyToElement,
        preload: () => {
            const value = theme.resolved;
            sync();
            applyToElement();
            return value;
        },
    };
}
