/**
 * 领域纯函数：表单渲染（布局元数据驱动渲染的数据态语义）。
 *
 * 消费 `domain/form-layout` 的设计产出（`LayoutEffective`），只做**渲染分发、三态与字段权限叠加、
 * 校验执行与定位、明细区与提交载荷装配**——不重定义元数据契约；字段类型只映射为框架无关的
 * **控件语义键**（具体组件归各端插件），规则编译复用 `domain/validators`。
 * 框架无关、不触 DOM、不请求，同输入同输出。
 */
import { normalizeCaptchaKind, normalizeCaptchaScene } from './captcha';
import { DEFAULT_LAYOUT_COLUMNS, SECTION_KEY_PREFIX, normalizeLayout } from './form-layout';
import { codePattern, lengthRange, numberRange, required as requiredRule } from './validators';
/** 渲染器占位文案（数据通路未就绪）。 */
export const RENDERER_PLACEHOLDER_TEXT = '表单渲染器未就绪（占位）';
/** 空布局回退提示文案。 */
export const RENDERER_FALLBACK_HINT = '未配置布局，已按字段默认栅格渲染';
/** 未注册字段类型回退文案。 */
export const RENDERER_UNKNOWN_TYPE_HINT = '未注册的字段类型，已回退纯文本';
/** 无可见字段空态文案。 */
export const RENDERER_EMPTY_HINT = '没有可渲染的字段';
/** 脱敏掩码文本。 */
export const MASK_TEXT = '******';
/** 空值展示占位。 */
export const EMPTY_TEXT = '—';
/** 明细区未配置时的回退列数上限。 */
export const DEFAULT_DETAIL_COLUMNS = 6;
/** 明细区缺省每页行数。 */
export const DEFAULT_DETAIL_PAGE_SIZE = 20;
/** 渲染权限码（登录即可；未注入权限上下文视为有权，后端兜底）。 */
export const FORM_RENDER_PERM = 'formdesign:query';
/** 控件语义键全量（含未知回退 `plain`）。 */
export const FIELD_WIDGETS = [
    'text',
    'textarea',
    'number',
    'datetime',
    'select',
    'multi-select',
    'radio',
    'checkbox',
    'switch',
    'file',
    'image',
    'file-upload',
    'image-upload',
    'richtext',
    'tree-select',
    'org-select',
    'dict-select',
    'dict-multi',
    'transfer',
    'cascader',
    'tags',
    'captcha',
    'i18n-name',
    'i18n-text',
    'plain',
];
/** 字段类型 → 控件语义键内建映射表（表外类型回退 `plain`）。 */
export const FIELD_WIDGET_MAP = {
    text: 'text',
    longtext: 'textarea',
    textarea: 'textarea',
    number: 'number',
    amount: 'number',
    percent: 'number',
    date: 'datetime',
    datetime: 'datetime',
    select: 'select',
    multi_select: 'multi-select',
    radio: 'radio',
    checkbox: 'checkbox',
    switch: 'switch',
    file: 'file-upload',
    image: 'image-upload',
    richtext: 'richtext',
    dept: 'org-select',
    tree: 'tree-select',
    user: 'org-select',
    post: 'org-select',
    org: 'org-select',
    dict: 'dict-select',
    dict_multi: 'dict-multi',
    transfer: 'transfer',
    cascader: 'cascader',
    tags: 'tags',
    captcha: 'captcha',
    'i18n-name': 'i18n-name',
    i18n_name: 'i18n-name',
    'i18n-text': 'i18n-text',
    i18n_text: 'i18n-text',
};
/** 已知层级取值。 */
const LEVELS = ['platform', 'tenant', 'role'];
/** 已知字段状态取值。 */
const FIELD_STATUSES = ['pending', 'active', 'failed', 'disabled'];
/** 已知字段分组取值。 */
const FIELD_GROUPS = ['platform', 'tenant'];
/** 已知规则种类取值。 */
const RULE_KINDS = ['required', 'length', 'range', 'pattern', 'options'];
/**
 * 解析字段控件语义键（表外类型回退 `plain`）。
 *
 * @param type 字段类型。
 */
export function resolveFieldWidget(type) {
    return FIELD_WIDGET_MAP[type] ?? 'plain';
}
/**
 * 字段类型是否已登记（内建映射表内且非 `plain` 回退）。
 *
 * @param type 字段类型。
 */
export function isKnownFieldType(type) {
    const widget = FIELD_WIDGET_MAP[type];
    return widget !== undefined && widget !== 'plain';
}
/**
 * 归一三态（非法值回落 `create`）。
 *
 * @param mode 原始值。
 */
export function normalizeRenderMode(mode) {
    return mode === 'edit' || mode === 'view' ? mode : 'create';
}
/** 归一字段状态。 */
function normalizeFieldStatus(status) {
    return typeof status === 'string' && FIELD_STATUSES.includes(status) ? status : undefined;
}
/** 归一选项集。 */
function normalizeOptions(options) {
    if (!Array.isArray(options)) {
        return [];
    }
    const result = [];
    for (const item of options) {
        if (item === null || typeof item !== 'object') {
            continue;
        }
        const record = item;
        if (record.value === null || record.value === undefined) {
            continue;
        }
        result.push({
            value: String(record.value),
            label: typeof record.label === 'string' ? record.label : String(record.value),
        });
    }
    return result;
}
/** 归一规则集（非法规则剔除）。 */
function normalizeRules(rules) {
    if (!Array.isArray(rules)) {
        return [];
    }
    const result = [];
    for (const item of rules) {
        if (item === null || typeof item !== 'object') {
            continue;
        }
        const record = item;
        if (typeof record.kind !== 'string' || !RULE_KINDS.includes(record.kind)) {
            continue;
        }
        const rule = { kind: record.kind };
        if (typeof record.min === 'number') {
            rule.min = record.min;
        }
        if (typeof record.max === 'number') {
            rule.max = record.max;
        }
        if (typeof record.pattern === 'string') {
            rule.pattern = record.pattern;
        }
        if (typeof record.message === 'string') {
            rule.message = record.message;
        }
        result.push(rule);
    }
    return result;
}
/**
 * 归一单个字段（缺省项补确定值，运行态无 `undefined` 成员）。
 *
 * @param input 字段装载输入。
 * @param index 下标（用于派生缺省键）。
 */
export function normalizeField(input, index = 0) {
    const source = input ?? {};
    const field = {
        key: typeof source.key === 'string' && source.key !== '' ? source.key : `${SECTION_KEY_PREFIX}${index + 1}`,
        label: typeof source.label === 'string' ? source.label : '',
        type: typeof source.type === 'string' && source.type !== '' ? source.type : 'text',
        group: typeof source.group === 'string' && FIELD_GROUPS.includes(source.group)
            ? source.group
            : 'platform',
    };
    const status = normalizeFieldStatus(source.status);
    if (status !== undefined) {
        field.status = status;
    }
    if (source.disabled === true) {
        field.disabled = true;
    }
    if (source.required === true) {
        field.required = true;
    }
    if (typeof source.placeholder === 'string' && source.placeholder !== '') {
        field.placeholder = source.placeholder;
    }
    if (source.defaultValue !== undefined) {
        field.defaultValue = source.defaultValue;
    }
    const rules = normalizeRules(source.rules);
    if (rules.length > 0) {
        field.rules = rules;
    }
    const options = normalizeOptions(source.options);
    if (options.length > 0) {
        field.options = options;
    }
    if (typeof source.dictType === 'string' && source.dictType !== '') {
        field.dictType = source.dictType;
    }
    if (typeof source.uploadAccept === 'string' && source.uploadAccept !== '') {
        field.uploadAccept = source.uploadAccept;
    }
    if (typeof source.uploadMaxSize === 'number' && Number.isFinite(source.uploadMaxSize) && source.uploadMaxSize > 0) {
        field.uploadMaxSize = source.uploadMaxSize;
    }
    if (typeof source.uploadLimit === 'number' && Number.isFinite(source.uploadLimit) && source.uploadLimit > 0) {
        field.uploadLimit = source.uploadLimit;
    }
    if (source.uploadMultiple === true || source.uploadMultiple === false) {
        field.uploadMultiple = source.uploadMultiple;
    }
    const captchaKind = normalizeCaptchaKind(source.captchaKind);
    if (captchaKind !== undefined) {
        field.captchaKind = captchaKind;
    }
    const captchaScene = normalizeCaptchaScene(source.captchaScene);
    if (captchaScene !== undefined) {
        field.captchaScene = captchaScene;
    }
    if (source.readonly === true) {
        field.readonly = true;
    }
    if (source.hidden === true) {
        field.hidden = true;
    }
    return field;
}
/**
 * 归一渲染元数据（装载输入 → 运行态；`LayoutEffective` 直传时按需补齐字段清单）。
 *
 * @param input 装载输入或生效布局。
 */
export function normalizeRenderMetadata(input) {
    if (input === undefined || input === null) {
        const empty = {
            layout: normalizeLayout(undefined),
            fields: [],
            level: 'tenant',
            source: 'empty',
            readonly: true,
            fallback: true,
            permissions: {},
        };
        return empty;
    }
    const raw = input;
    const fields = Array.isArray(raw.fields) ? raw.fields.map((field, index) => normalizeField(field, index)) : [];
    const level = typeof raw.level === 'string' && LEVELS.includes(raw.level) ? raw.level : 'tenant';
    const source = typeof raw.source === 'string' && (LEVELS.includes(raw.source) || raw.source === 'empty')
        ? raw.source
        : 'empty';
    const permissions = {};
    for (const [key, value] of Object.entries(raw.permissions ?? {})) {
        const entry = {};
        if (typeof value?.visible === 'boolean') {
            entry.visible = value.visible;
        }
        if (typeof value?.editable === 'boolean') {
            entry.editable = value.editable;
        }
        if (typeof value?.required === 'boolean') {
            entry.required = value.required;
        }
        if (typeof value?.mask === 'boolean') {
            entry.mask = value.mask;
        }
        permissions[key] = entry;
    }
    return {
        layout: normalizeLayout(raw.layout),
        fields,
        level,
        source,
        readonly: raw.readonly === true,
        fallback: raw.fallback === true,
        permissions,
    };
}
/**
 * 归一件层字段覆盖（缺省返回空对象）。
 *
 * @param input 覆盖集合。
 */
export function normalizeFieldOverrides(input) {
    if (input === undefined || input === null) {
        return {};
    }
    const result = {};
    for (const [key, value] of Object.entries(input)) {
        if (value === undefined || value === null) {
            continue;
        }
        result[key] = { ...value };
    }
    return result;
}
/**
 * 解析三态可编辑基线（`view` / 强制只读恒不可编辑）。
 *
 * @param mode 三态。
 * @param forceReadOnly 外部强制只读。
 */
export function resolveBaselineEditable(mode, forceReadOnly = false) {
    if (forceReadOnly) {
        return false;
    }
    return mode !== 'view';
}
/**
 * 解析字段渲染状态（三态基线 → 字段属性 → 权限终态，**双向覆盖**）。
 *
 * @param input 输入（字段 / 覆盖 / 权限 / 三态 / 强制只读）。
 */
export function resolveFieldRenderState(input) {
    const { field, override, permission } = input;
    const baseline = resolveBaselineEditable(input.mode, input.forceReadOnly ?? false);
    const hidden = override?.hidden ?? field.hidden ?? false;
    const readonly = override?.readonly ?? field.readonly ?? false;
    const required = override?.required ?? field.required ?? false;
    const visible = permission?.visible ?? !hidden;
    const editable = permission?.editable ?? (baseline && !readonly);
    return {
        visible,
        editable,
        disabled: !editable,
        required: permission?.required ?? required,
        masked: permission?.mask ?? false,
        displayOnly: input.mode === 'view',
    };
}
/** 合并字段属性（覆盖优先）。 */
function mergeAttrs(field, override) {
    if (override === undefined) {
        return field;
    }
    return {
        required: override.required ?? field.required,
        placeholder: override.placeholder ?? field.placeholder,
        defaultValue: override.defaultValue ?? field.defaultValue,
        rules: override.rules ?? field.rules,
        options: override.options ?? field.options,
        dictType: override.dictType ?? field.dictType,
        uploadAccept: override.uploadAccept ?? field.uploadAccept,
        uploadMaxSize: override.uploadMaxSize ?? field.uploadMaxSize,
        uploadLimit: override.uploadLimit ?? field.uploadLimit,
        uploadMultiple: override.uploadMultiple ?? field.uploadMultiple,
        readonly: override.readonly ?? field.readonly,
        hidden: override.hidden ?? field.hidden,
    };
}
/**
 * 构建字段渲染项。
 *
 * @param input 输入（字段 / 覆盖 / 权限 / 三态 / 值 / 跨列）。
 */
export function buildFieldPlan(input) {
    const attrs = mergeAttrs(input.field, input.override);
    const state = resolveFieldRenderState({
        field: input.field,
        override: input.override,
        permission: input.permission,
        mode: input.mode,
        forceReadOnly: input.forceReadOnly,
    });
    const widget = resolveFieldWidget(input.field.type);
    return {
        ...state,
        key: input.field.key,
        label: input.field.label,
        widget,
        unknown: widget === 'plain' && !isKnownFieldType(input.field.type),
        colSpan: input.colSpan === true,
        placeholder: typeof attrs.placeholder === 'string' ? attrs.placeholder : '',
        defaultValue: attrs.defaultValue,
        options: normalizeOptions(attrs.options),
        rules: mkFieldRules(input.field, { override: input.override, state }),
        value: input.value ?? attrs.defaultValue,
        base: input.field,
    };
}
/**
 * 构建渲染计划（分区 / 分组 / 字段 + 明细列 + 跳过项）。
 *
 * @param effective 生效布局。
 * @param input 输入（三态 / 强制只读 / 数据 / 权限 / 覆盖）。
 */
export function buildRenderPlan(effective, input = {}) {
    const mode = normalizeRenderMode(input.mode);
    const data = input.data ?? {};
    const permissions = input.permissions ?? effective.permissions ?? {};
    const overrides = normalizeFieldOverrides(input.overrides);
    const layout = normalizeLayout(effective.layout);
    const byKey = new Map(effective.fields.map((field) => [field.key, field]));
    const unknownFields = [];
    const disabledFields = [];
    const hiddenFields = [];
    const sections = [];
    /** 构建字段项（缺字段定义即记失效并跳过；停用 / 建列失败转只读保留）。 */
    const buildField = (key, colSpan) => {
        const field = byKey.get(key);
        if (field === undefined) {
            if (!unknownFields.includes(key)) {
                unknownFields.push(key);
            }
            return undefined;
        }
        const unusable = field.disabled === true || (field.status !== undefined && field.status !== 'active');
        if (unusable && !disabledFields.includes(key)) {
            disabledFields.push(key);
        }
        const explicit = overrides[key];
        const merged = unusable ? { ...explicit, readonly: true } : explicit;
        const item = buildFieldPlan({
            field,
            override: merged,
            permission: permissions[key],
            mode,
            forceReadOnly: input.forceReadOnly ?? false,
            value: data[key],
            colSpan,
        });
        if (!item.visible && !hiddenFields.includes(key)) {
            hiddenFields.push(key);
        }
        return item;
    };
    for (const section of layout.main.sections) {
        const groups = [];
        const fields = [];
        /** 分区内非分组字段（有分组时先行平铺渲染）。 */
        const ungroupedFields = [];
        for (const ref of section.fields) {
            const item = buildField(ref.key, ref.colSpan === true);
            if (item !== undefined) {
                fields.push(item);
                ungroupedFields.push(item);
            }
        }
        for (const group of section.groups ?? []) {
            const groupFields = [];
            for (const ref of group.fields) {
                const item = buildField(ref.key, ref.colSpan === true);
                if (item !== undefined) {
                    groupFields.push(item);
                    fields.push(item);
                }
            }
            groups.push({ key: group.key, title: group.title, fields: groupFields });
        }
        sections.push({
            key: section.key,
            title: section.title,
            columns: section.columns,
            fields,
            ungroupedFields: groups.length === 0 ? fields : ungroupedFields,
            groups,
        });
    }
    const configured = layout.detail?.columns ?? [];
    const detailFallback = configured.length === 0;
    const detailSource = detailFallback
        ? fallbackDetailColumns(sections)
        : configured.map((column) => ({ key: column.key, width: column.width }));
    const readonly = effective.readonly || (input.forceReadOnly ?? false);
    const detailColumns = detailSource.map((column) => {
        const base = byKey.get(column.key);
        const item = {
            ...column,
            title: base?.label ?? column.key,
            editable: !readonly,
        };
        if (base !== undefined) {
            item.base = base;
        }
        return item;
    });
    return {
        sections,
        detailColumns,
        detailFallback,
        unknownFields,
        disabledFields,
        hiddenFields,
        fallback: effective.fallback,
        readonly,
    };
}
/**
 * 明细列回退：按主表字段顺序去重取前若干列。
 *
 * @param sections 分区计划。
 */
export function fallbackDetailColumns(sections) {
    const result = [];
    const seen = new Set();
    for (const section of sections) {
        for (const field of section.fields) {
            if (seen.has(field.key)) {
                continue;
            }
            seen.add(field.key);
            result.push({ key: field.key });
            if (result.length >= DEFAULT_DETAIL_COLUMNS) {
                return result;
            }
        }
    }
    return result;
}
/**
 * 统计计划内的字段数（含不可见字段）。
 *
 * @param plan 渲染计划。
 */
export function countPlanFields(plan) {
    return plan.sections.reduce((sum, section) => sum + section.fields.length, 0);
}
/**
 * 取计划内可见字段。
 *
 * @param plan 渲染计划。
 */
export function visibleFields(plan) {
    return plan.sections.flatMap((section) => section.fields.filter((field) => field.visible));
}
/**
 * 生成字段规则（字段属性 → 声明式规则集；不可见 / 只读不产出必填）。
 *
 * @param field 字段。
 * @param input 输入（覆盖 / 渲染状态）。
 */
export function mkFieldRules(field, input = {}) {
    const attrs = mergeAttrs(field, input.override);
    const explicit = normalizeRules(attrs.rules);
    const rules = [];
    const visible = input.state?.visible ?? true;
    const editable = input.state?.editable ?? true;
    const required = input.state?.required ?? attrs.required ?? false;
    if (required && visible && editable && !explicit.some((rule) => rule.kind === 'required')) {
        rules.push({ kind: 'required' });
    }
    rules.push(...explicit);
    return rules;
}
/**
 * 编译声明式规则为校验器链（复用既有 `domain/validators`）。
 *
 * @param rules 规则集。
 */
export function compileFieldRules(rules) {
    const validators = [];
    for (const rule of rules) {
        if (rule.kind === 'required') {
            validators.push(requiredRule(rule.message ?? '必填'));
            continue;
        }
        if (rule.kind === 'length') {
            validators.push(lengthRange(rule.min ?? 0, rule.max ?? 255, rule.message));
            continue;
        }
        if (rule.kind === 'range') {
            validators.push(numberRange(rule.min ?? 0, rule.max ?? 0, rule.message));
            continue;
        }
        if (rule.kind === 'pattern') {
            if (typeof rule.pattern === 'string' && rule.pattern !== '') {
                validators.push(codePattern(new RegExp(rule.pattern), rule.message ?? '格式不正确'));
            }
            continue;
        }
        if (rule.kind === 'options') {
            // 选项集校验在 `validateFieldValue` 内按字段选项集执行（规则本身不携带选项）。
            continue;
        }
    }
    return validators;
}
/**
 * 是否空值（`null` / `undefined` / 空串 / 空数组）。
 *
 * @param value 值。
 */
function isEmptyValue(value) {
    return value == null || value === '' || (Array.isArray(value) && value.length === 0);
}
/**
 * 校验单字段值（不可见 / 只读 / 非必填空值跳过）。
 *
 * @param field 字段。
 * @param value 值。
 * @param input 输入（覆盖 / 权限 / 三态 / 强制只读）。
 */
export function validateFieldValue(field, value, input = {}) {
    const state = resolveFieldRenderState({
        field,
        override: input.override,
        permission: input.permission,
        mode: normalizeRenderMode(input.mode),
        forceReadOnly: input.forceReadOnly ?? false,
    });
    if (!state.visible || !state.editable) {
        return undefined;
    }
    const attrs = mergeAttrs(field, input.override);
    const rules = mkFieldRules(field, { override: input.override, state });
    if (state.required && isEmptyValue(value)) {
        const explicit = rules.find((rule) => rule.kind === 'required');
        return explicit?.message ?? '必填';
    }
    for (const validator of compileFieldRules(rules)) {
        const message = validator(value);
        if (message !== undefined) {
            return message;
        }
    }
    const options = normalizeOptions(attrs.options);
    if (options.length > 0 && !isEmptyValue(value)) {
        const allowed = new Set(options.map((option) => option.value));
        const values = Array.isArray(value) ? value : [value];
        for (const item of values) {
            if (!allowed.has(String(item))) {
                return '选项不在可选范围内';
            }
        }
    }
    return undefined;
}
/**
 * 表单全量校验（主表可见字段逐项校验，定位首个错误字段）。
 *
 * @param plan 渲染计划。
 * @param data 主表数据。
 * @param input 输入（覆盖 / 权限）。
 */
export function validateFormData(plan, data = {}) {
    const errors = [];
    for (const item of plan.sections.flatMap((section) => section.fields)) {
        if (!item.visible) {
            continue;
        }
        const value = item.key in data ? data[item.key] : item.value;
        // 计划项已含生效渲染状态与规则，直接按规则链执行（不重复叠加权限）。
        const isEmpty = isEmptyValue(value);
        const requiredRuleHit = item.rules.find((rule) => rule.kind === 'required');
        let message;
        if (item.required && isEmpty) {
            message = requiredRuleHit?.message ?? '必填';
        }
        else {
            for (const validator of compileFieldRules(item.rules)) {
                message = validator(value);
                if (message !== undefined) {
                    break;
                }
            }
        }
        if (message === undefined && item.options.length > 0 && !isEmpty) {
            const allowed = new Set(item.options.map((option) => option.value));
            const values = Array.isArray(value) ? value : [value];
            message = values.every((entry) => allowed.has(String(entry))) ? undefined : '选项不在可选范围内';
        }
        if (message !== undefined) {
            errors.push({ field: item.key, message });
        }
    }
    return {
        valid: errors.length === 0,
        errors,
        firstField: errors[0]?.field,
        message: errors.length === 0 ? '' : errors.map((error) => `${error.field}：${error.message}`).join('；'),
    };
}
/**
 * 明细行级校验（逐行逐列，复用同一套规则，定位 `页签 → 行 → 列`）。
 *
 * @param columns 明细列。
 * @param rows 行集合。
 * @param detailKey 明细页签键（错误定位用）。
 */
export function validateDetailRows(columns, rows, detailKey = '') {
    const errors = [];
    rows.forEach((row, index) => {
        for (const column of columns) {
            const base = column.base;
            if (base === undefined) {
                continue;
            }
            // 只读列不校验（查看态明细整体只读，历史数据不阻塞查看）。
            const message = validateFieldValue(base, row?.[column.key], { mode: column.editable ? 'edit' : 'view' });
            if (message !== undefined) {
                errors.push({ detailKey, index, field: column.key, message: `第 ${index + 1} 行 ${column.title}：${message}` });
            }
        }
    });
    return {
        valid: errors.length === 0,
        errors,
        message: errors.length === 0 ? '' : errors.map((error) => error.message).join('；'),
    };
}
/**
 * 明细全量校验（全部页签，按页签序汇总）。
 *
 * @param plan 渲染计划。
 * @param details 明细数据。
 */
export function validateDetails(plan, details = {}) {
    const errors = [];
    for (const [detailKey, rows] of Object.entries(details)) {
        errors.push(...validateDetailRows(plan.detailColumns, rows, detailKey).errors);
    }
    return {
        valid: errors.length === 0,
        errors,
        message: errors.length === 0 ? '' : errors.map((error) => error.message).join('；'),
    };
}
/**
 * 脱敏文本（空值回占位）。
 *
 * @param value 值。
 */
export function maskFieldText(value) {
    return isEmptyValue(value) ? EMPTY_TEXT : MASK_TEXT;
}
/**
 * 展示文本（空值回占位，数组按顿号连接）。
 *
 * @param value 值。
 */
export function displayFieldText(value) {
    if (isEmptyValue(value)) {
        return EMPTY_TEXT;
    }
    if (Array.isArray(value)) {
        return value.map((item) => String(item)).join('、');
    }
    if (value !== null && typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}
/**
 * 归一行集合（剔除非对象与空行）。
 *
 * @param rows 原始行集合。
 */
export function normalizeDetailRows(rows) {
    if (!Array.isArray(rows)) {
        return [];
    }
    const result = [];
    for (const row of rows) {
        if (row === null || row === undefined || typeof row !== 'object' || Array.isArray(row)) {
            continue;
        }
        result.push({ ...row });
    }
    return result;
}
/**
 * 归一明细数据（缺省页签补空数组；运行态确定值）。
 *
 * @param details 明细数据。
 * @param keys 需要保证存在的页签键。
 */
export function normalizeDetailSet(details, keys = []) {
    const result = {};
    for (const key of keys) {
        result[key] = [];
    }
    for (const [key, rows] of Object.entries(details ?? {})) {
        result[key] = normalizeDetailRows(rows);
    }
    return result;
}
/**
 * 装配提交载荷（主表只含可见字段；只读字段保留；明细归一）。
 *
 * @param input 输入。
 */
export function buildSubmitPayload(input) {
    const data = input.data ?? {};
    const payload = {
        formCode: input.formCode,
        mode: input.mode,
        data: {},
        details: normalizeDetailSet(input.details, input.plan.detailColumns.length === 0 ? [] : Object.keys(input.details ?? {})),
    };
    for (const field of input.plan.sections.flatMap((section) => section.fields)) {
        if (!field.visible) {
            continue;
        }
        if (field.key in data) {
            payload.data[field.key] = data[field.key];
        }
        else if (field.defaultValue !== undefined) {
            payload.data[field.key] = field.defaultValue;
        }
    }
    if (input.recordId !== undefined) {
        payload.recordId = input.recordId;
    }
    if (input.mode === 'edit' && input.recordVersion !== undefined) {
        payload.recordVersion = input.recordVersion;
    }
    return payload;
}
/**
 * 是否允许提交（只读 / 进行中 / 校验未过均不允许）。
 *
 * @param input 输入。
 */
export function isSubmitAllowed(input) {
    if (input.readonly || input.busy || !input.validation.valid) {
        return false;
    }
    return input.detailValidation?.valid ?? true;
}
/**
 * 分区列数是否合法（供件层栅格类名派生）。
 *
 * @param columns 列数。
 */
export function isSectionColumnsValid(columns) {
    return columns === 1 || columns === 2 || columns === 3;
}
/**
 * 分区栅格跨度（Tailwind 口径的 12 栅格换算，供件层内联样式）。
 *
 * @param columns 列数。
 */
export function sectionSpan(columns) {
    return Math.max(1, Math.round(24 / (isSectionColumnsValid(columns) ? columns : DEFAULT_LAYOUT_COLUMNS)));
}
