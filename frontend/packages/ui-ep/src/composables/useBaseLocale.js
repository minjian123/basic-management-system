/** 语言上下文投影：把核心语言上下文能力基类 `BaseLocale` 投影为组合式（locale / 时区 / 格式上下文）。 */
import { BaseLocale } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体语言上下文件（可实例化）。 */
class LocaleState extends BaseLocale {
}
/**
 * 使用语言上下文投影。
 *
 * @param options 选项。
 * @returns 语言上下文响应式面。
 */
export function useBaseLocale(options = {}) {
    const state = new LocaleState();
    if (options.locale !== undefined) {
        state.locale = options.locale;
    }
    if (options.timezone !== undefined) {
        state.timezone = options.timezone;
    }
    const locale = ref(state.locale);
    const timezone = ref(state.timezone);
    const formatContext = ref(state.formatContext);
    const sync = () => {
        locale.value = state.locale;
        timezone.value = state.timezone;
        formatContext.value = state.formatContext;
    };
    const off = state.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        localeContext: state,
        locale,
        timezone,
        formatContext,
        setLocale: (value) => {
            state.setLocale(value);
            sync();
        },
        setTimezone: (value) => {
            state.setTimezone(value);
            sync();
        },
    };
}
