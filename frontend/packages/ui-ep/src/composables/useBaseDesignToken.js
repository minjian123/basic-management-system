/** 设计令牌投影：把核心设计令牌能力基类 `BaseDesignToken` 投影为组合式（令牌 / 主题）。 */
import { BaseDesignToken } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体设计令牌（可实例化）。 */
class TokenState extends BaseDesignToken {
}
/**
 * 使用设计令牌投影。
 *
 * @param options 选项。
 * @returns 设计令牌基类实例与响应式面。
 */
export function useBaseDesignToken(options = {}) {
    const designToken = new TokenState();
    if (options.tokens !== undefined) {
        designToken.setTokens(options.tokens);
    }
    if (options.theme !== undefined) {
        designToken.setTheme(options.theme);
    }
    const tokens = ref(designToken.tokens);
    const theme = ref(designToken.theme);
    const off = designToken.onLifecycle((event) => {
        if (event === 'update') {
            tokens.value = designToken.tokens;
            theme.value = designToken.theme;
        }
    });
    onScopeDispose(off);
    return {
        designToken,
        tokens,
        theme,
        setTokens: (next) => designToken.setTokens(next),
        setTheme: (next) => designToken.setTheme(next),
        onThemeChange: (listener) => designToken.onThemeChange(listener),
    };
}
