/**
 * 多语言文案字段投影：把核心多语言文案族组件基类 `BaseMultilingualName` 投影为组合式
 * （语言清单装载 / 必填语言 / 语言行与缺失 / 明细弹框草稿 / 提交载荷 / 校验）。
 *
 * 件层只做渲染与事件转发，语义（必填语言解析、回退链、派生化口径）全在核心基类。
 */
import { BaseMultilingualName, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体多语言文案字段（可实例化）。 */
class MultilingualNameState extends BaseMultilingualName {
}
/**
 * 使用多语言文案字段投影。
 *
 * @param options 选项。
 * @returns 字段实例与响应式面。
 */
export function useBaseMultilingualName(options = {}) {
    const field = new MultilingualNameState();
    const localDisabled = ref(options.disabled ?? false);
    if (options.ready !== undefined) {
        field.setReady(options.ready);
    }
    if (options.multiline !== undefined) {
        field.setMultiline(options.multiline);
    }
    if (options.maxLength !== undefined) {
        field.setMaxLength(options.maxLength);
    }
    if (options.required !== undefined) {
        field.setRequired(options.required);
    }
    if (options.userLocale !== undefined) {
        field.setUserLocale(options.userLocale);
    }
    if (options.locales !== undefined) {
        field.setLocales(options.locales);
    }
    if (options.source !== undefined) {
        field.setSource(options.source);
    }
    if (options.value !== undefined) {
        field.setNames(options.value);
    }
    const value = ref(field.value);
    const rows = ref(field.rows);
    const requiredLocale = ref(field.requiredLocale);
    const defaultLocale = ref(field.defaultLocale);
    const text = ref(field.text);
    const displayText = ref(field.displayText);
    const hintText = ref(field.hintText);
    const missingLocales = ref(field.missingLocales);
    const invalid = ref(field.invalid);
    const localeDegraded = ref(field.localeDegraded);
    const loadingLocales = ref(field.loadingLocales);
    const detailVisible = ref(field.detailVisible);
    const draftRows = ref(field.draftRows());
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        value.value = field.value;
        rows.value = field.rows;
        requiredLocale.value = field.requiredLocale;
        defaultLocale.value = field.defaultLocale;
        text.value = field.text;
        displayText.value = field.displayText;
        hintText.value = field.hintText;
        missingLocales.value = field.missingLocales;
        invalid.value = field.invalid;
        localeDegraded.value = field.localeDegraded;
        loadingLocales.value = field.loadingLocales;
        detailVisible.value = field.detailVisible;
        draftRows.value = field.draftRows();
    }
    const off = field.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offValue = field.onChange(() => sync());
    onScopeDispose(() => {
        off();
        offValue();
        field.dispose();
    });
    const disabled = computed(() => localDisabled.value || field.disabled);
    return {
        field,
        value,
        rows,
        requiredLocale,
        defaultLocale,
        text,
        displayText,
        hintText,
        missingLocales,
        invalid,
        localeDegraded,
        loadingLocales,
        detailVisible,
        draftRows,
        disabled,
        setValue: (next) => field.setValue(next),
        setNames: (next) => field.setNames(next),
        setName: (code, next) => field.setName(code, next),
        setText: (next) => field.setText(next),
        setLocales: (next) => field.setLocales(next),
        setUserLocale: (next) => field.setUserLocale(next),
        setRequired: (next) => field.setRequired(next),
        setMultiline: (next) => field.setMultiline(next),
        setSource: (next) => field.setSource(next),
        setReady: (next) => field.setReady(next),
        loadLocales: () => field.loadLocales(),
        openDetail: () => field.openDetail(),
        closeDetail: () => field.closeDetail(),
        confirmDetail: () => field.confirmDetail(),
        setDraftName: (code, next) => field.setDraftName(code, next),
        setFilter: (next) => field.setFilter(next),
        submitPayload: () => field.submitPayload(),
        validate: () => field.validate(),
        defaultText: () => field.defaultText(),
        fallbackHint: (code) => field.fallbackHint(code),
        onValueChange: (listener) => field.onChange(listener),
    };
}
