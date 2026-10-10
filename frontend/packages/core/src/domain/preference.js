/**
 * 偏好领域纯函数：偏好项键与平台默认值、租户策略判定、默认值合并与差异计算。
 *
 * 框架无关；偏好项集合与《组件设计 · 偏好设置面板》「偏好项（内置）」及后端用户喜好登记项对齐。
 * 偏好项的后端存储与同步不在此列（本模块只做前端取值口径）。
 */
import { stableStringify } from './serialize';
/** 偏好项键（扁平路径，含嵌套键；与组件设计登记一致）。 */
export const PREFERENCE_KEYS = [
    'themeMode',
    'accent',
    'locale',
    'timezone',
    'sidebarCollapsed',
    'tabsEnabled',
    'tabsStyle',
    'listDensity',
    'defaultRoute',
    'notify.inbox',
    'notify.email',
    'notify.sms',
    'shortcuts',
];
/** 平台默认偏好值。 */
export const PREFERENCE_DEFAULTS = {
    themeMode: 'light',
    accent: false,
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    sidebarCollapsed: false,
    tabsEnabled: true,
    tabsStyle: 'card',
    listDensity: 'comfortable',
    defaultRoute: '/dashboard',
    notify: { inbox: true, email: false, sms: false },
    shortcuts: true,
};
/** 主题模式取值域。 */
const THEME_MODES = ['light', 'dark', 'system'];
/** 多标签样式取值域。 */
const TABS_STYLES = ['card', 'plain'];
/** 列表密度取值域。 */
const LIST_DENSITIES = ['compact', 'comfortable', 'loose'];
/**
 * 读取扁平偏好键对应的值。
 *
 * @param values 偏好值。
 * @param key 偏好项键。
 * @returns 原始值。
 */
export function readPreferenceValue(values, key) {
    if (key.startsWith('notify.')) {
        return values.notify[key.slice('notify.'.length)];
    }
    return values[key];
}
/**
 * 写入扁平偏好键（返回新值对象，不改原对象）。
 *
 * @param values 偏好值。
 * @param key 偏好项键。
 * @param value 新值（不合法值视为未变更）。
 * @returns 新的偏好值。
 */
export function writePreferenceValue(values, key, value) {
    if (key.startsWith('notify.')) {
        const channel = key.slice('notify.'.length);
        return { ...values, notify: { ...values.notify, [channel]: value } };
    }
    return { ...values, [key]: value };
}
/**
 * 合并偏好值（嵌套 `notify` 逐键合并）。
 *
 * @param base 基线值。
 * @param override 覆盖值。
 * @returns 合并结果。
 */
export function mergePreferences(base, override) {
    const source = override ?? {};
    return { ...base, ...source, notify: { ...base.notify, ...(source.notify ?? {}) } };
}
/**
 * 校验单个偏好项取值是否合法（非法值回退默认）。
 *
 * @param key 偏好项键。
 * @param value 原始值。
 * @returns 是否合法。
 */
function isValidPreferenceValue(key, value) {
    switch (key) {
        case 'themeMode':
            return THEME_MODES.includes(value);
        case 'tabsStyle':
            return TABS_STYLES.includes(value);
        case 'listDensity':
            return LIST_DENSITIES.includes(value);
        case 'locale':
        case 'timezone':
        case 'defaultRoute':
            return typeof value === 'string' && value !== '';
        default:
            return typeof value === 'boolean';
    }
}
/**
 * 按默认值修正非法项（返回新值对象）。
 *
 * @param values 候选值。
 * @param fallback 回退基线。
 * @param keys 需回退的键。
 * @returns 修正后的偏好值。
 */
function fallbackPreferences(values, fallback, keys) {
    let next = values;
    for (const key of keys) {
        next = writePreferenceValue(next, key, readPreferenceValue(fallback, key));
    }
    return next;
}
/**
 * 归一偏好值：逐键校验，非法值回退基线（缺省平台默认）。
 *
 * @param input 候选值（含部分键）。
 * @param fallback 回退基线。
 * @returns 全量合法偏好值。
 */
export function sanitizePreferences(input = {}, fallback = PREFERENCE_DEFAULTS) {
    const merged = mergePreferences(fallback, input);
    const invalid = PREFERENCE_KEYS.filter((key) => !isValidPreferenceValue(key, readPreferenceValue(merged, key)));
    return invalid.length === 0 ? merged : fallbackPreferences(merged, fallback, invalid);
}
/**
 * 解析默认值 = 平台默认 ∩ 租户默认（租户已禁用项不接受租户覆盖）。
 *
 * @param tenantDefaults 租户默认值。
 * @param policy 租户策略。
 * @returns 默认偏好值。
 */
export function resolvePreferenceDefaults(tenantDefaults, policy) {
    const resolved = sanitizePreferences(tenantDefaults ?? {}, PREFERENCE_DEFAULTS);
    if (policy === undefined) {
        return resolved;
    }
    const disabled = PREFERENCE_KEYS.filter((key) => !isPreferenceEnabled(key, policy));
    return disabled.length === 0 ? resolved : fallbackPreferences(resolved, { ...PREFERENCE_DEFAULTS }, disabled);
}
/**
 * 应用默认值（可选项取默认、不可选项保留现值）——「恢复默认」口径。
 *
 * @param current 当前值。
 * @param defaults 默认值（平台默认 ∩ 租户默认）。
 * @param policy 租户策略。
 * @returns 恢复后的偏好值。
 */
export function applyPreferenceDefaults(current, defaults, policy) {
    let next = current;
    for (const key of PREFERENCE_KEYS) {
        if (isPreferenceEnabled(key, policy)) {
            next = writePreferenceValue(next, key, readPreferenceValue(defaults, key));
        }
    }
    return next;
}
/**
 * 计算差异键（用于脏标记与单项变更事件）。
 *
 * @param a 前值。
 * @param b 后值。
 * @returns 发生变更的偏好项键（按登记顺序）。
 */
export function diffPreferences(a, b) {
    return PREFERENCE_KEYS.filter((key) => stableStringify(readPreferenceValue(a, key)) !== stableStringify(readPreferenceValue(b, key)));
}
/**
 * 偏好项是否可见（策略 `visible: false` 时不可见）。
 *
 * @param key 偏好项键。
 * @param policy 租户策略。
 * @returns 是否可见。
 */
export function isPreferenceVisible(key, policy) {
    return policy?.[key]?.visible !== false;
}
/**
 * 偏好项是否可选（不可见视为不可选）。
 *
 * @param key 偏好项键。
 * @param policy 租户策略。
 * @returns 是否可选。
 */
export function isPreferenceEnabled(key, policy) {
    return isPreferenceVisible(key, policy) && policy?.[key]?.enabled !== false;
}
