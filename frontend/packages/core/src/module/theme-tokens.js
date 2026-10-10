/**
 * 模块主题令牌机制：汇聚已登记令牌并按登记序应用 / 还原。
 *
 * **核心不触 DOM**——令牌写回目标（`ThemeTokenTarget`）由宿主注入（浏览器为根元素自定义属性）；
 * 应用返回已写入的令牌名，供卸载时按名移除。
 */
/**
 * 汇聚已登记令牌（按登记序合并，后者覆盖同名令牌）。
 *
 * @param source 令牌来源（如主题令牌注册表）。
 * @param options 汇聚选项。
 * @returns 令牌映射（令牌名 → 值）。
 */
export function collectThemeTokens(source, options = {}) {
    const records = options.mode === undefined || source.byMode === undefined ? source.values() : source.byMode(options.mode);
    const tokens = {};
    for (const record of records) {
        for (const [name, value] of Object.entries(record.tokens)) {
            tokens[name] = value;
        }
    }
    return tokens;
}
/**
 * 应用令牌（返回已写入的令牌名，供还原）。
 *
 * @param target 令牌写回目标。
 * @param tokens 令牌映射。
 * @returns 已写入的令牌名（应用序）。
 */
export function applyThemeTokens(target, tokens) {
    const names = Object.keys(tokens);
    for (const name of names) {
        target.setToken(name, tokens[name] ?? '');
    }
    return names;
}
/**
 * 还原令牌（按名逆序移除；幂等）。
 *
 * @param target 令牌写回目标。
 * @param names `applyThemeTokens` 返回的令牌名清单。
 */
export function releaseThemeTokens(target, names) {
    for (const name of [...names].reverse()) {
        target.removeToken(name);
    }
}
