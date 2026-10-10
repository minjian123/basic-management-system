/**
 * 领域用例：业务文案多语言（语言清单归一 / 必填语言解析 / 语言行装配 / 缺失派生 / 回退链 /
 * 提交载荷 / 校验 / 明细筛选 / 默认文案派生优先级）。
 *
 * 「派生化口径」用例表与服务端 `services/menu.py` 同源，双侧共用一组期望值。
 */
import { describe, expect, it } from 'vitest';
import { EMPTY_LOCALE_FILTER, I18N_NAME_MAX, buildI18nPayload, buildLocaleRows, countFilled, deriveDefaultText, deriveMissingNameLocales, fallbackHintText, filterLocaleRows, isBlankName, isNamesEqual, nameHintText, normalizeLocaleOptions, orderLocaleOptions, resolveDefaultLocale, resolveDisplayText, resolveRequiredLocale, validateI18nNames, } from '../src';
/** 语言清单装载输入（zh-CN 为系统默认语言，en-US 为当前登录用户语言）。 */
const LOCALES = [
    { code: 'zh-CN', name: '简体中文', isDefault: true },
    { code: 'en-US', name: 'English' },
    { code: 'ja-JP', name: '日本語', rtl: false },
];
describe('语言清单归一与默认 / 必填语言解析', () => {
    it('归一：去空白、按标识去重保序、默认标记至多一条、语言名缺省回落标识', () => {
        const locales = normalizeLocaleOptions([
            { code: ' zh-CN ', isDefault: true },
            { code: 'en-US', name: ' English ' },
            { code: 'zh-CN', isDefault: true },
            { code: '' },
        ]);
        expect(locales.map((item) => item.code)).toEqual(['zh-CN', 'en-US']);
        expect(locales[0]?.name).toBe('zh-CN');
        expect(locales[1]?.name).toBe('English');
        expect(locales.filter((item) => item.isDefault)).toHaveLength(1);
    });
    it('默认语言：清单默认标记唯一时命中，重复或缺失时为空串（清单非法不静默取首项）', () => {
        const locales = normalizeLocaleOptions(LOCALES);
        expect(resolveDefaultLocale(locales)).toBe('zh-CN');
        expect(resolveDefaultLocale(normalizeLocaleOptions([{ code: 'en-US' }]))).toBe('');
    });
    it('必填语言：当前登录用户语言在启用清单内即取之，未启用回退系统默认语言，再回退清单首项', () => {
        const locales = normalizeLocaleOptions(LOCALES);
        expect(resolveRequiredLocale(locales, 'en-US')).toBe('en-US');
        expect(resolveRequiredLocale(locales, ' EN-us ')).toBe('en-US');
        expect(resolveRequiredLocale(locales, 'ko-KR')).toBe('zh-CN');
        expect(resolveRequiredLocale(locales, '')).toBe('zh-CN');
        expect(resolveRequiredLocale(normalizeLocaleOptions([{ code: 'ja-JP' }, { code: 'ko-KR' }]), 'ko-KR')).toBe('ko-KR');
    });
    it('语言行排序：必填语言恒置顶，其余保持清单序', () => {
        const locales = normalizeLocaleOptions(LOCALES);
        expect(orderLocaleOptions(locales, 'en-US').map((item) => item.code)).toEqual(['en-US', 'zh-CN', 'ja-JP']);
        expect(orderLocaleOptions(locales, '').map((item) => item.code)).toEqual(['zh-CN', 'en-US', 'ja-JP']);
    });
});
describe('语言行装配、缺失派生与回退链', () => {
    it('语言行：带默认 / 必填标记与缺失态，必填语言置顶', () => {
        const rows = buildLocaleRows({ 'zh-CN': '用户管理', 'en-US': ' ' }, normalizeLocaleOptions(LOCALES), 'en-US');
        expect(rows.map((row) => row.code)).toEqual(['en-US', 'zh-CN', 'ja-JP']);
        expect(rows[0]).toMatchObject({ isRequired: true, isDefault: false, missing: true });
        expect(rows[1]).toMatchObject({ isRequired: false, isDefault: true, missing: false, value: '用户管理' });
    });
    it('缺失派生：启用语言中值为空者（去空白），按清单顺序；已填计数与之一致', () => {
        const locales = normalizeLocaleOptions(LOCALES);
        const names = { 'zh-CN': '用户管理', 'en-US': '   ' };
        expect(deriveMissingNameLocales(names, locales)).toEqual(['en-US', 'ja-JP']);
        expect(countFilled(names, locales)).toBe(1);
        expect(isBlankName('  ')).toBe(true);
        expect(isBlankName(' x ')).toBe(false);
    });
    it('回退链：当前语言 → 系统默认语言 → 首个有值语言 → 空串（不合成值）', () => {
        expect(resolveDisplayText({ 'zh-CN': '中文名', 'en-US': 'English' }, 'en-US', 'zh-CN')).toBe('English');
        expect(resolveDisplayText({ 'zh-CN': '中文名' }, 'en-US', 'zh-CN')).toBe('中文名');
        expect(resolveDisplayText({ 'ja-JP': '日本語' }, 'en-US', 'zh-CN')).toBe('日本語');
        expect(resolveDisplayText({}, 'en-US', 'zh-CN')).toBe('');
    });
    it('默认文案派生（与服务端同口径）：系统默认语言优先 → 必填语言 → 首个有值语言', () => {
        expect(deriveDefaultText({ 'zh-CN': '中文名', 'en-US': 'English' }, 'zh-CN', 'en-US')).toBe('中文名');
        expect(deriveDefaultText({ 'en-US': 'English' }, 'zh-CN', 'en-US')).toBe('English');
        expect(deriveDefaultText({ 'ja-JP': '日本語' }, 'zh-CN', 'en-US')).toBe('日本語');
        expect(deriveDefaultText({}, 'zh-CN', 'en-US')).toBe('');
    });
});
describe('提交载荷、校验与明细筛选', () => {
    it('提交载荷：启用语言去空白值 + 停用语言存量值原样透传', () => {
        const locales = normalizeLocaleOptions([
            { code: 'zh-CN', isDefault: true },
            { code: 'en-US' },
        ]);
        const payload = buildI18nPayload({ 'zh-CN': '中文名 ', 'en-US': '  ', 'fr-FR': 'Nom' }, locales);
        expect(payload).toEqual({ 'zh-CN': '中文名', 'fr-FR': 'Nom' });
    });
    it('校验：必填语言缺文案即失败（提示附语言标识），逐语言长度按 Unicode 码点计', () => {
        expect(validateI18nNames({ 'zh-CN': '中文名' }, 'zh-CN')).toEqual({ valid: true, message: '' });
        const missingRequired = validateI18nNames({ 'en-US': 'English' }, 'zh-CN');
        expect(missingRequired.valid).toBe(false);
        expect(missingRequired.message).toContain('zh-CN');
        expect(validateI18nNames({ 'zh-CN': '中'.repeat(I18N_NAME_MAX + 1) }, 'zh-CN').valid).toBe(false);
        expect(validateI18nNames({ 'zh-CN': '🙂'.repeat(I18N_NAME_MAX) }, 'zh-CN').valid).toBe(true);
    });
    it('明细筛选：关键字匹配标识或语言名 + 全部 / 仅看缺失 / 仅看已填三态（本地筛选）', () => {
        const rows = buildLocaleRows({ 'zh-CN': '用户管理', 'en-US': '' }, normalizeLocaleOptions(LOCALES), 'zh-CN');
        expect(filterLocaleRows(rows, EMPTY_LOCALE_FILTER)).toHaveLength(3);
        expect(filterLocaleRows(rows, { keyword: '', mode: 'missing' }).map((row) => row.code)).toEqual(['en-US', 'ja-JP']);
        expect(filterLocaleRows(rows, { keyword: '', mode: 'filled' }).map((row) => row.code)).toEqual(['zh-CN']);
        expect(filterLocaleRows(rows, { keyword: 'english', mode: 'all' }).map((row) => row.code)).toEqual(['en-US']);
        expect(filterLocaleRows(rows, { keyword: 'ja', mode: 'all' }).map((row) => row.code)).toEqual(['ja-JP']);
    });
    it('未保存变更判定：键集与逐值比较', () => {
        expect(isNamesEqual({ 'zh-CN': 'A' }, { 'zh-CN': 'A' })).toBe(true);
        expect(isNamesEqual({ 'zh-CN': 'A' }, { 'zh-CN': 'B' })).toBe(false);
        expect(isNamesEqual({ 'zh-CN': 'A' }, { 'zh-CN': 'A', 'en-US': '' })).toBe(false);
    });
    it('外壳提示：已填完整度；有缺失时列出缺失语言（不含必填语言）；缺省回退提示指向回退目标', () => {
        const locales = normalizeLocaleOptions(LOCALES);
        expect(nameHintText({ 'zh-CN': '中文名', 'en-US': 'English', 'ja-JP': '日本語' }, locales, 'zh-CN')).toBe('多语言文案 · 已填 3 / 3');
        expect(nameHintText({ 'zh-CN': '中文名' }, locales, 'zh-CN')).toBe('多语言文案 · 缺失：en-US、ja-JP');
        expect(fallbackHintText({ 'zh-CN': '中文名' }, 'en-US', 'zh-CN', 'en-US')).toBe('缺省回退：中文名');
        expect(fallbackHintText({ 'zh-CN': '中文名' }, 'zh-CN', 'zh-CN', 'en-US')).toBe('缺省回退：中文名');
        expect(fallbackHintText({}, 'en-US', 'zh-CN', 'en-US')).toBe('');
    });
});
