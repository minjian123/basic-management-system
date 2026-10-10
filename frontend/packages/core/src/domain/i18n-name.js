/**
 * 领域纯函数：业务文案多语言（启用语言清单归一 / 必填语言解析 / 语言行装配与排序 /
 * 缺失派生 / 回退链 / 提交载荷 / 变更集校验 / 默认文案派生预览 / 明细筛选）。
 *
 * 框架无关、无副作用、不发请求；**与后端 `services/menu.py` 的派生化口径同源**——
 * 必填语言＝请求语言（未启用时回退系统默认语言），主表默认文案按
 * 「系统默认语言 → 必填语言 → 首个有值语言」兜底派生（`deriveDefaultText` 与后端共用一套用例表）。
 * 口径见《组件设计 · 多语言文案字段》与《国际化规范》「业务文案多语言字段」节。
 */
/** 单条文案长度上限（Unicode 码点；与后端 `VARCHAR(128)` 同口径）。 */
export const I18N_NAME_MAX = 128;
/** 字段外壳占位文案（必填语言为空时）。 */
export const I18N_NAME_PLACEHOLDER = '请输入文案';
/** 字段外壳按钮提示前缀（已填 x / y）。 */
export const I18N_NAME_COUNT_PREFIX = '多语言文案 · 已填';
/** 字段外壳按钮提示（缺失语言）。 */
export const I18N_NAME_MISSING_PREFIX = '多语言文案 · 缺失：';
/** 字段外壳按钮提示（语言清单未就绪降级）。 */
export const I18N_NAME_PLACEHOLDER_HINT = '多语言文案（语言清单未就绪，占位）';
/** 明细弹框标题。 */
export const I18N_DETAIL_TITLE = '多语言文案';
/** 明细弹框说明（草稿语义）。 */
export const I18N_DETAIL_HINT = '弹框内为草稿，确定后回写字段，最终随宿主「保存」统一提交。';
/** 明细表空态文案（筛选无命中）。 */
export const I18N_DETAIL_EMPTY_TEXT = '当前筛选无语言';
/** 明细行缺失标记。 */
export const I18N_ROW_MISSING_TEXT = '缺失';
/** 明细行必填标记。 */
export const I18N_REQUIRED_TAG_TEXT = '必填';
/** 明细行默认标记。 */
export const I18N_DEFAULT_TAG_TEXT = '默认';
/** 明细行缺省回退提示前缀。 */
export const I18N_FALLBACK_PREFIX = '缺省回退：';
/** 必填语言缺文案提示（附语言标识）。 */
export const I18N_REQUIRED_EMPTY_PREFIX = '缺少必填语言文案：';
/** 文案超长提示。 */
export const I18N_NAME_TOO_LONG_TEXT = `文案超长（最多 ${I18N_NAME_MAX} 字）`;
/** 未就绪占位提示（语言清单取数失败）。 */
export const I18N_LOCALE_FAILED_TEXT = '语言清单取数失败（仅必填语言可编辑）';
/** 空筛选条件。 */
export const EMPTY_LOCALE_FILTER = { keyword: '', mode: 'all' };
/** 通过结果。 */
const OK = { valid: true, message: '' };
/**
 * 归一语言标识（去空白）。
 *
 * @param code 语言标识。
 * @returns 归一后的标识。
 */
function normalizeCode(code) {
    return String(code ?? '').trim();
}
/**
 * 归一语言清单（逐项归一、按标识去重保序；默认标记全清单至多保留第一个）。
 *
 * @param input 装载输入清单。
 * @returns 运行态语言项清单。
 */
export function normalizeLocaleOptions(input) {
    const result = [];
    const seen = new Set();
    let defaultTaken = false;
    for (const item of input) {
        const code = normalizeCode(item.code);
        if (code === '' || seen.has(code)) {
            continue;
        }
        seen.add(code);
        const isDefault = (item.isDefault ?? false) && !defaultTaken;
        if (isDefault) {
            defaultTaken = true;
        }
        const name = String(item.name ?? '').trim();
        result.push({ code, name: name === '' ? code : name, isDefault, rtl: item.rtl ?? false });
    }
    return result;
}
/**
 * 解析系统默认语言（清单默认标记；缺失或重复时按清单非法处置）。
 *
 * @param locales 语言清单。
 * @returns 默认语言标识；清单无默认标记或标记重复时为空串。
 */
export function resolveDefaultLocale(locales) {
    const marked = locales.filter((item) => item.isDefault);
    return marked.length === 1 ? marked[0].code : '';
}
/**
 * 解析必填语言（当前登录用户语言；未启用或为空则回退系统默认语言 → 清单首项）。
 *
 * @param locales 语言清单。
 * @param userLocale 当前登录用户语言。
 * @returns 必填语言标识；清单为空时为空串。
 */
export function resolveRequiredLocale(locales, userLocale) {
    const target = normalizeCode(userLocale);
    if (target !== '') {
        const hit = locales.find((item) => item.code.toLowerCase() === target.toLowerCase());
        if (hit !== undefined) {
            return hit.code;
        }
    }
    const fallback = resolveDefaultLocale(locales);
    if (fallback !== '') {
        return fallback;
    }
    return locales.length > 0 ? locales[0].code : '';
}
/**
 * 语言行排序（必填语言恒置顶；其余保持清单序）。
 *
 * @param locales 语言清单。
 * @param requiredCode 必填语言标识。
 * @returns 排序后的语言项清单。
 */
export function orderLocaleOptions(locales, requiredCode) {
    const required = normalizeCode(requiredCode);
    const first = locales.filter((item) => item.code === required);
    return first.length === 0 ? [...locales] : [...first, ...locales.filter((item) => item.code !== required)];
}
/**
 * 语言值是否为空（去空白后空串）。
 *
 * @param value 文案值。
 * @returns 是否为空。
 */
export function isBlankName(value) {
    return String(value ?? '').trim() === '';
}
/**
 * 派生缺失语言（启用语言中值为空者，按清单顺序）。
 *
 * @param names 多语言文案映射。
 * @param locales 语言清单。
 * @returns 缺失语言标识（保序去重）。
 */
export function deriveMissingNameLocales(names, locales) {
    return locales.filter((item) => isBlankName(names[item.code])).map((item) => item.code);
}
/**
 * 装配语言行（必填语言置顶；带标记与缺失态）。
 *
 * @param names 多语言文案映射。
 * @param locales 语言清单。
 * @param requiredCode 必填语言标识。
 * @returns 语言行清单。
 */
export function buildLocaleRows(names, locales, requiredCode) {
    const required = normalizeCode(requiredCode);
    return orderLocaleOptions(locales, required).map((item) => {
        const value = String(names[item.code] ?? '');
        return {
            code: item.code,
            name: item.name,
            rtl: item.rtl,
            isDefault: item.isDefault,
            isRequired: item.code === required,
            value,
            missing: isBlankName(value),
        };
    });
}
/**
 * 回退链解析展示文案（当前语言 → 系统默认语言 → 首个有值语言 → 空串）。
 *
 * @param names 多语言文案映射。
 * @param locale 当前语言。
 * @param defaultCode 系统默认语言。
 * @returns 展示文案（不合成值）。
 */
export function resolveDisplayText(names, locale, defaultCode) {
    for (const code of [normalizeCode(locale), normalizeCode(defaultCode)]) {
        if (code !== '' && !isBlankName(names[code])) {
            return String(names[code]).trim();
        }
    }
    for (const value of Object.values(names)) {
        if (!isBlankName(value)) {
            return String(value).trim();
        }
    }
    return '';
}
/**
 * 派生主表默认文案预览（系统默认语言 → 必填语言 → 首个有值语言；与后端同口径）。
 *
 * @param names 多语言文案映射。
 * @param defaultCode 系统默认语言。
 * @param requiredCode 必填语言。
 * @returns 派生文案（全空返回空串）。
 */
export function deriveDefaultText(names, defaultCode, requiredCode) {
    for (const code of [normalizeCode(defaultCode), normalizeCode(requiredCode)]) {
        if (code !== '' && !isBlankName(names[code])) {
            return String(names[code]).trim();
        }
    }
    for (const value of Object.values(names)) {
        if (!isBlankName(value)) {
            return String(value).trim();
        }
    }
    return '';
}
/**
 * 装配提交载荷（启用语言取当前值；表外键即停用语言存量值，原样透传）。
 *
 * @param names 多语言文案映射。
 * @param locales 语言清单（启用语言）。
 * @returns 提交映射（去空白值）。
 */
export function buildI18nPayload(names, locales) {
    const payload = {};
    for (const item of locales) {
        const value = String(names[item.code] ?? '').trim();
        if (value !== '') {
            payload[item.code] = value;
        }
    }
    const known = new Set(locales.map((item) => item.code));
    for (const [code, value] of Object.entries(names)) {
        if (!known.has(code) && !isBlankName(value)) {
            payload[code] = String(value).trim();
        }
    }
    return payload;
}
/**
 * 校验多语言文案（必填语言非空 + 逐语言长度上限）。
 *
 * @param names 多语言文案映射。
 * @param requiredCode 必填语言（空串表示不做必填校验）。
 * @param maxLength 长度上限（Unicode 码点；缺省 `I18N_NAME_MAX`）。
 * @returns 校验结果。
 */
export function validateI18nNames(names, requiredCode, maxLength = I18N_NAME_MAX) {
    const required = normalizeCode(requiredCode);
    if (required !== '' && isBlankName(names[required])) {
        return { valid: false, message: `${I18N_REQUIRED_EMPTY_PREFIX}${required}` };
    }
    for (const value of Object.values(names)) {
        if (Array.from(String(value ?? '')).length > maxLength) {
            return { valid: false, message: I18N_NAME_TOO_LONG_TEXT };
        }
    }
    return OK;
}
/**
 * 统计已填语言数。
 *
 * @param names 多语言文案映射。
 * @param locales 语言清单。
 * @returns 已填语言数。
 */
export function countFilled(names, locales) {
    return locales.filter((item) => !isBlankName(names[item.code])).length;
}
/**
 * 字段外壳按钮提示（已填完整度；有缺失时列出缺失语言）。
 *
 * @param names 多语言文案映射。
 * @param locales 语言清单。
 * @param requiredCode 必填语言标识。
 * @returns 提示文案。
 */
export function nameHintText(names, locales, requiredCode) {
    const total = locales.length;
    const filled = countFilled(names, locales);
    const missing = deriveMissingNameLocales(names, locales).filter((code) => code !== normalizeCode(requiredCode));
    if (missing.length === 0) {
        return `${I18N_NAME_COUNT_PREFIX} ${filled} / ${total}`;
    }
    return `${I18N_NAME_MISSING_PREFIX}${missing.join('、')}`;
}
/**
 * 缺失回退提示（该语言为空时给出回退目标文案）。
 *
 * @param names 多语言文案映射。
 * @param code 目标语言标识。
 * @param defaultCode 系统默认语言。
 * @param requiredCode 必填语言。
 * @returns 占位提示（无回退目标时为空串）。
 */
export function fallbackHintText(names, code, defaultCode, requiredCode) {
    const source = normalizeCode(code) === normalizeCode(defaultCode) ? requiredCode : defaultCode;
    const text = resolveDisplayText(names, source, requiredCode);
    return text === '' ? '' : `${I18N_FALLBACK_PREFIX}${text}`;
}
/**
 * 筛选语言行（本地筛选：关键字匹配标识或语言名 + 缺失 / 已填三态）。
 *
 * @param rows 语言行。
 * @param filter 筛选条件。
 * @returns 命中行。
 */
export function filterLocaleRows(rows, filter) {
    const keyword = filter.keyword.trim().toLowerCase();
    return rows.filter((row) => {
        if (filter.mode === 'missing' && !row.missing) {
            return false;
        }
        if (filter.mode === 'filled' && row.missing) {
            return false;
        }
        if (keyword === '') {
            return true;
        }
        return row.code.toLowerCase().includes(keyword) || row.name.toLowerCase().includes(keyword);
    });
}
/**
 * 多语言文案映射是否等价（键集与逐值相等；未保存变更判定用）。
 *
 * @param left 左侧映射。
 * @param right 右侧映射。
 * @returns 是否等价。
 */
export function isNamesEqual(left, right) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    if (leftKeys.length !== rightKeys.length) {
        return false;
    }
    return leftKeys.every((key) => String(left[key] ?? '') === String(right[key] ?? ''));
}
/**
 * 明细行文案是否为空（保留原样的编辑值判定）。
 *
 * @param row 语言行。
 * @returns 是否为空。
 */
export function isRowBlank(row) {
    return isBlankName(row.value);
}
